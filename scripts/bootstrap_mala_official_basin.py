#!/usr/bin/env python3
"""Bootstrap official ANA Cuenca Mala geometry for Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. This script acquires only the official ANA hydrologic
unit named Cuenca Mala. It must not infer tributary ravines, event footprints,
outlets, negative controls, hydraulic capacity, thresholds, risk or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
QUERY_NAME = "Cuenca Mala"
CANDIDATE_ID = "lima_sur_mala"

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
        raise ValueError("expected exactly one official Cuenca Mala feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if props.get("NOMBRE") != QUERY_NAME:
        raise ValueError(f"unexpected ANA unit name: {props.get('NOMBRE')!r}")
    code = str(props.get("CODIGO") or "")
    if not code or not code.isdigit():
        raise ValueError("official Cuenca Mala code missing or non-numeric")
    area = float(props.get("AREA_KM2") or 0)
    if not 2200.0 <= area <= 2450.0:
        raise ValueError(f"official Cuenca Mala area outside bounded reasonableness band: {area}")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Cuenca Mala geometry is not polygonal")
    return feature


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    request = Request(query_url(), headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    feature = validate(data)
    props = feature["properties"]
    canonical_source = canonical(data)
    manifest = {
        "version": "phase2-mala-official-basin-bootstrap-v1",
        **GUARDS,
        "candidate_id": CANDIDATE_ID,
        "query_url": query_url(),
        "official_unit_code": str(props["CODIGO"]),
        "official_unit_name": props["NOMBRE"],
        "official_area_km2": float(props["AREA_KM2"]),
        "geometry_type": feature["geometry"]["type"],
        "raw_response_sha256": sha(raw),
        "canonical_source_sha256": sha(canonical_source),
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
        "event_footprint_asserted": False,
        "hydraulic_capacity_inferred": False,
        "negative_control_inferred": False,
    }
    for path, payload in ((args.source, data), (args.manifest, manifest)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(payload))
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
