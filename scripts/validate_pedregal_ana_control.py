#!/usr/bin/env python3
"""Valida el candidato DEM Pedregal contra hitos oficiales ANA de la faja marginal.

La validación solo controla la ubicación del cauce/boca y consistencia interna
DEM. No existe aún un área oficial de microcuenca en esta fuente y por tanto el
resultado NO es production-ready.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json, math

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "site/data/watersheds/chosica_local_candidate_sets.geojson"
OUT = ROOT / "site/data/calibration/pedregal_ana_validation.json"

# ANA RD 2070-2015, anexos 1 y 2 (páginas PDF 4 y 5). Datum WGS84.
# Zona UTM 18S se resuelve por la ubicación de Lurigancho-Chosica.
RIGHT = [
    (314648,8679037),(314494,8679298),(314512,8679357),(314439,8679459),
    (314418,8679562),(314536,8679765),(314544,8679952),(314557,8680063),
    (314581,8680230),(314589,8680328),(314614,8680482),(314657,8680690),
    (314699,8680957),(314694,8681113),(314686,8681240),(314600,8681300),
    (314568,8681398),(314583,8681484),(314559,8681518),(314521,8681582),
    (314448,8681679),
]
LEFT = [
    (314769,8679203),(314621,8679455),(314606,8679654),(314666,8679786),
    (314648,8679988),(314637,8680191),(314647,8680313),(314681,8680378),
    (314736,8680469),(314772,8680672),(314809,8680971),(314807,8681113),
    (314777,8681191),(314754,8681261),(314690,8681354),(314632,8681417),
    (314642,8681488),(314637,8681577),(314605,8681630),(314531,8681732),
]


def point_segment_distance(px, py, ax, ay, bx, by):
    vx, vy = bx-ax, by-ay
    wx, wy = px-ax, py-ay
    denom = vx*vx + vy*vy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (wx*vx + wy*vy)/denom))
    qx, qy = ax+t*vx, ay+t*vy
    return math.hypot(px-qx, py-qy), (qx,qy), t


def main():
    fc = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    feature = next((f for f in fc.get("features", []) if f.get("properties",{}).get("id") == "pedregal_3_8"), None)
    if not feature:
        raise SystemExit("No existe candidato pedregal_3_8")
    p = feature["properties"]
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32718", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True)
    sx, sy = to_utm.transform(float(p["snapped_lon"]), float(p["snapped_lat"]))
    dist, proj, t = point_segment_distance(sx, sy, *RIGHT[0], *LEFT[0])
    mouth_mid = ((RIGHT[0][0]+LEFT[0][0])/2, (RIGHT[0][1]+LEFT[0][1])/2)
    mouth_mid_lonlat = to_wgs.transform(*mouth_mid)
    snap_lonlat = (float(p["snapped_lon"]), float(p["snapped_lat"]))
    acc_area = float(p["accumulation_area_approx_km2"])
    poly_area = float(p["delineated_area_km2"])
    area_internal_error = abs(poly_area-acc_area)/acc_area*100.0 if acc_area else None

    outlet_pass = dist <= 100.0
    internal_area_pass = area_internal_error is not None and area_internal_error <= 10.0
    status = "ANA_CONTROLLED_CANDIDATE" if outlet_pass and internal_area_pass else "REVIEW"

    payload = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "candidate_id": "pedregal_3_8",
        "status": status,
        "scientific_scope": "representative_local_chosica_catchment_candidate",
        "source": {
            "institution": "Autoridad Nacional del Agua (ANA)",
            "resolution": "RD 2070-2015-ANA-AAA.CAÑETE-FORTALEZA",
            "sigrid_document_id": 6066,
            "document_url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/6066",
            "control": "41 hitos WGS84 de faja marginal; 21 margen derecha y 20 izquierda",
        },
        "ana_control": {
            "utm_crs_used": "WGS84 / UTM zone 18S (EPSG:32718)",
            "right_hito_count": len(RIGHT),
            "left_hito_count": len(LEFT),
            "mouth_right_h1_utm": list(RIGHT[0]),
            "mouth_left_h1_utm": list(LEFT[0]),
            "mouth_mid_wgs84": [round(mouth_mid_lonlat[0],7), round(mouth_mid_lonlat[1],7)],
        },
        "dem_candidate": {
            "snapped_outlet_wgs84": list(snap_lonlat),
            "snapped_outlet_utm": [round(sx,2), round(sy,2)],
            "distance_to_ana_mouth_cross_section_m": round(dist,1),
            "projection_fraction_between_h1_markers": round(t,3),
            "accumulation_area_approx_km2": acc_area,
            "delineated_area_km2": poly_area,
            "internal_area_difference_pct": round(area_internal_error,2),
        },
        "gates": {
            "ana_outlet_spatial_control": "PASS" if outlet_pass else "FAIL",
            "dem_internal_area_consistency": "PASS" if internal_area_pass else "FAIL",
            "official_catchment_area_validation": "UNAVAILABLE_IN_THIS_SOURCE",
            "historical_local_rainfall_calibration": "REQUIRED",
        },
        "decision": "Use this polygon for experimental Pedregal rainfall/intensity replay and forecast testing only." if status == "ANA_CONTROLLED_CANDIDATE" else "Do not use until spatial discrepancy is resolved.",
        "warning": "La faja marginal controla el cauce y la boca, no el área total de la microcuenca. Este resultado no habilita alertas de producción.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
