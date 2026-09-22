#!/usr/bin/env python3
"""Bootstrap official ANA Cuenca Pisco geometry for Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. This bootstrap may only acquire the official ANA
hydrologic-unit polygon named Cuenca Pisco. It does not resolve San Andres
local drainage, event footprints, tributary ravines, outlets, hydraulic
capacity, operational thresholds, negative controls or activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
QUERY_NAME = "Cuenca Pisco"
CANDIDATE_ID = "ica_pisco_san_andres"

GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


def query_url() -> str:
    return BASE + "?" + urlencode({
        "where": f"NOMBRE='{QUERY_NAME}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    })


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate(data: dict) -> dict:
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) != 1:
        raise ValueError("expected exactly one official Cuenca Pisco feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if props.get("NOMBRE") != QUERY_NAME:
        raise ValueError(f"unexpected ANA unit name: {props.get('NOMBRE')!r}")
    code = str(props.get("CODIGO") or "")
    if not code or not code.isdigit():
        raise ValueError("official Cuenca Pisco code missing or non-numeric")
    area = float(props.get("AREA_KM2") or 0)
    if not 4000.0 <= area <= 4400.0:
        raise ValueError(f"official Cuenca Pisco area outside preregistered plausibility band: {area}")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Cuenca Pisco geometry is not polygonal")
    return feature


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--normalized", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    request = Request(query_url(), headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    feature = validate(data)
    canonical_source = canonical(data)
    props = feature["properties"]
    normalized = {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "candidate_id": CANDIDATE_ID,
            "geometry_status": "PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT",
            "source_institution": "Autoridad Nacional del Agua / IDEP",
            "coverage": "Official ANA Cuenca Pisco basin only; San Andres local drainage and tributary ravines remain unresolved and are not polygonized here.",
            "map_disclaimer": "RESEARCH_ONLY basin context; not an event footprint, inundation extent, hydraulic-capacity model, risk level or alert layer.",
        },
        "features": [{
            "type": "Feature",
            "id": "ica_pisco_basin_context",
            "properties": {
                "candidate_id": CANDIDATE_ID,
                "unit_id": "ica_pisco_basin_context",
                "name": "Cuenca Pisco · contexto hidrológico ANA",
                "feature_role": "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT",
                "hydrologic_role": "OFFICIAL_BASIN_BOUNDARY_NOT_EVENT_FOOTPRINT",
                "deployment_status": "RESEARCH_ONLY",
                "test_mode": "TEST_ONLY",
                "review_status": "REVIEW_ONLY",
                "activation_gate": "BLOCKED",
                "production_use": False,
                "production_ready": False,
                "alerting_enabled": False,
                "operational_alerting_enabled": False,
                "loaded_into_operational_calculation": False,
                "carries_alert_values": False,
                "carries_risk_classification": False,
                "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
                "decision_thresholds": None,
                "hydraulic_factors": None,
                "official_hydrologic_unit_code": str(props["CODIGO"]),
                "official_hydrologic_unit_name": props["NOMBRE"],
                "official_area_km2": float(props["AREA_KM2"]),
                "source_crs": "EPSG:4326 requested from ANA IDEP ArcGIS service",
                "geometry_method": "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM",
                "district_boundary_used": False,
                "dem_used": False,
                "outlet_used": False,
                "outlet": None,
                "san_andres_local_drainage_geometry_resolved": False,
                "tributary_ravines_geometry_resolved": False,
                "event_footprint_asserted": False,
                "counts_as_complete_candidate_geometry": False,
                "confidence": "HIGH_OFFICIAL_BASIN_GEOMETRY",
            },
            "geometry": feature["geometry"],
        }],
    }
    manifest = {
        "version": "phase2-pisco-official-basin-bootstrap-v1",
        **GUARDS,
        "candidate_id": CANDIDATE_ID,
        "query_url": query_url(),
        "official_unit_code": str(props["CODIGO"]),
        "official_unit_name": props["NOMBRE"],
        "official_area_km2": float(props["AREA_KM2"]),
        "raw_response_sha256": sha(raw),
        "canonical_source_sha256": sha(canonical_source),
        "normalized_geometry_sha256": sha(canonical(normalized)),
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
        "event_footprint_asserted": False,
        "hydraulic_capacity_inferred": False,
        "negative_control_inferred": False,
    }
    for path, payload in ((args.source, data), (args.normalized, normalized), (args.manifest, manifest)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(payload))
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
