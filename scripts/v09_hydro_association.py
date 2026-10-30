#!/usr/bin/env python3
"""IRFEN v0.9 · investigación: relacionar la evidencia territorial documental (centros poblados ANA 2016-2017) con
unidades hidrográficas oficiales ANA y con cauces oficiales nombrados. RESEARCH_ONLY / TEST_ONLY. Sin red.

Entradas (archivadas con SHA-256 por scripts/v09_hydro_units_capture.py):
* data/v09/sources/ana_hydrographic_units/uh_layer8_pacific_part*.geojson.gz — Unidades Hidrográficas ANA (IDEP, capa 8);
* rq_<dep>_part*.geojson.gz — «Ríos y Quebradas» ANA (SNIRH), Tumbes y Piura;
* ign_<dep>_named_part*.geojson.gz — «Corriente de Agua» IGN (IDEP), líneas con nombre, Tumbes y Piura;
* site/data/v09/ana2017_coastal_points_v0_1.json — centros poblados admitidos.

Vocabulario cerrado (nunca se confunde cuenca con cauce, desembocadura ni zona inundable):
* UH_QUE_CONTIENE_AL_CENTRO_POBLADO — el punto documental cae dentro del polígono de la UH. Es una relación
  territorial: NO dice que la quebrada nombrada drene a esa UH ni que el agua llegue al centro poblado.
  Si el punto está a menos de BORDER_M del límite, se marca CERCA_DEL_LIMITE (la coordenada del cuadro no tiene
  precisión declarada).
* Cauce oficial candidato por nombre: una línea oficial cuyo nombre normalizado coincide con la quebrada del cuadro
  a menos de NEAR_M del centro poblado. Candidato: la identidad del cauce exige revisión aparte.
  NOMBRE_COINCIDE_CERCA · NOMBRE_COINCIDE_LEJOS · SIN_LINEA_OFICIAL_CON_ESE_NOMBRE · QUEBRADA_SIN_NOMBRE_EN_EL_CUADRO.
* Celdas IMERG (0,1°) que tocan cada UH de Tumbes y Piura: indicador de si la lluvia por satélite puede
  distinguir la UH (no se calcula lluvia aquí).

    python scripts/v09_hydro_association.py           # escribe data/v09/research/hydro_association_v0_1.json
    python scripts/v09_hydro_association.py --check
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana_hydrographic_units"
POINTS = ROOT / "site/data/v09/ana2017_coastal_points_v0_1.json"
OUT = ROOT / "data/v09/research/hydro_association_v0_1.json"
_spec = importlib.util.spec_from_file_location("b", ROOT / "scripts/v09_build_ana2017_coastal_points.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False, used_by_rain_or_priority=False)
FUNCTIONAL = ("TUMBES", "PIURA")
BORDER_M = 1000.0
NEAR_M = 3000.0
GENERIC = {"quebrada", "qda", "qda.", "rio", "río", "s/n", "sn"}


def load_parts(prefix: str) -> tuple[list[dict], list[dict]]:
    feats, files = [], []
    for p in sorted(SRC.glob(f"{prefix}_part*.geojson.gz")):
        raw = gzip.decompress(p.read_bytes())
        feats += json.loads(raw).get("features", [])
        files.append(dict(file=p.name, sha256_uncompressed=hashlib.sha256(raw).hexdigest()))
    return feats, files


def polys(geom: dict) -> list:
    if not geom:
        return []
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def lines(geom: dict) -> list:
    if not geom:
        return []
    return [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]


def bbox_of(coords_iter) -> list[float]:
    xs, ys = [], []
    for x, y, *_ in coords_iter:
        xs.append(x)
        ys.append(y)
    return [min(xs), min(ys), max(xs), max(ys)]


def metres(lon0: float, lat0: float, lon: float, lat: float) -> tuple[float, float]:
    k = math.cos(math.radians(lat0))
    return (lon - lon0) * 111320.0 * k, (lat - lat0) * 110574.0


def seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def dist_to_paths(lon: float, lat: float, paths: list) -> float:
    best = float("inf")
    for path in paths:
        pts = [metres(lon, lat, x, y) for x, y, *_ in path]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            best = min(best, seg_dist(0.0, 0.0, ax, ay, bx, by))
    return best


def norm_name(s: str) -> str:
    f = B.fold(s)
    f = re.sub(r"^(quebrada|qda|qda\.|rio|r)\s+", "", f)
    f = re.sub(r"^(el|la|los|las)\s+", "", f)
    return f.strip()


def build() -> dict:
    uh, uh_files = load_parts("uh_layer8_pacific")
    for f in uh:
        rings = [p[0] for p in polys(f["geometry"])]
        f["_bbox"] = bbox_of(pt for r in rings for pt in r)
    pts_doc = json.loads(POINTS.read_text(encoding="utf-8"))
    admitted = [p for p in pts_doc["points"] if p["status"] == "ADMITIDA_UBICACION_DOCUMENTAL"]
    channels = {}
    channel_files = {}
    for dep in FUNCTIONAL:
        rq, rq_files = load_parts(f"rq_{dep.lower()}")
        ign, ign_files = load_parts(f"ign_{dep.lower()}_named")
        channels[dep] = dict(ANA=rq, IGN=ign)
        channel_files[dep] = dict(ANA=rq_files, IGN=ign_files)
        for src, feats in channels[dep].items():
            for f in feats:
                props = f.get("properties") or {}
                f["_name"] = norm_name(props.get("NOMBRE_CA") if src == "ANA" else props.get("NOMBRE") or "")
                f["_bbox"] = bbox_of(pt for path in lines(f["geometry"]) for pt in path) if lines(f["geometry"]) else None

    rows, per_uh = [], {}
    for p in admitted:
        lon, lat = p["lon"], p["lat"]
        hit = None
        for f in uh:
            b = f["_bbox"]
            if b[0] <= lon <= b[2] and b[1] <= lat <= b[3] and B.in_geometry(lon, lat, f["geometry"]):
                hit = f
                break
        rec = dict(id=p["id"], department=p["department"], centro_poblado=p["centro_poblado_display"],
                   quebrada=p["quebrada_display"], lon=lon, lat=lat)
        if hit is None:
            rec.update(uh_relation="FUERA_DE_TODA_UH_DEL_PACIFICO", uh_code=None, uh_name=None)
        else:
            pr = hit["properties"]
            border = dist_to_paths(lon, lat, [ring for poly in polys(hit["geometry"]) for ring in poly])
            rec.update(uh_relation="UH_QUE_CONTIENE_AL_CENTRO_POBLADO", uh_code=pr.get("CODIGO"), uh_name=pr.get("NOMBRE"),
                       uh_area_km2=pr.get("AREA_KM2"), distance_to_uh_boundary_m=round(border),
                       near_boundary=border < BORDER_M)
            per_uh.setdefault(pr.get("CODIGO"), dict(name=pr.get("NOMBRE"), area_km2=pr.get("AREA_KM2"), points=[], departments=set()))
            per_uh[pr.get("CODIGO")]["points"].append(p["id"])
            per_uh[pr.get("CODIGO")]["departments"].add(p["department"])
        if p["department"] in FUNCTIONAL:
            want = norm_name(p["quebrada_display"])
            res = {}
            for src, feats in channels[p["department"]].items():
                if not feats:
                    res[src] = dict(relation="FUENTE_NO_DISPONIBLE")
                    continue
                if p["unnamed_quebrada"] or not want or want in GENERIC:
                    res[src] = dict(relation="QUEBRADA_SIN_NOMBRE_EN_EL_CUADRO")
                    continue
                same = [f for f in feats if f["_name"] and f["_name"] == want and f["_bbox"]]
                if not same:
                    res[src] = dict(relation="SIN_LINEA_OFICIAL_CON_ESE_NOMBRE")
                    continue
                d, f = min((dist_to_paths(lon, lat, lines(f["geometry"])), f) for f in same) if len(same) > 1 else \
                    (dist_to_paths(lon, lat, lines(same[0]["geometry"])), same[0])
                props = f.get("properties") or {}
                res[src] = dict(relation="NOMBRE_COINCIDE_CERCA" if d <= NEAR_M else "NOMBRE_COINCIDE_LEJOS",
                                distance_m=round(d), lines_with_name=len(same),
                                name=props.get("NOMBRE_CA") if src == "ANA" else props.get("NOMBRE"),
                                uh_of_line=props.get("NOMBRE_UH") if src == "ANA" else props.get("CUENCA"),
                                objectid=props.get("OBJECTID_1", props.get("OBJECTID")))
            rec["official_channel_by_name"] = res
        rows.append(rec)

    # IMERG 0.1° cells touching each UH of the functional departments (sub-sampled 5×5 per cell)
    imerg = {}
    for code, u in per_uh.items():
        if not (u["departments"] & set(FUNCTIONAL)):
            continue
        f = next(x for x in uh if x["properties"].get("CODIGO") == code)
        b = f["_bbox"]
        cells, full = 0, 0
        i0, i1 = math.floor(b[0] * 10), math.floor(b[2] * 10)
        j0, j1 = math.floor(b[1] * 10), math.floor(b[3] * 10)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                inside = sum(B.in_geometry((i + (a + .5) / 5) / 10, (j + (c + .5) / 5) / 10, f["geometry"])
                             for a in range(5) for c in range(5))
                if inside:
                    cells += 1
                    full += inside == 25
        imerg[code] = dict(name=u["name"], area_km2=u["area_km2"], imerg_cells_touching=cells, imerg_cells_fully_inside=full)

    summary = {}
    for r in rows:
        s = summary.setdefault(r["department"], dict(admitted=0, in_uh=0, near_boundary=0, outside_uh=0, uh=set()))
        s["admitted"] += 1
        if r["uh_relation"] == "UH_QUE_CONTIENE_AL_CENTRO_POBLADO":
            s["in_uh"] += 1
            s["near_boundary"] += bool(r["near_boundary"])
            s["uh"].add(r["uh_code"])
        else:
            s["outside_uh"] += 1
    for dep in FUNCTIONAL:
        s = summary.get(dep)
        if not s:
            continue
        for src in ("ANA", "IGN"):
            c = {}
            for r in rows:
                if r["department"] == dep:
                    k = r["official_channel_by_name"][src]["relation"]
                    c[k] = c.get(k, 0) + 1
            s[f"channel_by_name_{src}"] = dict(sorted(c.items()))
        s["both_sources_near"] = sum(1 for r in rows if r["department"] == dep and all(
            r["official_channel_by_name"][x]["relation"] == "NOMBRE_COINCIDE_CERCA" for x in ("ANA", "IGN")))
    for s in summary.values():
        s["uh_distinct"] = len(s.pop("uh"))
    uh_table = {k: dict(name=v["name"], area_km2=v["area_km2"], documented_points=len(v["points"]),
                        departments=sorted(v["departments"])) for k, v in sorted(per_uh.items())}
    return dict(schema_version="irfen_v09_hydro_association_v0_1", **GUARDS,
                purpose_es=("Relación territorial entre centros poblados documentados (ANA 2016-2017) y unidades hidrográficas "
                            "oficiales ANA; candidatos de cauce oficial por nombre en Tumbes y Piura. Inferencias de "
                            "investigación: no son conectividad hidráulica, ni huella de inundación, ni prioridad."),
                inputs=dict(points=f"{POINTS.relative_to(ROOT)} sha256 {B.sha(POINTS)}", uh=uh_files,
                            channels=channel_files, provenance=f"{(SRC / 'provenance.json').relative_to(ROOT)}"),
                parameters=dict(border_m=BORDER_M, near_m=NEAR_M, imerg_cell_deg=0.1, imerg_subsample=25,
                                name_rule="nombre normalizado (sin tildes, sin «Quebrada/Qda/Río» ni artículo inicial) idéntico"),
                uh_features=len(uh), summary_by_department=summary, uh_with_documented_points=uh_table,
                imerg_cells_functional_uh=imerg, points=rows)


def dumps(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=0) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = dumps(build())
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    print(json.dumps(d["summary_by_department"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
