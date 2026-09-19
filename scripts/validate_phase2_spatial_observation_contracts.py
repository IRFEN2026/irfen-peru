#!/usr/bin/env python3
"""Validate Claude F Phase-2 Spatial Observation Contracts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
SCHEMA = ROOT / "config/phase2_spatial_observation_contracts.schema.json"
INVENTORY = ROOT / "config/phase2_candidate_inventory_v0_2.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
SANTA_GEOM = ROOT / "site/data/phase2/geometries/w1_santa_eulalia_rimac.geojson"
LURIN_GEOM = ROOT / "site/data/validation/phase2_research_evidence/ana_lurin_faja_marginal_antioquia_2025.geojson"

SANTA_ID = "lima_este_santa_eulalia_rimac"
LURIN_ID = "lima_este_lurin_cieneguilla"
EXPECTED_SUBUNITS = {
    "cashahuacra": {
        "geometry_type": "Polygon",
        "geometry_sha256": "edcad38438dff974befc4dda7993dee088c19367dc488c297f5f4e67e6eb0ee6",
        "area_km2": 15.088,
    },
    "shingolay": {
        "geometry_type": "MultiPolygon",
        "geometry_sha256": "df0e0594bc491f00968a4d314aa6fc03deee4bcaacce3842a1ebcbbbed145553",
        "area_km2": 0.243,
    },
}
ERRORS = []


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"cannot read {path.relative_to(ROOT)}: {exc}")
        return None


def check_schema(result, schema):
    try:
        import jsonschema
    except ImportError:
        return
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(result), key=str):
        ERRORS.append(
            "schema: " + error.message + " at " + "/".join(str(x) for x in error.absolute_path)
        )


def check_phase2_guardrails(inventory, catalog):
    candidates = inventory.get("candidates") or []
    zones = catalog.get("zones") or []
    if len(candidates) != 18 or len(zones) != 18:
        ERRORS.append(
            f"Phase-2 count changed: inventory={len(candidates)} catalog={len(zones)}"
        )
    if (catalog.get("summary") or {}).get("contracts_approved") != 0:
        ERRORS.append("contracts_approved must remain 0")
    if (catalog.get("summary") or {}).get("operational_candidates") != 0:
        ERRORS.append("operational_candidates must remain 0")
    if any(zone.get("activation_gate") != "BLOCKED" for zone in zones):
        ERRORS.append("all activation gates must remain BLOCKED")
    if any((zone.get("promotion_gate") or {}).get("promotion_gate_met") is True for zone in zones):
        ERRORS.append("no promotion gate may be met")
    if catalog.get("deployment_status") != "RESEARCH_ONLY":
        ERRORS.append("catalog must remain RESEARCH_ONLY")
    if catalog.get("production_use") is not False or catalog.get("production_ready") is not False:
        ERRORS.append("catalog production flags changed")
    if (catalog.get("guardrails") or {}).get("alerts_disabled") is not True:
        ERRORS.append("catalog alerts_disabled guardrail changed")


def check_authoritative_geometry_state(catalog):
    zones = {zone["candidate_id"]: zone for zone in catalog.get("zones") or []}
    present = {
        cid
        for cid, zone in zones.items()
        if ((zone.get("asset_readiness") or {}).get("geometry") or {}).get("data_presence")
        == "PRESENT"
    }
    if present != {SANTA_ID, LURIN_ID}:
        ERRORS.append(f"geometry PRESENT set changed: {sorted(present)}")

    ready = {
        cid
        for cid, zone in zones.items()
        if (zone.get("asset_status") or {}).get("geometry") == "READY"
    }
    if ready:
        ERRORS.append(
            f"candidate-wide geometry READY state changed and requires review: {sorted(ready)}"
        )

    for cid in (SANTA_ID, LURIN_ID):
        if (zones.get(cid, {}).get("asset_status") or {}).get("geometry") != "PARTIAL":
            ERRORS.append(f"{cid}: expected geometry asset status PARTIAL")

    malanche = zones.get("lima_sur_malanche") or {}
    if (malanche.get("asset_status") or {}).get("geometry") != "PARTIAL":
        ERRORS.append("lima_sur_malanche: expected PARTIAL geometry asset status")
    if ((malanche.get("asset_readiness") or {}).get("geometry") or {}).get("data_presence") != "MISSING":
        ERRORS.append("lima_sur_malanche: PARTIAL label must not be treated as file presence")


def check_santa_geometry():
    data = load(SANTA_GEOM)
    if data is None:
        return
    features = data.get("features") or []
    by_unit = {
        (feature.get("properties") or {}).get("unit_id"): feature
        for feature in features
    }

    for unit_id, expected in EXPECTED_SUBUNITS.items():
        feature = by_unit.get(unit_id)
        if feature is None:
            ERRORS.append(f"Santa Eulalia geometry missing research subunit {unit_id}")
            continue
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        if props.get("hydrologic_role") != "local_debris_flow_catchment_candidate":
            ERRORS.append(f"{unit_id}: hydrologic_role changed")
        if geom.get("type") != expected["geometry_type"]:
            ERRORS.append(f"{unit_id}: geometry type changed")
        if props.get("geometry_sha256") != expected["geometry_sha256"]:
            ERRORS.append(f"{unit_id}: pinned geometry hash changed")
        if (props.get("coverage") or {}).get("delineated_area_km2") != expected["area_km2"]:
            ERRORS.append(f"{unit_id}: declared area changed")
        if props.get("candidate_status") != "REVIEW_ONLY":
            ERRORS.append(f"{unit_id}: must remain REVIEW_ONLY")
        if props.get("production_use") is not False:
            ERRORS.append(f"{unit_id}: production_use must remain false")
        if props.get("loaded_into_operational_calculation") is not False:
            ERRORS.append(f"{unit_id}: must not enter operational calculation")

    forbidden_as_catchment = {
        "santa_eulalia_faja_2004",
        "rimac_faja_2020",
        "rimac_left_margin_update_2022",
    }
    missing = forbidden_as_catchment - set(by_unit)
    if missing:
        ERRORS.append(f"expected non-catchment Santa geometries missing: {sorted(missing)}")


def check_lurin_geometry():
    data = load(LURIN_GEOM)
    if data is None:
        return
    features = data.get("features") or []
    roles = {
        (feature.get("properties") or {}).get("feature_role")
        for feature in features
    }
    expected = {
        "official_right_margin_hitos_connected",
        "official_left_margin_hitos_connected",
        "derived_regulatory_corridor_polygon",
    }
    if roles != expected:
        ERRORS.append(f"Lurin geometry roles changed: {sorted(roles)}")


def check_artifact(result, inventory):
    records = result.get("candidate_records") or []
    by_id = {record.get("candidate_id"): record for record in records}
    expected_ids = {candidate["candidate_id"] for candidate in inventory.get("candidates") or []}

    if len(records) != 18 or set(by_id) != expected_ids:
        ERRORS.append("artifact must represent the exact 18 Phase-2 candidates")

    expected_status = {
        SANTA_ID: "SUBUNIT_RESEARCH_ONLY",
        LURIN_ID: "NON_CATCHMENT_GEOMETRY_ONLY",
    }
    for cid in expected_ids:
        expected = expected_status.get(cid, "BLOCKED_MISSING_GEOMETRY")
        if (by_id.get(cid) or {}).get("spatial_contract_status") != expected:
            ERRORS.append(
                f"{cid}: expected spatial_contract_status={expected}, found "
                f"{(by_id.get(cid) or {}).get('spatial_contract_status')}"
            )

    santa = by_id.get(SANTA_ID) or {}
    contracts = {
        contract.get("subunit_id"): contract
        for contract in santa.get("subunit_contracts") or []
    }
    if set(contracts) != set(EXPECTED_SUBUNITS):
        ERRORS.append(f"unexpected Santa subunit contract set: {sorted(contracts)}")

    for unit_id, expected in EXPECTED_SUBUNITS.items():
        contract = contracts.get(unit_id) or {}
        geom = contract.get("geometry_ref") or {}
        if geom.get("geometry_sha256") != expected["geometry_sha256"]:
            ERRORS.append(f"{unit_id}: artifact geometry hash mismatch")
        if geom.get("declared_area_km2") != expected["area_km2"]:
            ERRORS.append(f"{unit_id}: artifact area mismatch")
        if contract.get("counts_as_candidate_wide_geometry") is not False:
            ERRORS.append(f"{unit_id}: subunit must not complete parent geometry")
        if contract.get("counts_as_operational_geometry") is not False:
            ERRORS.append(f"{unit_id}: subunit must not count as operational geometry")
        sampling = contract.get("sampling_contract") or {}
        if sampling.get("cross_candidate_transfer_allowed") is not False:
            ERRORS.append(f"{unit_id}: cross-candidate transfer must be forbidden")
        if sampling.get("minimum_coverage_pct") is not None:
            ERRORS.append(f"{unit_id}: arbitrary coverage threshold must not be introduced")

    summary = result.get("summary") or {}
    expected_summary = {
        "candidate_count": 18,
        "candidate_wide_ready_count": 0,
        "subunit_research_only_candidate_count": 1,
        "non_catchment_geometry_only_count": 1,
        "blocked_missing_geometry_count": 16,
        "research_subunit_contract_count": 2,
        "operational_spatial_contract_count": 0,
    }
    for key, value in expected_summary.items():
        if summary.get(key) != value:
            ERRORS.append(f"summary.{key} expected {value}, found {summary.get(key)}")


def walk_forbidden(node, path="root"):
    forbidden = {
        "risk_score",
        "activation_score",
        "alert_score",
        "physical_response_plausibility_score",
        "promotion_gate_met",
    }
    if isinstance(node, dict):
        for key, value in node.items():
            if key in forbidden:
                ERRORS.append(f"forbidden decision key in spatial contract artifact: {path}.{key}")
            walk_forbidden(value, path + "." + str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            walk_forbidden(value, f"{path}[{index}]")


def first_difference(left, right, path="root"):
    if isinstance(left, (int, float)) and isinstance(right, (int, float)) and left == right:
        return None
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys differ {sorted(set(left) ^ set(right))}"
        for key in sorted(left):
            diff = first_difference(left[key], right[key], path + "." + str(key))
            if diff:
                return diff
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: list length {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            diff = first_difference(a, b, f"{path}[{index}]")
            if diff:
                return diff
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def check_determinism(result):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_phase2_spatial_observation_contracts as builder

    fresh = builder.generate(write=False)
    left = dict(result)
    right = dict(fresh)
    left.pop("generated_at", None)
    right.pop("generated_at", None)
    if left != right:
        ERRORS.append(
            "committed spatial contract artifact differs from deterministic regeneration: "
            + (first_difference(left, right) or "unknown difference")
        )


def main():
    ERRORS.clear()
    result = load(OUT)
    schema = load(SCHEMA)
    inventory = load(INVENTORY)
    catalog = load(CATALOG)
    if any(value is None for value in (result, schema, inventory, catalog)):
        for error in ERRORS:
            print("ERROR:", error)
        return 1

    check_schema(result, schema)
    check_phase2_guardrails(inventory, catalog)
    check_authoritative_geometry_state(catalog)
    check_santa_geometry()
    check_lurin_geometry()
    check_artifact(result, inventory)
    walk_forbidden(result)
    check_determinism(result)

    for error in ERRORS:
        print("ERROR:", error)
    if ERRORS:
        print(f"validate_phase2_spatial_observation_contracts: FAILED with {len(ERRORS)} error(s).")
        return 1
    print("validate_phase2_spatial_observation_contracts: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
