#!/usr/bin/env python3
"""IRFEN v0.9 · ubicaciones documentales ANA 2016-2017 (centros poblados vulnerables por activación de quebradas) en
los departamentos costeros. RESEARCH_ONLY / TEST_ONLY.

Entradas (todas en el repositorio, sin red):
* data/v09/sources/ana2017_complementacion_quebradas/: registro de descarga del PDF (SHA-256), páginas renderizadas y
  lecturas OCR celda a celda (scripts/v09_ana2017_table_ocr.py);
* data/v09/sources/inei_coastal_provinces/provinces.geojson: provincias INEI referenciales (comprobación de jurisdicción);
* config/phase2_national_inventory_completeness_audit_v0_1.json: maestro nacional (solo lectura, para enlazar).

Qué es cada punto: la coordenada UTM que ANA da para un CENTRO POBLADO vulnerable expuesto a la activación de una
quebrada nombrada. NO es la ubicación de la quebrada, ni de su cauce, ni de su desembocadura, ni una zona de inundación.

Regla de admisión (todas obligatorias):
1. al menos dos de las tres lecturas OCR independientes de Este y de Norte coinciden y tienen 6 y 7 cifras;
2. el datum y la zona UTM se leen del pie del propio cuadro («WGS 84 - ZONA nn SUR»);
3. el punto transformado (EPSG:327nn → WGS84) cae dentro de la provincia INEI que declara la fila.
Lo que no cumple queda en la lista con su motivo y no se dibuja. Nada se corrige a mano en silencio: las revisiones
visuales, si las hay, se registran en REVIEWS con la página y el motivo.

    python scripts/v09_build_ana2017_coastal_points.py           # escribe site/data/v09/ana2017_coastal_points_v0_1.json
    python scripts/v09_build_ana2017_coastal_points.py --check   # reconstruye y compara
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana2017_complementacion_quebradas"
OCR = SRC / "ocr_tables.json"
RECORD = SRC / "source_record.json"
PAGES_INDEX = SRC / "table_pages_index.json"
PROVINCES = ROOT / "data/v09/sources/inei_coastal_provinces/provinces.geojson"
PROVINCES_PROV = ROOT / "data/v09/sources/inei_coastal_provinces/provenance.json"
MASTER = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
OUT = ROOT / "site/data/v09/ana2017_coastal_points_v0_1.json"
SCHEMA = "irfen_v09_ana2017_coastal_points_v0_1"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None, map_publishable=False)
# cuadro -> department as printed in the title of the cuadro (PDF pages 25..70)
# rows declared by the document itself (department summaries, «Centros poblados vulnerables: N»)
DECLARED_ROWS = {9: 44, 11: 79, 17: 47, 19: 69, 23: 67, 29: 97, 41: 53, 43: 120, 47: 37, 49: 25}
CUADROS = {9: "TUMBES", 11: "PIURA", 17: "LAMBAYEQUE", 19: "LA LIBERTAD", 23: "ANCASH", 29: "LIMA", 41: "ICA",
           43: "AREQUIPA", 47: "MOQUEGUA", 49: "TACNA"}
# Manual visual reviews of single cells (page image read by a person). Empty unless a review is recorded:
# {(cuadro, n): {"field": value, "reason": "...", "reviewed_page": 35}}
REVIEWS: dict[tuple[int, int], dict] = {}


# ---------- geodesy: UTM (WGS84, southern hemisphere) -> lon/lat; Karney/Krüger series, sub-millimetre ----------
A, F = 6378137.0, 1 / 298.257223563
N_ = F / (2 - F)
A_ = A / (1 + N_) * (1 + N_ ** 2 / 4 + N_ ** 4 / 64)
BETA = [N_ / 2 - 2 * N_ ** 2 / 3 + 37 * N_ ** 3 / 96, N_ ** 2 / 48 + N_ ** 3 / 15, 17 * N_ ** 3 / 480]
DELTA = [2 * N_ - 2 * N_ ** 2 / 3 - 2 * N_ ** 3, 7 * N_ ** 2 / 3 - 8 * N_ ** 3 / 5, 56 * N_ ** 3 / 15]


def utm_to_lonlat(easting: float, northing: float, zone: int, south: bool = True) -> tuple[float, float]:
    k0, e0, n0 = 0.9996, 500000.0, 10000000.0 if south else 0.0
    xi = (northing - n0) / (k0 * A_)
    eta = (easting - e0) / (k0 * A_)
    xi_p = xi - sum(b * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j, b in enumerate(BETA))
    eta_p = eta - sum(b * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j, b in enumerate(BETA))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    lat = chi + sum(d * math.sin(2 * (j + 1) * chi) for j, d in enumerate(DELTA))
    lon0 = math.radians(zone * 6 - 183)
    lon = lon0 + math.atan2(math.sinh(eta_p), math.cos(xi_p))
    return math.degrees(lon), math.degrees(lat)


# ---------- point in (multi)polygon, ray casting with holes ----------
def _in_ring(x: float, y: float, ring: list) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_geometry(x: float, y: float, geom: dict) -> bool:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return any(_in_ring(x, y, p[0]) and not any(_in_ring(x, y, h) for h in p[1:]) for p in polys)


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, fold(a), fold(b)).ratio()


def digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(cell: dict | None) -> int | None:
    """Value read identically by at least two of the three OCR passes; otherwise None (never a guess)."""
    if not cell or not cell.get("consensus"):
        return None
    return int(cell["consensus"])


def build() -> dict:
    ocr = json.loads(OCR.read_text(encoding="utf-8"))
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    pages = {p["file"]: p for p in json.loads(PAGES_INDEX.read_text(encoding="utf-8"))["pages"]}
    provinces = json.loads(PROVINCES.read_text(encoding="utf-8"))["features"]
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    by_dep = {}
    for f in provinces:
        by_dep.setdefault(f["properties"]["NOMBDEP"], []).append(f)
    # rows already transcribed in the master (Tumbes, Piura, Lambayeque): cuadro/row -> inventory id and reference point
    master_rows = {}
    for r in master["candidates"]:
        for e in r.get("evidence") or []:
            if e.get("source_id") == "ANA-2016-COMPLEMENTACION-NACIONAL" and e.get("table") and e.get("row_number_as_read"):
                cu = int(re.sub(r"\D", "", e["table"]))
                master_rows.setdefault((cu, int(e["row_number_as_read"])), []).append(
                    dict(inventory_id=r["inventory_id"], point=e.get("source_reference_point"), name=r["documentary_name"]))
    master_by_dep = {}
    for r in master["candidates"]:
        master_by_dep.setdefault(fold(r["department"]), []).append(r)

    points, tables = [], []
    for t in ocr["tables"]:
        cu = int(re.search(r"cuadro(\d+)", t["file"]).group(1))
        dep = CUADROS[cu]
        zone = t.get("datum_zone_ocr")
        page = pages.get(t["file"], {}).get("pdf_page")
        cands = by_dep.get(dep, []) + (by_dep.get("CALLAO", []) if dep == "LIMA" else [])
        sums = dict(viviendas=0, hab_directos=0, hab_indirectos=0)
        sums_ok_cols = dict(viviendas=True, hab_directos=True, hab_indirectos=True)
        first_point = len(points)
        stats = dict(rows=0, admitted=0, ocr_review=0, outside_province=0, no_datum=0)
        # data rows: a 6-digit Este or a row number read by consensus (the notes row under TOTAL has neither)
        data = [r for r in t.get("rows", []) if number(r["cells"].get("n")) is not None
                or len(r["cells"].get("este", {}).get("consensus") or "") == 6]
        nums = [number(r["cells"].get("n")) for r in data]
        for i, v in enumerate(nums):  # a missing number is inferred only when both neighbours enclose it exactly
            if v is None and 0 < i < len(nums) - 1 and nums[i - 1] is not None and nums[i + 1] == nums[i - 1] + 2:
                nums[i] = -(nums[i - 1] + 1)  # negative = inferred
        seen = [abs(v) for v in nums if v is not None]
        declared = DECLARED_ROWS.get(cu)
        stats["rows_declared"] = declared
        stats["rows_not_read"] = sorted(set(range(1, (declared or 0) + 1)) - set(seen))
        stats["number_inferred"] = sum(1 for v in nums if v is not None and v < 0)
        for row, nv in zip(data, nums):
            c = row["cells"]
            if nv is None:
                stats["rows_unnumbered"] = stats.get("rows_unnumbered", 0) + 1
                continue
            n, n_read = abs(nv), (nv if nv > 0 else None)
            rv = REVIEWS.get((cu, n), {})
            e_raw = rv.get("este") or c.get("este", {}).get("consensus")
            n_raw = rv.get("norte") or c.get("norte", {}).get("consensus")
            # second independent reading: the master's own transcription of this row (Tumbes, Piura, Lambayeque). If the
            # OCR has no consensus but one of its three reads equals the master value, two independent reads agree.
            coord_basis = "OCR_2_DE_3"
            mpts = [m["point"] for m in master_rows.get((cu, n), []) if m.get("point")]
            if mpts and (not e_raw or not n_raw):
                me, mn = str(mpts[0]["easting_m"]), str(mpts[0]["northing_m"])
                reads_e = {digits(c.get("este", {}).get(k, "")) for k in ("read_a", "read_b", "read_c")}
                reads_n = {digits(c.get("norte", {}).get(k, "")) for k in ("read_a", "read_b", "read_c")}
                if (e_raw or me in reads_e) and (n_raw or mn in reads_n):
                    e_raw, n_raw, coord_basis = e_raw or me, n_raw or mn, "OCR_1_DE_3_MAS_TRANSCRIPCION_DEL_MAESTRO"
            for key in sums:
                v = number(c.get(key))
                if v is None:
                    sums_ok_cols[key] = False
                else:
                    sums[key] += v
            prov_ocr = c.get("prov", {}).get("text", "")
            best = max(cands, key=lambda f: similar(f["properties"]["NOMBPROV"], prov_ocr), default=None)
            prov_score = similar(best["properties"]["NOMBPROV"], prov_ocr) if best else 0
            prov_name = best["properties"]["NOMBPROV"] if best and prov_score >= 0.6 else None
            reasons = []
            if not (e_raw and n_raw and len(e_raw) == 6 and len(n_raw) == 7):
                reasons.append("OCR_COORDENADAS_SIN_CONSENSO")
            if not zone:
                reasons.append("DATUM_NO_LEIDO")
            if not prov_name:
                reasons.append("PROVINCIA_NO_RECONOCIDA")
            lon = lat = None
            in_prov = None
            found_in = None
            if "OCR_COORDENADAS_SIN_CONSENSO" not in reasons and zone:
                lon, lat = utm_to_lonlat(int(e_raw), int(n_raw), zone)
                found_in = next((f"{f['properties']['NOMBDEP']}/{f['properties']['NOMBPROV']}" for f in provinces
                                 if in_geometry(lon, lat, f["geometry"])), None)
                if prov_name:
                    in_prov = in_geometry(lon, lat, best["geometry"])
                    if not in_prov:
                        reasons.append("FUERA_DE_LA_PROVINCIA_DECLARADA")
            status = "ADMITIDA_UBICACION_DOCUMENTAL" if not reasons else (
                "FUERA_DE_PROVINCIA" if reasons == ["FUERA_DE_LA_PROVINCIA_DECLARADA"] else "REVISION_PENDIENTE")
            stats["rows"] += 1
            stats["admitted"] += status == "ADMITIDA_UBICACION_DOCUMENTAL"
            stats["outside_province"] += status == "FUERA_DE_PROVINCIA"
            stats["ocr_review"] += "OCR_COORDENADAS_SIN_CONSENSO" in reasons
            stats["no_datum"] += "DATUM_NO_LEIDO" in reasons
            quebrada = c.get("quebrada", {}).get("text", "")
            # link to the master: by cuadro/row where the master transcribed it, else by quebrada name in the department
            links, check = [], None
            for m in master_rows.get((cu, n), []):
                links.append(dict(inventory_id=m["inventory_id"], basis="MISMA_FILA_DEL_CUADRO_EN_EL_MAESTRO"))
                if m.get("point") and e_raw and n_raw and coord_basis == "OCR_2_DE_3":  # independent check only
                    check = dict(master_easting=m["point"]["easting_m"], master_northing=m["point"]["northing_m"],
                                 matches=(int(e_raw), int(n_raw)) == (m["point"]["easting_m"], m["point"]["northing_m"]))
            if not links and fold(quebrada) not in ("", "s n", "sn"):
                for r in master_by_dep.get(fold(dep), []):
                    names = [r["documentary_name"], *(r.get("name_variants_observed") or [])]
                    if any(fold(x) == fold(quebrada) or fold(x) == fold(re.sub(r"(?i)^quebrada\s+", "", quebrada)) for x in names):
                        links.append(dict(inventory_id=r["inventory_id"], basis="MISMO_NOMBRE_EN_EL_DEPARTAMENTO_POR_COMPROBAR"))
            points.append(dict(
                id=f"ANA2017-C{cu:02d}-{n:03d}", cuadro=cu, row=n, ocr_row_index=row["row_index"], row_number_ocr=n_read, row_number_inferred=nv < 0,
                pdf_page=page, department=dep,
                province_ocr=prov_ocr, province_inei=prov_name, province_match=round(prov_score, 2),
                district_ocr=c.get("distrito", {}).get("text", ""), centro_poblado_ocr=c.get("centro", {}).get("text", ""),
                quebrada_ocr=quebrada, unnamed_quebrada=fold(quebrada) in ("s n", "sn", ""),
                utm=dict(easting_m=int(e_raw) if e_raw and e_raw.isdigit() else None, northing_m=int(n_raw) if n_raw and n_raw.isdigit() else None,
                         zone=zone, hemisphere="S", epsg=f"EPSG:327{zone}" if zone else None, datum="WGS 84"),
                lon=round(lon, 6) if lon is not None else None, lat=round(lat, 6) if lat is not None else None,
                in_declared_province=in_prov, point_in_inei_province=found_in, coordinate_basis=coord_basis if e_raw else None,
                status=status, reasons=reasons,
                exposure=dict(viviendas=number(c.get("viviendas")), habitantes_directos=number(c.get("hab_directos")),
                              habitantes_indirectos=number(c.get("hab_indirectos"))),
                inventory_links=links, master_transcription_check=check, manual_review=rv or None))
        tot = t.get("total_row") or {}
        totals = {k: number(tot.get(k)) for k in sums}
        col_ok = {k: sums_ok_cols.get(k, False) and totals[k] is not None and totals[k] == sums[k] for k in sums}
        for p in points[first_point:]:
            for k, out in (("viviendas", "viviendas"), ("hab_directos", "habitantes_directos"), ("hab_indirectos", "habitantes_indirectos")):
                if not col_ok[k]:
                    p["exposure"][out] = None
            p["exposure"]["checksum_basis"] = "columna = TOTAL del cuadro" if any(col_ok.values()) else "sin suma de control: no se publica"
        tables.append(dict(cuadro=cu, department=dep, pdf_page=page, datum_zone=zone, footer_ocr=t.get("footer_ocr"),
                           columns=t.get("columns"), **stats,
                           checksums=dict(totals_in_cuadro=totals, sums_of_rows=sums, columns_ok=col_ok)))
    checks = [p["master_transcription_check"] for p in points if p["master_transcription_check"]]
    # navigation only: bounding box of the INEI referential provinces of each department (never drawn as a geometry)
    departments = {}
    for dep in sorted(set(CUADROS.values()) | {"CALLAO"}):
        xs, ys = [], []
        for f in by_dep.get(dep, []):
            g = f["geometry"]
            for poly in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
                for x, y in poly[0]:
                    xs.append(x)
                    ys.append(y)
        if xs:
            departments[dep] = dict(bbox=[round(min(ys), 4), round(min(xs), 4), round(max(ys), 4), round(max(xs), 4)],
                                    provinces=len(by_dep.get(dep, [])))
    return dict(
        schema_version=SCHEMA, **GUARDS,
        purpose_es=("Centros poblados vulnerables por activación de quebradas con coordenadas UTM publicadas por ANA "
                    "(2016-2017), departamentos costeros. Cada punto es un centro poblado expuesto, NO la ubicación de la "
                    "quebrada, de su cauce ni de su desembocadura, ni una zona de inundación. No entra en la lluvia ni en "
                    "la prioridad."),
        source=dict(source_id="ANA-2016-COMPLEMENTACION-NACIONAL", institution="Autoridad Nacional del Agua (ANA) - DEPHM",
                    title="Complementación de identificación de poblaciones vulnerables por activación de quebradas 2016-2017",
                    url=record["final_url"], registry_url="https://sigrid.cenepred.gob.pe/sigridv3/documento/2799",
                    alt_url=record["url"], pdf_sha256=record["sha256"], pdf_size_bytes=record["size_bytes"],
                    retrieved_at_utc=record["retrieved_at_utc"], pdf_last_modified=record["http_headers"].get("last-modified"),
                    tables="Cuadros 9, 11, 17, 19, 23, 29, 41, 43, 47 y 49 («Centros poblados vulnerables…»)"),
        method=dict(render="poppler pdftoppm 300 dpi (data/v09/sources/ana2017_complementacion_quebradas/table_pages_index.json)",
                    ocr=f"{ocr.get('method')} · {ocr.get('tesseract')} · lengua {ocr.get('text_language')}",
                    ocr_sha256=sha(OCR), crs="UTM WGS 84 zona según el pie de cada cuadro → WGS 84 geográficas (Krüger)",
                    jurisdiction_check=f"punto dentro de la provincia INEI declarada ({PROVINCES.relative_to(ROOT)}, sha256 {sha(PROVINCES)})",
                    names="Nombres tal como los lee el OCR (pueden faltar tildes o haber errores de lectura): por comprobar.",
                    master_cross_check=dict(rows=len(checks), coordinates_identical=sum(1 for c in checks if c["matches"])),
                    manual_reviews=len(REVIEWS)),
        departments=departments, departments_note="bbox [lat_min, lon_min, lat_max, lon_max] de las provincias INEI "
        "referenciales: solo para acercar el mapa; no se dibuja.", tables=tables, points=points)


def dumps(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = dumps(build())
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL: rebuild site/data/v09/ana2017_coastal_points_v0_1.json")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    for t in d["tables"]:
        print(f"C{t['cuadro']:>2} {t['department']:<12} zona {t['datum_zone']} filas {t['rows']:>3}/{t['rows_declared']} admitidas {t['admitted']:>3} "
              f"OCR {t['ocr_review']:>2} fuera {t['outside_province']:>2} no leídas {t['rows_not_read']} sumas {t['checksums']['columns_ok']}")
    print("master cross-check", d["method"]["master_cross_check"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
