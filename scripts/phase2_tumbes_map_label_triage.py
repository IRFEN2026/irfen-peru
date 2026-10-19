#!/usr/bin/env python3
"""IRFEN — triage of the quebrada labels of the ANA 2016 Tumbes map (SIGRID 3743) that the inventory does not hold.

Documentary QA tool (RESEARCH_ONLY / TEST_ONLY). It does not add any inventory row and creates no geometry.

For every label candidate of config/phase2_inventory_completeness_review_v0_1.json (evidence scale MAP_LABEL_ONLY):
  * locates the label on the archived map page (pdftotext -bbox) and converts its position to an APPROXIMATE
    UTM 17S / WGS84 point with the map's own printed grid (affine fit of the E and N tick labels). The point marks
    where the text is printed, not the channel, outlet or catchment: it is a triage aid, never geometry;
  * validates that georeference against the ANA 2016 table: the numbered point markers (1-44) printed on the map
    are compared with the table's own UTM coordinates;
  * assigns the INEI province (or OUTSIDE_TUMBES) that contains the approximate point;
  * lists possible duplicates: inventory rows of Tumbes whose name is similar (never merged), the nearest ANA 2016
    reference point, and other labels of the same map with a similar name;
  * counts corroboration in a second archived source (INGEMMET A6764 drainage labels).

    python scripts/phase2_tumbes_map_label_triage.py --sources DIR --lanes DIR   # writes the triage ledger
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "config/phase2_inventory_completeness_review_v0_1.json"
OUT = ROOT / "config/phase2_tumbes_map_label_triage_v0_1.json"
MAP = dict(file="raw/sigrid-3743.pdf", sha256="3b63261930a7e908722c8109b4818908e08cdb28591d96edc7a54171d165f8c8")
INGEMMET = dict(file="text/sigrid-3708-ingemmet-a6764-tumbes-2017.pages.json")
PREFIX = ("Q.", "Qda.", "Quebrada")
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, operational_alerting_enabled=False,
              activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False)


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn").lower()).strip()


def norm(s: str) -> str:
    w = re.sub(r"[^a-z0-9 ]+", " ", fold(s)).split()
    return " ".join(x for x in w if x not in ("q", "qda", "quebrada"))


def core(s: str) -> str:
    return " ".join(w for w in norm(s).split() if w not in ("el", "la", "los", "las", "de", "del"))


# ------------------------------------------------------------------ UTM 17S -> WGS84 (inverse transverse Mercator)
def utm17s_to_lonlat(e: float, n: float) -> tuple[float, float]:
    a, f = 6378137.0, 1 / 298.257223563
    k0, e2 = 0.9996, f * (2 - f)
    ep2 = e2 / (1 - e2)
    x, y = e - 500000.0, n - 10000000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu) \
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    c1, t1 = ep2 * math.cos(p1) ** 2, math.tan(p1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                          + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lon) + (-81.0), math.degrees(lat)


def point_in_geom(lon: float, lat: float, geom: dict) -> bool:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"] if geom["type"] == "MultiPolygon" else []
    for poly in polys:
        inside = False
        for ring in poly:  # even-odd over all rings handles holes
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                    inside = not inside
        if inside:
            return True
    return False


# ------------------------------------------------------------------ map page
def words(pdf: Path) -> list[tuple]:
    xml = subprocess.check_output(["pdftotext", "-bbox", str(pdf), "-"]).decode("utf-8")
    return [(float(a), float(b), float(c), float(d), w) for a, b, c, d, w in
            re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', xml)]


def georeference(ws: list[tuple]) -> dict:
    """Least-squares E = a*x + b, N = c*y + d from the printed grid tick labels (text centres)."""
    ex, ny = [], []
    for x0, y0, x1, y1, w in ws:
        if re.fullmatch(r"[5-6]\d0000", w) and y0 > 780:              # bottom E ticks (horizontal text)
            ex.append(((x0 + x1) / 2, float(w)))
        if re.fullmatch(r"9[56]\d0000", w) and x0 < 40:              # left N ticks (vertical text)
            ny.append(((y0 + y1) / 2, float(w)))
    fit = lambda pts: (lambda n, sx, sy, sxx, sxy: ((n * sxy - sx * sy) / (n * sxx - sx * sx), (sy * sxx - sx * sxy) / (n * sxx - sx * sx)))(
        len(pts), sum(p[0] for p in pts), sum(p[1] for p in pts), sum(p[0] ** 2 for p in pts), sum(p[0] * p[1] for p in pts))
    (a, b), (c, d) = fit(ex), fit(ny)
    resid = [abs(a * x + b - e) for x, e in ex] + [abs(c * y + d - n) for y, n in ny]
    return dict(a=a, b=b, c=c, d=d, e_ticks=len(ex), n_ticks=len(ny), max_tick_residual_m=round(max(resid), 1))


def label_positions(pdf: Path) -> list[dict]:
    """Every "Q."/"Qda."/"Quebrada" text run with its printed position (pypdf text matrix: origin and direction of
    the run, converted to the pdftotext page frame, y downwards). The position used is the estimated centre of the
    run along its direction, so curved or rotated labels keep their place."""
    from pypdf import PdfReader

    page = PdfReader(str(pdf)).pages[0]
    height = float(page.mediabox.height)
    out = []

    def visit(text, cm, tm, font_dict, font_size):
        t = " ".join(text.split())
        m = re.match(r"^(?:Q\.|Qda\.|Quebrada)\s*(.+)$", t)
        if not m:
            return
        a, b = tm[0], tm[1]
        size = math.hypot(a, b) or 1.0
        half = len(t) * 0.5 * size / 2  # half the run length, ~0.5 em per character
        x, y = tm[4] + a / size * half, tm[5] + b / size * half
        out.append(dict(label=m.group(1).strip(), x=x, y=height - y))

    page.extract_text(visitor_text=visit)
    return out


def validate_with_table(ws: list[tuple], geo: dict, table_points: list[dict]) -> dict:
    """Numbered point markers on the map vs. the table's own UTM coordinates (same document)."""
    errs = []
    for p in table_points:
        x = (p["e"] - geo["b"]) / geo["a"]
        y = (p["n"] - geo["d"]) / geo["c"]
        cands = [((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in ws if w[4] == str(p["row"]) and 40 < w[0] < 1150 and 40 < w[1] < 800]
        if cands:
            cx, cy = min(cands, key=lambda c: (c[0] - x) ** 2 + (c[1] - y) ** 2)
            errs.append(math.hypot((cx - x) * geo["a"], (cy - y) * geo["c"]))
    errs.sort()
    return dict(points_compared=len(errs), median_error_m=round(errs[len(errs) // 2]) if errs else None,
                p90_error_m=round(errs[int(len(errs) * 0.9)]) if errs else None,
                note="Error between the printed marker number and the table coordinate: it bounds the georeference error, plus the offset of a marker's number from its symbol.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", required=True)
    ap.add_argument("--lanes", required=True)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    src = Path(a.sources)
    pdf = src / MAP["file"]
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != MAP["sha256"]:
        raise SystemExit("SHA-256 mismatch for the archived map")  # fail closed
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    cands = [c for c in review["new_candidates"] if c["evidence_scale"] == "MAP_LABEL_ONLY"]
    # inventory of Tumbes: main plus open lanes (same baseline as the review)
    inv = {r["inventory_id"]: r for r in json.loads((ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json").read_text(encoding="utf-8"))["candidates"]}
    for lane in json.loads((Path(a.lanes) / "lanes.json").read_text(encoding="utf-8")):
        for r in json.loads((Path(a.lanes) / lane["file"]).read_text(encoding="utf-8"))["candidates"]:
            inv.setdefault(r["inventory_id"], r)
    tumbes = [r for r in inv.values() if r["department"] == "Tumbes"]
    table_points = []
    for r in tumbes:
        for e in r["evidence"]:
            pt = e.get("source_reference_point")
            if e.get("table") == "Cuadro 9" and pt:
                table_points.append(dict(row=e["row_number_as_read"], e=pt["easting_m"], n=pt["northing_m"], inventory_id=r["inventory_id"]))
    ws = words(pdf)
    geo = georeference(ws)
    validation = validate_with_table(ws, geo, table_points)
    positions = label_positions(pdf)
    latest = json.loads((ROOT / "data/v09/admin_boundaries/latest.json").read_text(encoding="utf-8"))
    provinces = json.loads((ROOT / latest["path"]).read_text(encoding="utf-8"))["features"]
    # second source: only the drainage labels of the INGEMMET A6764 hazard maps (pages carrying the "Drenaje" legend
    # and the coastline label), not the report prose, so a generic word in a sentence does not count as corroboration
    ing_pages = json.loads((src / INGEMMET["file"]).read_text(encoding="utf-8"))["pages"]
    ing_text = fold(" ".join(t for t in ing_pages if "Drenaje" in t and "Linea de costa" in t))
    names = {r["inventory_id"]: [r["documentary_name"]] + [v["label"] if isinstance(v, dict) else v for v in r.get("name_variants_observed", [])] for r in tumbes}
    label_cores = {c["candidate_id"]: core(c["documentary_label"]) for c in cands}

    rows = []
    for c in cands:
        lab = c["documentary_label"]
        hits = [p for p in positions if norm(p["label"]) == norm(lab)]
        locs = []
        for p in hits:
            e, n = geo["a"] * p["x"] + geo["b"], geo["c"] * p["y"] + geo["d"]
            lon, lat = utm17s_to_lonlat(e, n)
            prov = next((f["properties"]["NOMBDEP"] + " / " + f["properties"]["NOMBPROV"] for f in provinces if point_in_geom(lon, lat, f["geometry"])), "FUERA_DE_LAS_PROVINCIAS_INEI_CARGADAS")
            near = min(table_points, key=lambda t: math.hypot(t["e"] - e, t["n"] - n)) if table_points else None
            locs.append(dict(utm17s_e=round(e), utm17s_n=round(n), lon=round(lon, 5), lat=round(lat, 5), inei_province=prov,
                             nearest_ana2016_point=dict(inventory_id=near["inventory_id"], row=near["row"], distance_m=round(math.hypot(near["e"] - e, near["n"] - n)))
                             if near else None))
        similar_inv = sorted({iid for iid, ns in names.items() for nm in ns
                              if difflib.SequenceMatcher(None, core(lab), core(nm)).ratio() >= 0.8 or (core(lab) and (core(lab) in core(nm).split() or core(nm) == core(lab)))})
        similar_labels = sorted(cid for cid, cl in label_cores.items() if cid != c["candidate_id"] and cl and
                                difflib.SequenceMatcher(None, core(lab), cl).ratio() >= 0.8)
        corroborated = bool(core(lab)) and re.search(r"\b" + re.escape(core(lab)) + r"\b", ing_text) is not None
        outside = locs and all(not l["inei_province"].startswith("TUMBES") for l in locs)
        if not locs:
            cls = "SIN_POSICION_EN_EL_MAPA"
        elif outside:
            cls = "POSIBLEMENTE_FUERA_DE_TUMBES"
        elif similar_inv or similar_labels:
            cls = "POSIBLE_DUPLICADO_POR_ADJUDICAR"
        elif corroborated:
            cls = "CANDIDATO_CORROBORADO_SEGUNDA_FUENTE"
        else:
            cls = "CANDIDATO_SOLO_ROTULO_ANA_2016"
        rows.append(dict(candidate_id=c["candidate_id"], label_as_printed=lab, source_id="ANA-2016-MAPA-TUMBES-SIGRID-3743", source_sha256=MAP["sha256"],
                         occurrences_on_map=len(hits), approximate_label_positions=locs,
                         location_basis="POSICION_APROXIMADA_DEL_ROTULO_EN_EL_MAPA (malla UTM impresa); no es cauce, outlet ni área colectora",
                         possible_duplicates=dict(inventory_rows_similar_name=similar_inv, other_map_labels_similar=similar_labels),
                         corroborated_in_ingemmet_a6764=corroborated, classification=cls,
                         map_block="BLOQUEADO: sin geometría reproducible; la posición del rótulo no es admisible como geometría (catálogo map_semantics)"))
    doc = dict(schema_version="0.1", ledger_id="irfen-phase2-tumbes-map-label-triage:2026-10-14", **GUARDS,
               source=dict(source_id="ANA-2016-MAPA-TUMBES-SIGRID-3743", sha256=MAP["sha256"], archived_file="data/phase2/source_archive/tumbes_capitana_hualaca_higueron/" + MAP["file"]),
               georeference=geo, georeference_validation=validation,
               counts=dict(labels=len(rows), **{k: sum(1 for r in rows if r["classification"] == k) for k in sorted({r["classification"] for r in rows})}),
               rows=rows)
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(georeference=geo, validation=validation, counts=doc["counts"]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
