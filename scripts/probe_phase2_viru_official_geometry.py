#!/usr/bin/env python3
"""Freeze exact official ANA Cuenca Viru geometry for discovery use only.

RESEARCH_ONLY / TEST_ONLY. This script reads hydrologic identity and official geometry
only. It does not read outcomes, rainfall, hydraulic capacity, thresholds or controls.
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
DISCOVERY_ID = "lalibertad_viru"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/lalibertad_viru.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_viru.json"
SOURCE = ROOT / "site/data/phase2/sources/north_coast_discovery_geometry/ana_lalibertad_viru_137714.geojson"
GEOMETRY = ROOT / "site/data/phase2/geometries/lalibertad_viru_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lalibertad_viru_geometry_validation.json"
APPROVED_ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"

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


def validate_guards(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise ProbeError(f"UNSAFE_{label}_{key}")


def validate_inputs(contract: dict, package: dict) -> tuple[str, str, dict]:
    validate_guards(contract, "CONTRACT")
    validate_guards(package, "PACKAGE")
    if contract.get("discovery_id") != DISCOVERY_ID or package.get("discovery_id") != DISCOVERY_ID:
        raise ProbeError("DISCOVERY_ID_MISMATCH")
    cident = contract.get("hydrologic_identity") or {}
    pident = package.get("hydrologic_identity") or {}
    code = str(cident.get("ana_unit_code") or "")
    name = cident.get("ana_unit_name")
    if code != "137714" or name != "Cuenca Viru":
        raise ProbeError("UNEXPECTED_VIRU_IDENTITY")
    if str(pident.get("ana_unit_code") or "") != code or pident.get("ana_unit_name") != name:
        raise ProbeError("PACKAGE_CONTRACT_IDENTITY_DRIFT")
    if cident.get("territorial_reference_is_basin") is not False or pident.get("territorial_reference_is_basin") is not False:
        raise ProbeError("TERRITORIAL_REFERENCE_MUST_NOT_BE_BASIN")
    query = contract.get("source_query") or {}
    pquery = ((package.get("assets") or {}).get("geometry") or {}).get("source_query") or {}
    if query != pquery:
        raise ProbeError("PACKAGE_CONTRACT_QUERY_DRIFT")
    if query.get("endpoint") != APPROVED_ENDPOINT or query.get("where") != "CODIGO='137714'":
        raise ProbeError("QUERY_NOT_LOCKED_TO_EXACT_ANA_UNIT")
    cg = ((contract.get("assets") or {}).get("geometry") or {})
    pg = ((package.get("assets") or {}).get("geometry") or {})
    for label, geom in (("CONTRACT", cg), ("PACKAGE", pg)):
        if geom.get("path") != GEOMETRY.relative_to(ROOT).as_posix():
            raise ProbeError(f"UNEXPECTED_{label}_GEOMETRY_PATH")
        if geom.get("counts_as_operational_geometry") is not False or geom.get("counts_as_event_footprint") is not False:
            raise ProbeError(f"UNSAFE_{label}_GEOMETRY_ROLE")
    return code, name, query


def fetch_source(query: dict) -> tuple[dict, str]:
    params = {
        "where": query["where"],
        "outFields": query.get("out_fields", "*"),
        "returnGeometry": "true",
        "outSR": str(query.get("out_sr", 4326)),
        "geometryPrecision": str(query.get("geometry_precision", 7)),
        "f": query.get("format", "geojson"),
    }
    url = query["endpoint"] + "?" + urlencode(params)
    with urlopen(Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"}), timeout=90) as response:
        return json.loads(response.read().decode("utf-8")), url


def validate_source(source: dict, code: str, name: str) -> dict:
    if source.get("type") != "FeatureCollection":
        raise ProbeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
    features = source.get("features") or []
    if len(features) != 1:
        raise ProbeError(f"ANA_EXACT_CODE_NOT_UNIQUE count={len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    got_code = str(props.get("CODIGO") or props.get("codigo") or "")
    got_name = props.get("NOMBRE") or props.get("nombre")
    if got_code != code:
        raise ProbeError(f"ANA_CODE_MISMATCH expected={code} got={got_code}")
    if got_name != name:
        raise ProbeError(f"ANA_NAME_MISMATCH expected={name!r} got={got_name!r}")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
        raise ProbeError("ANA_GEOMETRY_MISSING_OR_NOT_POLYGON")
    return feature


def normalized(feature: dict, code: str, name: str, source_hash: str) -> dict:
    props = {
        "unit_id": DISCOVERY_ID,
        "name": name,
        "official_unit_code": code,
        "source_id": "ANA-UH-137714-VIRU",
        "source_snapshot_sha256": source_hash,
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            "deployment_status": "RESEARCH_ONLY",
            "test_mode": "TEST_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "decision_thresholds": None,
            "hydraulic_factors": None,
            "context_only": True,
            "source_id": "ANA-UH-137714-VIRU",
            "source_snapshot_sha256": source_hash,
        },
        "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
    }


def run(refresh_source: bool) -> dict:
    contract = load(CONTRACT)
    package = load(PACKAGE)
    code, name, query = validate_inputs(contract, package)
    if refresh_source:
        source, request_url = fetch_source(query)
        source_sha = dump(SOURCE, source)
    else:
        if not SOURCE.is_file():
            raise ProbeError("FROZEN_SOURCE_MISSING_USE_REFRESH_SOURCE_ONCE")
        source = load(SOURCE)
        source_sha = sha256(SOURCE.read_bytes()).hexdigest()
        request_url = None
    feature = validate_source(source, code, name)
    geometry = normalized(feature, code, name, source_sha)
    geometry_sha = dump(GEOMETRY, geometry)
    validation = {
        "schema_version": "0.1",
        "discovery_id": DISCOVERY_ID,
        "status": "PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY",
        **SAFE,
        "source_id": "ANA-UH-137714-VIRU",
        "ana_unit_code": code,
        "ana_unit_name": name,
        "source_path": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "request_url": request_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat() if refresh_source else None,
        "outcomes_read": False,
        "rainfall_read": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
    }
    validation_sha = dump(VALIDATION, validation)
    for obj in (contract, package):
        asset = obj["assets"]["geometry"]
        asset["status"] = "PARTIAL_OFFICIAL_BASIN_CONTEXT"
        asset["representation"] = "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
        asset["sha256"] = geometry_sha
        asset["validation_path"] = VALIDATION.relative_to(ROOT).as_posix()
        asset["validation_sha256"] = validation_sha
        asset["source_path"] = SOURCE.relative_to(ROOT).as_posix()
        asset["source_sha256"] = source_sha
    contract["contract_status"] = "DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"
    package["contract_status"] = "DISCOVERY_HYDROLOGIC_IDENTITY_AND_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"
    package["geometry_contract_path"] = CONTRACT.relative_to(ROOT).as_posix()
    dump(CONTRACT, contract)
    dump(PACKAGE, package)
    return validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    args = parser.parse_args()
    result = run(args.refresh_source)
    print(json.dumps({"status": result["status"], "discovery_id": DISCOVERY_ID}, sort_keys=True))

if __name__ == "__main__":
    main()
