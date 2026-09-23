#!/usr/bin/env python3
"""Register Supe-Caleta Vidal discovery and freeze exact ANA Cuenca Supe context.

RESEARCH_ONLY / TEST_ONLY. Caleta Vidal remains a territorial exposure node, never a
basin substitute. The ANA basin polygon is context only and never an event footprint.
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
DISCOVERY_ID = "lima_norte_supe_caleta_vidal"
INVENTORY = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/lima_norte_supe_caleta_vidal.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lima_norte_supe_caleta_vidal.json"
SOURCE = ROOT / "site/data/phase2/sources/north_coast_discovery_geometry/ana_lima_norte_supe_137572.geojson"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_supe_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_supe_geometry_validation.json"
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

DISCOVERY_ROW = {
    "discovery_id": DISCOVERY_ID,
    "system_name": "Cuenca Rio Supe with Caleta Vidal territorial exposure node",
    "department": "Lima",
    "territorial_reference": "Supe lower valley / Caleta Vidal",
    "entity_role": "DISCOVERY_HYDROLOGIC_SYSTEM_WITH_TERRITORIAL_EXPOSURE_NODE",
    "hydrologic_components": [
        "Rio Supe",
        "Caleta Vidal territorial exposure node",
        "irrigation/drainage network as a separate unresolved mechanism"
    ],
    "must_not_merge_with": ["Cuenca Pativilca", "Cuenca Fortaleza"],
    "mechanism_preliminary": "river_flood_irrigation_drainage_pluvial_or_compound_attribution_unresolved",
    "official_evidence_stage": "2017_positive_territorial_impact_and_regulatory_river_context_available_geometry_replay_required",
    "official_source_ids": [
        "ANA-UH-137572-SUPE",
        "INGEMMET-A6789-LIMA-ICA-2017",
        "ANA-SUPE-FAJA-2015-RD2010",
        "ANA-SUPE-FAJA-2019-RD1281",
        "ANA-SUPE-FAJA-2024-RD1166",
        "ANA-SUPE-WATER-QUALITY-2015"
    ],
    "priority_reason": "Caleta Vidal has positive 2017 territorial flood impact evidence within the Supe study corridor, while the exact mechanism remains unresolved and must not be inferred from the basin or faja geometry.",
    "first_work_package": [
        "official Cuenca Supe geometry",
        "1982-83/1997-98/2017/2023 event ledger",
        "Caleta Vidal and lower-valley exposure/connectivity",
        "event-paired rainfall and river observation discovery",
        "faja and river-management context kept separate from event footprint and historical capacity"
    ]
}

class BootstrapError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def validate_guards(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise BootstrapError(f"UNSAFE_{label}_{key}")


def register_inventory(inventory: dict) -> None:
    validate_guards(inventory, "INVENTORY")
    rel = inventory.get("relationship_to_phase2") or {}
    if rel.get("registered_candidate_count_unchanged") != 18:
        raise BootstrapError("PHASE2_REGISTERED_CANDIDATE_COUNT_DRIFT")
    if rel.get("changes_registered_candidate_count") is not False or rel.get("changes_operational_scope") is not False:
        raise BootstrapError("DISCOVERY_EXTENSION_WOULD_CHANGE_OPERATIONAL_SCOPE")
    units = inventory.get("discovery_units")
    if not isinstance(units, list):
        raise BootstrapError("DISCOVERY_UNITS_MISSING")
    declared = rel.get("discovery_units_count")
    if declared != len(units):
        raise BootstrapError(f"DISCOVERY_COUNT_DRIFT declared={declared} actual={len(units)}")
    matches = [row for row in units if row.get("discovery_id") == DISCOVERY_ID]
    if not matches:
        units.append(DISCOVERY_ROW)
        rel["discovery_units_count"] = len(units)
    elif len(matches) != 1 or matches[0] != DISCOVERY_ROW:
        raise BootstrapError("SUPE_DISCOVERY_ROW_DRIFT")


def validate_inputs(contract: dict, package: dict) -> tuple[str, str, dict]:
    validate_guards(contract, "CONTRACT")
    validate_guards(package, "PACKAGE")
    if contract.get("discovery_id") != DISCOVERY_ID or package.get("discovery_id") != DISCOVERY_ID:
        raise BootstrapError("DISCOVERY_ID_MISMATCH")
    cident = contract.get("hydrologic_identity") or {}
    pident = package.get("hydrologic_identity") or {}
    code = str(cident.get("ana_unit_code") or "")
    name = cident.get("ana_unit_name")
    if code != "137572" or name != "Cuenca Supe":
        raise BootstrapError("UNEXPECTED_SUPE_IDENTITY")
    if str(pident.get("ana_unit_code") or "") != code or pident.get("ana_unit_name") != name:
        raise BootstrapError("PACKAGE_CONTRACT_IDENTITY_DRIFT")
    if cident.get("caleta_vidal_is_hydrologic_basin") is not False or pident.get("caleta_vidal_is_hydrologic_basin") is not False:
        raise BootstrapError("CALETA_VIDAL_MUST_REMAIN_EXPOSURE_NODE")
    query = contract.get("source_query") or {}
    pquery = ((package.get("assets") or {}).get("geometry") or {}).get("source_query") or {}
    if query != pquery:
        raise BootstrapError("PACKAGE_CONTRACT_QUERY_DRIFT")
    if query.get("endpoint") != APPROVED_ENDPOINT or query.get("where") != "CODIGO='137572'":
        raise BootstrapError("QUERY_NOT_LOCKED_TO_EXACT_ANA_UNIT")
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
        raise BootstrapError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
    features = source.get("features") or []
    if len(features) != 1:
        raise BootstrapError(f"ANA_EXACT_CODE_NOT_UNIQUE count={len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    got_code = str(props.get("CODIGO") or props.get("codigo") or "")
    got_name = props.get("NOMBRE") or props.get("nombre")
    if got_code != code:
        raise BootstrapError(f"ANA_CODE_MISMATCH expected={code} got={got_code}")
    if got_name != name:
        raise BootstrapError(f"ANA_NAME_MISMATCH expected={name!r} got={got_name!r}")
    geom = feature.get("geometry") or {}
    if geom.get("type") not in {"Polygon", "MultiPolygon"} or not geom.get("coordinates"):
        raise BootstrapError("ANA_GEOMETRY_MISSING_OR_NOT_POLYGON")
    return feature


def normalized(feature: dict, code: str, name: str, source_sha: str) -> dict:
    feature_props = {
        "unit_id": DISCOVERY_ID,
        "name": name,
        "official_unit_code": code,
        "source_id": "ANA-UH-137572-SUPE",
        "source_snapshot_sha256": source_sha,
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "caleta_vidal_is_hydrologic_basin": False,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        **SAFE,
        "alerting_enabled": False,
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "context_only": True,
            "source_id": "ANA-UH-137572-SUPE",
            "source_snapshot_sha256": source_sha,
            "caleta_vidal_is_hydrologic_basin": False,
            "counts_as_event_footprint": False,
        },
        "features": [{"type": "Feature", "properties": feature_props, "geometry": feature["geometry"]}],
    }


def run(refresh_source: bool) -> dict:
    inventory = load(INVENTORY)
    contract = load(CONTRACT)
    package = load(PACKAGE)
    register_inventory(inventory)
    code, name, query = validate_inputs(contract, package)
    if refresh_source:
        source, request_url = fetch_source(query)
        source_sha = dump(SOURCE, source)
    else:
        if not SOURCE.is_file():
            raise BootstrapError("FROZEN_SOURCE_MISSING_USE_REFRESH_SOURCE_ONCE")
        source = load(SOURCE)
        source_sha = digest(SOURCE)
        request_url = None
    feature = validate_source(source, code, name)
    geometry_sha = dump(GEOMETRY, normalized(feature, code, name, source_sha))
    validation = {
        "schema_version": "0.1",
        "discovery_id": DISCOVERY_ID,
        "status": "PASS_OFFICIAL_ANA_SUPE_DISCOVERY_BASIN_GEOMETRY",
        **SAFE,
        "source_id": "ANA-UH-137572-SUPE",
        "ana_unit_code": code,
        "ana_unit_name": name,
        "source_path": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "request_url": request_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat() if refresh_source else None,
        "outcomes_read_for_geometry": False,
        "rainfall_read_for_geometry": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
        "caleta_vidal_used_as_basin": False,
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
    alignment = package.get("inventory_alignment") or {}
    alignment["registration_status"] = "REGISTERED_DISCOVERY_ONLY_NON_OPERATIONAL"
    alignment["operational_candidate_count_change_allowed"] = False
    alignment["next_safe_action"] = "continue mechanism and event-observation QA without promoting discovery maturity"
    package["inventory_alignment"] = alignment
    dump(INVENTORY, inventory)
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
