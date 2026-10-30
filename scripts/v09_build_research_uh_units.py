#!/usr/bin/env python3
"""IRFEN v0.9 · unidades de investigación para lluvia IMERG por unidad hidrográfica oficial ANA (Piura y Tumbes).
RESEARCH_ONLY / TEST_ONLY. Sin red.

Entradas: polígonos ANA archivados en #456 (data/v09/sources/ana_hydrographic_units/uh_layer8_pacific_part*.geojson.gz)
y la asociación territorial de centros poblados (data/v09/research/hydro_association_v0_1.json).

Salidas:
* data/v09/research/uh_units_v0_1.geojson — los polígonos tal como los sirve ANA (sin simplificar ni recortar);
* data/v09/research/uh_units_v0_1.json — ficha por unidad: código ANA, superficie (atributo ANA y cálculo esférico),
  cobertura IMERG 0,1°, límite internacional, centros poblados asociados y grado de incertidumbre territorial.

Grado de incertidumbre territorial (regla explícita, sin umbrales de decisión):
* resolución IMERG: SUFICIENTE (≥10 celdas enteras dentro), MARGINAL (1-9), INSUFICIENTE (0);
* ALTA si la resolución es INSUFICIENTE o más del 25 % de sus centros poblados están a < 1 km del límite;
* MEDIA si la resolución es MARGINAL, si la cabecera está fuera del Perú o si algún centro poblado está a < 1 km;
* BAJA en otro caso.

    python scripts/v09_build_research_uh_units.py [--check]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana_hydrographic_units"
ASSOC = ROOT / "data/v09/research/hydro_association_v0_1.json"
OUT_JSON = ROOT / "data/v09/research/uh_units_v0_1.json"
OUT_GEO = ROOT / "data/v09/research/uh_units_v0_1.geojson"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False, used_by_rain_engine_or_priority=False)
# Transboundary Peru–Ecuador basins (Puyango-Tumbes, Zarumilla, Catamayo-Chira): the ANA layer covers only the Peruvian
# part, so rain over the Ecuadorian headwaters is not represented by these polygons.
TRANSBOUNDARY = {
    "1394": "Puyango-Tumbes: cabecera en Ecuador (provincias de El Oro y Loja) no incluida en el polígono ANA",
    "13952": "Zarumilla: parte alta en Ecuador (El Oro) no incluida en el polígono ANA",
    "138": "Catamayo-Chira: cabecera en Ecuador (Loja) no incluida en el polígono ANA",
}
UNITS = [  # (ANA code, class, department(s) of study)
    ("1378", "PRIORITARIA", "PIURA"),
    ("138", "PRIORITARIA", "PIURA"),
    ("13778", "PRIORITARIA", "PIURA / LAMBAYEQUE"),
    ("13779", "PRIORITARIA", "PIURA"),
    ("1394", "EXPLORATORIA", "TUMBES"),
    ("13952", "EXPLORATORIA", "TUMBES"),
    ("13935", "EXPLORATORIA", "TUMBES"),
    ("13939", "EXPLORATORIA", "TUMBES"),
    ("13951", "EXPLORATORIA", "TUMBES"),
    ("13936", "CONTROL_DE_CONSISTENCIA", "TUMBES"),  # same polygon as the archived north zone tumbes_bocapan
]
R_EARTH_KM = 6371.0088


def load_uh() -> dict:
    out = {}
    for p in sorted(SRC.glob("uh_layer8_pacific_part*.geojson.gz")):
        for f in json.loads(gzip.decompress(p.read_bytes()))["features"]:
            out[f["properties"]["CODIGO"]] = f
    return out


def polys(geom: dict) -> list:
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def ring_area_km2(ring: list) -> float:
    """Spherical polygon area (Chamberlain & Duquette 2007), km²."""
    s = 0.0
    for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:] + ring[:1]):
        s += math.radians(x2 - x1) * (2 + math.sin(math.radians(y1)) + math.sin(math.radians(y2)))
    return abs(s) * R_EARTH_KM ** 2 / 2


def area_km2(geom: dict) -> float:
    return sum(ring_area_km2(p[0]) - sum(ring_area_km2(h) for h in p[1:]) for p in polys(geom))


def _in_ring(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(geom, x, y) -> bool:
    return any(_in_ring(x, y, p[0]) and not any(_in_ring(x, y, h) for h in p[1:]) for p in polys(geom))


def bbox(geom) -> list[float]:
    xs = [pt[0] for p in polys(geom) for pt in p[0]]
    ys = [pt[1] for p in polys(geom) for pt in p[0]]
    return [min(xs), min(ys), max(xs), max(ys)]


def imerg_cells(geom, sub: int = 10) -> dict:
    """IMERG 0.1° cells (centres at x.x5) touching the unit, by sub-sampling each cell sub×sub. Fraction of each cell
    inside the unit is reported so partial cells are explicit."""
    b = bbox(geom)
    cells = []
    for i in range(math.floor(b[0] * 10), math.floor(b[2] * 10) + 1):
        for j in range(math.floor(b[1] * 10), math.floor(b[3] * 10) + 1):
            inside = sum(contains(geom, (i + (a + .5) / sub) / 10, (j + (c + .5) / sub) / 10) for a in range(sub) for c in range(sub))
            if inside:
                cells.append(dict(lon_center=round((i + .5) / 10, 2), lat_center=round((j + .5) / 10, 2),
                                  fraction_inside=round(inside / sub ** 2, 2)))
    full = sum(1 for c in cells if c["fraction_inside"] == 1.0)
    return dict(cells_touching=len(cells), cells_fully_inside=full,
                cells_partial=len(cells) - full, equivalent_full_cells=round(sum(c["fraction_inside"] for c in cells), 1),
                resolution=("SUFICIENTE" if full >= 10 else "MARGINAL" if full >= 1 else "INSUFICIENTE"), cells=cells)


def build() -> tuple[dict, dict]:
    uh = load_uh()
    assoc = json.loads(ASSOC.read_text(encoding="utf-8"))
    by_uh = {}
    for p in assoc["points"]:
        if p["uh_relation"] == "UH_QUE_CONTIENE_AL_CENTRO_POBLADO":
            by_uh.setdefault(p["uh_code"], []).append(p)
    units, feats = [], []
    for code, cls, deps in UNITS:
        f = uh[code]
        pr = f["properties"]
        pts = sorted(by_uh.get(code, []), key=lambda p: p["id"])
        near = [p for p in pts if p["near_boundary"]]
        cells = imerg_cells(f["geometry"])
        share_near = (len(near) / len(pts)) if pts else 0.0
        if cells["resolution"] == "INSUFICIENTE" or share_near > 0.25:
            grade = "ALTA"
        elif cells["resolution"] == "MARGINAL" or code in TRANSBOUNDARY or near:
            grade = "MEDIA"
        else:
            grade = "BAJA"
        reasons = []
        if cells["resolution"] != "SUFICIENTE":
            reasons.append(f"RESOLUCION_IMERG_{cells['resolution']} ({cells['cells_fully_inside']} celdas enteras de 0,1°)")
        if code in TRANSBOUNDARY:
            reasons.append("CABECERA_FUERA_DE_PERU_NO_REPRESENTADA")
        if near:
            reasons.append(f"CENTROS_POBLADOS_CERCA_DEL_LIMITE ({len(near)} de {len(pts)} a < 1 km)")
        if not pts:
            reasons.append("SIN_CENTROS_POBLADOS_ANA_2016_17_DENTRO")
        units.append(dict(
            code=code, name=pr["NOMBRE"], study_class=cls, departments=deps,
            pfafstetter_levels={k: pr[k].strip() for k in ("NIVEL1", "NIVEL2", "NIVEL3", "NIVEL4", "NIVEL5", "NIVEL6", "NIVEL7") if pr[k].strip()},
            area_km2_ana=pr["AREA_KM2"], area_km2_spherical=round(area_km2(f["geometry"]), 1), bbox=[round(x, 4) for x in bbox(f["geometry"])],
            geometry_vertices=sum(len(r) for p in polys(f["geometry"]) for r in p),
            international_boundary=dict(headwaters_outside_peru=code in TRANSBOUNDARY, note=TRANSBOUNDARY.get(code)),
            imerg=cells,
            settlements=dict(count=len(pts), near_uh_boundary=len(near), share_near_boundary=round(share_near, 2),
                             relation="UH_QUE_CONTIENE_AL_CENTRO_POBLADO (pertenencia espacial, no causalidad hidráulica)",
                             points=[dict(id=p["id"], name=p["centro_poblado"], quebrada=p["quebrada"], lon=p["lon"], lat=p["lat"],
                                          distance_to_uh_boundary_m=p["distance_to_uh_boundary_m"], near_boundary=p["near_boundary"])
                                     for p in pts]),
            territorial_uncertainty=dict(grade=grade, reasons=reasons)))
        feats.append(dict(type="Feature", properties=dict(code=code, name=pr["NOMBRE"], study_class=cls,
                                                          source="ANA / IDEP ANA_WMS MapServer 8 (archivo #456)"),
                          geometry=f["geometry"]))
    doc = dict(schema_version="irfen_v09_research_uh_units_v0_1", **GUARDS,
               purpose_es=("Unidades hidrográficas oficiales ANA usadas como zonas de investigación para lluvia IMERG. "
                           "No sustituyen las zonas de vigilancia del motor ni entran en la prioridad."),
               source="data/v09/sources/ana_hydrographic_units (ANA / IDEP, capa 8, captura del 30-10-2026, #456)",
               uncertainty_rule=("ALTA: resolución IMERG INSUFICIENTE o > 25 % de centros poblados a < 1 km del límite; "
                                 "MEDIA: resolución MARGINAL, cabecera fuera del Perú o algún centro poblado a < 1 km; BAJA: resto."),
               units=units)
    geo = dict(type="FeatureCollection", features=feats)
    return doc, geo


def dumps(doc) -> str:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc, geo = build()
    texts = {OUT_JSON: json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n", OUT_GEO: dumps(geo)}
    if a.check:
        same = all(p.is_file() and p.read_text(encoding="utf-8") == t for p, t in texts.items())
        print("OK" if same else "FAIL")
        return 0 if same else 1
    for p, t in texts.items():
        p.write_text(t, encoding="utf-8")
    for u in doc["units"]:
        print(u["code"], u["name"], u["study_class"], u["area_km2_ana"], u["area_km2_spherical"], u["imerg"]["cells_touching"],
              u["imerg"]["cells_fully_inside"], u["imerg"]["resolution"], u["settlements"]["count"], u["settlements"]["near_uh_boundary"],
              u["territorial_uncertainty"]["grade"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
