#!/usr/bin/env python3
"""Probe exact ANA Rio Tumbes basin layer without promoting geometry.

RESEARCH_ONLY / TEST_ONLY. This probe only verifies that the preregistered
official ANA layer is queryable and returns one polygonal Cuenca Tumbes
feature. It does not write map assets or infer event footprints, capacity,
thresholds, risk, activation, alerts, negatives or travel times.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import unicodedata
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERVICE = "https://geosnirh.ana.gob.pe/server/rest/services/Inundacion_Tumbes/Capas_Inundacion_Tumbes_04052023/MapServer"
LAYER_ID = 2
EXPECTED_NAME = "Cuenca Tumbes"
SOURCE_ID = "ANA-TUMBES-2023-MAPSERVER-BASIN"
SAFE = {
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

class ProbeError(RuntimeError):
    pass

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())

def metadata_url() -> str:
    return f"{SERVICE}/{LAYER_ID}?f=pjson"

def query_url() -> str:
    return f"{SERVICE}/{LAYER_ID}/query?" + urlencode({
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    })

def fetch_json(url: str) -> tuple[dict, bytes]:
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    last = None
    for delay in (0, 5, 15):
        if delay:
            time.sleep(delay)
        try:
            with urlopen(req, timeout=75) as response:
                raw = response.read()
            return json.loads(raw.decode("utf-8")), raw
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = exc
    raise ProbeError(f"ANA_SOURCE_FETCH_FAILED: {last}")

def validate_metadata(metadata: dict) -> str:
    if metadata.get("id") != LAYER_ID:
        raise ProbeError(f"UNEXPECTED_LAYER_ID_{metadata.get('id')}")
    name = str(metadata.get("name") or "")
    if norm(EXPECTED_NAME) not in norm(name):
        raise ProbeError(f"UNEXPECTED_LAYER_NAME_{name}")
    if "query" not in str(metadata.get("capabilities") or "").lower():
        raise ProbeError("ANA_LAYER_NOT_QUERYABLE")
    return name

def validate_feature_collection(fc: dict) -> tuple[int, str]:
    if fc.get("type") != "FeatureCollection":
        raise ProbeError("NOT_FEATURE_COLLECTION")
    features = fc.get("features") or []
    if len(features) != 1:
        raise ProbeError(f"EXPECTED_ONE_BASIN_FEATURE_GOT_{len(features)}")
    geometry = features[0].get("geometry") or {}
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
        raise ProbeError("MISSING_OR_NONPOLYGON_BASIN_GEOMETRY")
    return len(features), geometry_type

def probe() -> dict:
    metadata, metadata_raw = fetch_json(metadata_url())
    layer_name = validate_metadata(metadata)
    fc, source_raw = fetch_json(query_url())
    feature_count, geometry_type = validate_feature_collection(fc)
    return {
        **SAFE,
        "status": "PASS_OFFICIAL_ANA_RIO_TUMBES_BASIN_PROBE",
        "source_id": SOURCE_ID,
        "service": SERVICE,
        "layer_id": LAYER_ID,
        "layer_name": layer_name,
        "query_url": query_url(),
        "feature_count": feature_count,
        "geometry_type": geometry_type,
        "canonical_geojson_sha256": hashlib.sha256(canonical(fc)).hexdigest(),
        "raw_geojson_sha256": hashlib.sha256(source_raw).hexdigest(),
        "raw_metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        "candidate_wide_sampling_ready": False,
        "map_publication_authorized": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    result = probe()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
