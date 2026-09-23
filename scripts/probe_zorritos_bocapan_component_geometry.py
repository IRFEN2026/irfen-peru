#!/usr/bin/env python3
"""Freeze the official ANA Bocapan hydrographic unit as one child of Zorritos-Bocapan.

RESEARCH_ONLY / TEST_ONLY. The territorial parent remains unmapped and no sibling
ravine geometry, event outcome, rainfall, hydraulic capacity, threshold or negative
control is inferred by this script.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/tumbes_zorritos_bocapan_coastal_ravines.json"
SOURCE = ROOT / "site/data/phase2/sources/north_coast_discovery_geometry/ana_tumbes_zorritos_bocapan_coastal_ravines_bocapan_casitas_13936.geojson"
GEOMETRY = ROOT / "site/data/phase2/geometries/tumbes_bocapan_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/tumbes_bocapan_basin_context_validation.json"
ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
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


def digest_bytes(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value)
    path.write_bytes(raw)
    return digest_bytes(raw)


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


def component(contract: dict) -> dict:
    for key, expected in SAFE.items():
        if contract.get(key) != expected:
            raise ProbeError(f"UNSAFE_CONTRACT_{key}")
    if contract.get("discovery_id") != "tumbes_zorritos_bocapan_coastal_ravines":
        raise ProbeError("DISCOVERY_ID_MISMATCH")
    policy = contract.get("component_policy") or {}
    required = {
        "parent_is_hydrologic_basin": False,
        "parent_is_map_polygon": False,
        "components_must_remain_separate": True,
        "composite_union_forbidden": True,
        "territorial_reference_is_basin": False,
    }
    for key, expected in required.items():
        if policy.get(key) != expected:
            raise ProbeError(f"UNSAFE_COMPONENT_POLICY_{key}")
    parent = ((contract.get("assets") or {}).get("geometry") or {})
    if parent.get("path") is not None or not str(parent.get("status", "")).startswith("MISSING_PARENT_GROUPER"):
        raise ProbeError("PARENT_SYNTHETIC_GEOMETRY_FORBIDDEN")
    components = ((contract.get("assets") or {}).get("geometry_components") or [])
    if len(components) != 1:
        raise ProbeError("BOCAPAN_CONTRACT_REQUIRES_EXACTLY_ONE_RESOLVED_CHILD")
    item = components[0]
    if item.get("component_id") != "bocapan_casitas":
        raise ProbeError("UNEXPECTED_COMPONENT")
    identity = item.get("hydrologic_identity") or {}
    if str(identity.get("ana_unit_code") or "") != "13936":
        raise ProbeError("UNEXPECTED_ANA_CODE")
    if norm(identity.get("ana_unit_name")) != "cuenca bocapan":
        raise ProbeError("UNEXPECTED_ANA_NAME")
    query = item.get("source_query") or {}
    if query.get("endpoint") != ENDPOINT or query.get("where") != "CODIGO='13936'":
        raise ProbeError("SOURCE_QUERY_NOT_FROZEN")
    geometry = item.get("geometry") or {}
    if geometry.get("path") != GEOMETRY.relative_to(ROOT).as_posix():
        raise ProbeError("UNEXPECTED_GEOMETRY_PATH")
    if geometry.get("counts_as_operational_geometry") is not False or geometry.get("counts_as_event_footprint") is not False:
        raise ProbeError("UNSAFE_GEOMETRY_ROLE")
    return item


def fetch_source(item: dict) -> dict:
    query = item["source_query"]
    url = query["endpoint"] + "?" + urlencode({
        "where": query["where"],
        "outFields": query.get("out_fields", "*"),
        "returnGeometry": "true",
        "outSR": str(query.get("out_sr", 4326)),
        "geometryPrecision": str(query.get("geometry_precision", 7)),
        "f": query.get("format", "geojson"),
    })
    with urlopen(Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"}), timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_source(source: dict) -> dict:
    if source.get("type") != "FeatureCollection":
        raise ProbeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
    features = source.get("features") or []
    if len(features) != 1:
        raise ProbeError(f"ANA_EXACT_CODE_NOT_UNIQUE_{len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    code = str(props.get("CODIGO") or props.get("codigo") or "")
    name = props.get("NOMBRE") or props.get("nombre")
    if code != "13936":
        raise ProbeError(f"ANA_CODE_MISMATCH_{code}")
    if norm(name) != "cuenca bocapan":
        raise ProbeError(f"ANA_NAME_MISMATCH_{name}")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
        raise ProbeError("ANA_GEOMETRY_MISSING_OR_INVALID")
    return feature


def normalized(feature: dict, source_sha: str) -> dict:
    props = {
        "unit_id": "tumbes_zorritos_bocapan_coastal_ravines__bocapan_casitas",
        "parent_discovery_id": "tumbes_zorritos_bocapan_coastal_ravines",
        "component_id": "bocapan_casitas",
        "name": "Cuenca Bocapán",
        "official_unit_code": "13936",
        "source_id": "ANA-UH-13936-BOCAPAN",
        "source_snapshot_sha256": source_sha,
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "alerting_enabled": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "confidence": "HIGH_OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "context_only": True,
            "parent_discovery_id": "tumbes_zorritos_bocapan_coastal_ravines",
            "source_id": "ANA-UH-13936-BOCAPAN",
            "map_disclaimer": "RESEARCH_ONLY official Bocapan basin context; not event footprint, risk, alert, threshold or hydraulic capacity. Other Zorritos ravines remain separate and unresolved.",
        },
        "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
    }


def derive(contract: dict, source: dict) -> tuple[dict, dict, dict]:
    item = component(contract)
    feature = validate_source(source)
    source_sha = digest_bytes(canonical(source))
    geo = normalized(feature, source_sha)
    geometry_sha = digest_bytes(canonical(geo))
    validation = {
        "schema_version": "0.1",
        **SAFE,
        "status": "PASS_OFFICIAL_ANA_DISCOVERY_COMPONENT_GEOMETRY",
        "parent_discovery_id": "tumbes_zorritos_bocapan_coastal_ravines",
        "component_id": "bocapan_casitas",
        "source_id": "ANA-UH-13936-BOCAPAN",
        "ana_unit_code": "13936",
        "ana_unit_name": "Cuenca Bocapán",
        "source_path": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "outcomes_read": False,
        "rainfall_read": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "composite_geometry_created": False,
        "sibling_ravine_geometry_inferred": False,
    }
    validation_sha = digest_bytes(canonical(validation))
    asset = item["geometry"]
    asset["status"] = "PARTIAL_OFFICIAL_BASIN_CONTEXT"
    asset["sha256"] = geometry_sha
    asset["validation_path"] = VALIDATION.relative_to(ROOT).as_posix()
    asset["validation_sha256"] = validation_sha
    contract["contract_status"] = "DISCOVERY_CHILD_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"
    return contract, geo, validation


def run(refresh: bool, check_only: bool) -> None:
    contract = load(CONTRACT)
    item = component(contract)
    if refresh:
        source = fetch_source(item)
        validate_source(source)
        write(SOURCE, source)
    if not SOURCE.is_file():
        raise ProbeError("FROZEN_ANA_SOURCE_MISSING")
    source = load(SOURCE)
    updated, geo, validation = derive(contract, source)
    expected = ((CONTRACT, updated), (GEOMETRY, geo), (VALIDATION, validation))
    if check_only:
        for path, value in expected:
            if not path.is_file() or path.read_bytes() != canonical(value):
                raise ProbeError(f"STALE_OR_MISSING_DERIVED_ARTIFACT_{path.relative_to(ROOT)}")
        return
    for path, value in expected:
        write(path, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source and args.check_only:
        raise ProbeError("REFRESH_AND_CHECK_ONLY_ARE_MUTUALLY_EXCLUSIVE")
    run(args.refresh_source, args.check_only)
    print(json.dumps({
        "status": "PASS_ZORRITOS_BOCAPAN_COMPONENT_GEOMETRY",
        "component_id": "bocapan_casitas",
        "activation_gate": "BLOCKED",
        "production_use": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
