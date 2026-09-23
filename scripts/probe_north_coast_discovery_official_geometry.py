#!/usr/bin/env python3
"""Fetch and freeze official ANA basin geometry for bounded Phase-2 discovery units.

This script is geometry/identity only. It reads no event outcomes, rainfall, hydraulic
capacity, thresholds or negative controls. Every target must have an explicit discovery
contract and exact ANA unit code/name; mismatches fail closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "site/data/validation/phase2_discovery_contracts"
GEOM_DIR = ROOT / "site/data/phase2/geometries"
SOURCE_ROOT = ROOT / "site/data/phase2/sources/north_coast_discovery_geometry"

TARGETS = {
    "lima_norte_pativilca": {
        "contract": CONTRACT_DIR / "lima_norte_pativilca.json",
        "source": SOURCE_ROOT / "ana_cuenca_pativilca_13758.geojson",
        "geometry": GEOM_DIR / "lima_norte_pativilca_basin_context.geojson",
        "validation": GEOM_DIR / "lima_norte_pativilca_geometry_validation.json",
    },
    "lima_norte_fortaleza_paramonga": {
        "contract": CONTRACT_DIR / "lima_norte_fortaleza_paramonga.json",
        "source": SOURCE_ROOT / "ana_cuenca_fortaleza_137592.geojson",
        "geometry": GEOM_DIR / "lima_norte_fortaleza_basin_context.geojson",
        "validation": GEOM_DIR / "lima_norte_fortaleza_geometry_validation.json",
    },
}

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

class GeometryProbeError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return digest_bytes(raw)


def validate_contract(contract: dict, discovery_id: str) -> tuple[str, str]:
    if contract.get("discovery_id") != discovery_id:
        raise GeometryProbeError("DISCOVERY_ID_MISMATCH")
    for key, expected in SAFE.items():
        if key == "alerting_enabled":
            continue
        if contract.get(key) != expected:
            raise GeometryProbeError(f"UNSAFE_CONTRACT_{key}")
    identity = contract.get("hydrologic_identity") or {}
    code = str(identity.get("ana_unit_code") or "")
    name = identity.get("ana_unit_name")
    if not code or not isinstance(name, str) or not name:
        raise GeometryProbeError("MISSING_EXACT_ANA_IDENTITY")
    if identity.get("territorial_reference_is_basin") is not False:
        raise GeometryProbeError("TERRITORIAL_REFERENCE_MUST_NOT_BE_BASIN")
    query = contract.get("source_query") or {}
    if query.get("where") != f"CODIGO='{code}'":
        raise GeometryProbeError("QUERY_NOT_LOCKED_TO_EXACT_CODE")
    if query.get("endpoint") != "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query":
        raise GeometryProbeError("UNAPPROVED_GEOMETRY_ENDPOINT")
    return code, name


def fetch_source(contract: dict) -> tuple[dict, str]:
    query = contract["source_query"]
    params = {
        "where": query["where"],
        "outFields": query.get("out_fields", "*"),
        "returnGeometry": "true",
        "outSR": str(query.get("out_sr", 4326)),
        "geometryPrecision": str(query.get("geometry_precision", 7)),
        "f": query.get("format", "geojson"),
    }
    url = query["endpoint"] + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    with urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data, url


def validate_source(source: dict, code: str, name: str) -> dict:
    if source.get("type") != "FeatureCollection":
        raise GeometryProbeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
    features = source.get("features") or []
    if len(features) != 1:
        raise GeometryProbeError(f"ANA_EXACT_CODE_NOT_UNIQUE count={len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    got_code = str(props.get("CODIGO") or props.get("codigo") or "")
    got_name = props.get("NOMBRE") or props.get("nombre")
    if got_code != code:
        raise GeometryProbeError(f"ANA_CODE_MISMATCH expected={code} got={got_code}")
    if got_name != name:
        raise GeometryProbeError(f"ANA_NAME_MISMATCH expected={name!r} got={got_name!r}")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
        raise GeometryProbeError("ANA_GEOMETRY_MISSING_OR_NOT_POLYGON")
    return feature


def normalize(feature: dict, discovery_id: str, code: str, name: str, source_id: str) -> dict:
    props = {
        "unit_id": discovery_id,
        "name": name,
        "official_unit_code": code,
        "source_id": source_id,
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        **SAFE,
    }
    return {
        "type": "FeatureCollection",
        "properties": {**SAFE, "context_only": True, "source_id": source_id},
        "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
    }


def run_target(discovery_id: str, refresh_source: bool) -> dict:
    cfg = TARGETS[discovery_id]
    contract = load(cfg["contract"])
    code, name = validate_contract(contract, discovery_id)
    if refresh_source:
        source, request_url = fetch_source(contract)
        source_sha = dump(cfg["source"], source)
    else:
        if not cfg["source"].is_file():
            raise GeometryProbeError("FROZEN_SOURCE_MISSING_USE_REFRESH_SOURCE_ONCE")
        source = load(cfg["source"])
        request_url = None
        source_sha = sha256(cfg["source"].read_bytes()).hexdigest()
    feature = validate_source(source, code, name)
    source_ids = contract.get("official_source_ids") or []
    if len(source_ids) != 1:
        raise GeometryProbeError("EXACTLY_ONE_GEOMETRY_SOURCE_ID_REQUIRED")
    normalized = normalize(feature, discovery_id, code, name, source_ids[0])
    geometry_sha = dump(cfg["geometry"], normalized)
    validation = {
        "schema_version": "0.1",
        "discovery_id": discovery_id,
        "status": "PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY",
        **{k: v for k, v in SAFE.items() if k != "alerting_enabled"},
        "source_id": source_ids[0],
        "ana_unit_code": code,
        "ana_unit_name": name,
        "source_path": cfg["source"].relative_to(ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": cfg["geometry"].relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "request_url": request_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat() if refresh_source else None,
        "outcomes_read": False,
        "rainfall_read": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "approximate_geometry_used": False,
    }
    validation_sha = dump(cfg["validation"], validation)
    asset = contract["assets"]["geometry"]
    asset["status"] = "PARTIAL_OFFICIAL_BASIN_CONTEXT"
    asset["sha256"] = geometry_sha
    asset["validation_path"] = cfg["validation"].relative_to(ROOT).as_posix()
    asset["validation_sha256"] = validation_sha
    contract["contract_status"] = "DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"
    dump(cfg["contract"], contract)
    return validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), action="append", required=True)
    parser.add_argument("--refresh-source", action="store_true")
    args = parser.parse_args()
    results = [run_target(target, args.refresh_source) for target in args.target]
    print(json.dumps({"status": "PASS", "targets": [r["discovery_id"] for r in results]}, sort_keys=True))

if __name__ == "__main__":
    main()
