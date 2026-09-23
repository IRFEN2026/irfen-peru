#!/usr/bin/env python3
"""Validate the universal Phase-2/discovery local-unit activation research architecture.

This validator is intentionally an overlay over legacy Phase-2 contracts. Older contracts
may omit newer guard fields, but any explicit conflicting value fails closed. The effective
policy is always the stricter global architecture. No outcome, threshold, capacity or
operational state is derived here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH_PATH = ROOT / "config/phase2_local_activation_hierarchy_v0_1.json"

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
ALLOWED_STATES = [
    "METEOROLOGICAL_CONDITIONS_PRESENT",
    "RUNOFF_RESPONSE_PLAUSIBLE",
    "DIRECT_FLOW_EVIDENCE",
    "IMPACT_CONFIRMED",
]
ALLOWED_TYPES = {
    "LOCAL_CATCHMENT_OR_RAVINE_POLYGON",
    "MAIN_CHANNEL_LINE",
    "OUTLET_OR_CONTROL_POINT",
    "HISTORICAL_FAN_DEPOSIT_OR_EVENT_FOOTPRINT",
    "RECEIVER_CONFLUENCE_NODE",
}


class HierarchyError(RuntimeError):
    pass


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def fail(message: str):
    raise HierarchyError(message)


def require_architecture_guards(arch: dict) -> None:
    for key, expected in SAFE.items():
        if arch.get(key) != expected:
            fail(f"ARCHITECTURE_GUARD_DRIFT_{key}")


def reject_explicit_conflict(obj: dict, label: str) -> None:
    """Legacy omissions inherit SAFE; explicit weaker/conflicting values fail closed."""
    aliases = {"operational_alerting_enabled": "alerting_enabled"}
    for key, expected in SAFE.items():
        if key in obj and obj.get(key) != expected:
            fail(f"UNSAFE_EXPLICIT_{label}_{key}")
        alias = aliases.get(key)
        if alias in obj and obj.get(alias) is not False:
            fail(f"UNSAFE_EXPLICIT_{label}_{alias}")
    validation = obj.get("validation") or {}
    if "activation_gate" in validation and validation.get("activation_gate") != "BLOCKED":
        fail(f"UNSAFE_EXPLICIT_{label}_validation_activation_gate")


def validate_architecture_semantics(arch: dict) -> None:
    pp = arch.get("parent_policy") or {}
    if pp.get("role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE":
        fail("PARENT_ROLE_DRIFT")
    if pp.get("child_evidence_promotes_parent_activation") is not False:
        fail("CHILD_TO_PARENT_PROMOTION_ENABLED")
    if pp.get("whole_basin_activation_statement_forbidden") is not True:
        fail("WHOLE_BASIN_ACTIVATION_NOT_FORBIDDEN")
    if pp.get("composite_child_geometry_union_forbidden") is not True:
        fail("SYNTHETIC_PARENT_UNION_NOT_FORBIDDEN")

    local = arch.get("local_unit_contract") or {}
    if set(local.get("allowed_unit_types") or []) != ALLOWED_TYPES:
        fail("LOCAL_UNIT_TYPES_DRIFT")
    if local.get("approximate_geometry_forbidden") is not True:
        fail("APPROXIMATE_GEOMETRY_NOT_FORBIDDEN")
    if local.get("invented_polygon_forbidden") is not True:
        fail("INVENTED_POLYGON_NOT_FORBIDDEN")
    if local.get("synthetic_union_forbidden") is not True:
        fail("SYNTHETIC_UNION_NOT_FORBIDDEN")

    if arch.get("research_evidence_states") != ALLOWED_STATES:
        fail("RESEARCH_EVIDENCE_STATES_DRIFT")
    state = arch.get("state_semantics") or {}
    if state.get("states_are_operational_alerts") is not False:
        fail("RESEARCH_STATES_PROMOTED_TO_ALERTS")
    if state.get("states_are_risk_classes") is not False:
        fail("RESEARCH_STATES_PROMOTED_TO_RISK")
    if state.get("parent_state_assignment_forbidden") is not True:
        fail("PARENT_STATE_ASSIGNMENT_NOT_FORBIDDEN")

    met = arch.get("meteorology_policy") or {}
    if met.get("imerg_role") != "REGIONAL_OR_SUBBASIN_CONTEXT_ONLY":
        fail("IMERG_ROLE_DRIFT")
    if met.get("imerg_alone_selects_small_ravine_activation") is not False:
        fail("IMERG_SMALL_RAVINE_DECISION_ENABLED")

    receiver = arch.get("receiver_policy") or {}
    if receiver.get("tributary_activation_implies_receiver_overflow") is not False:
        fail("TRIBUTARY_IMPLIES_RECEIVER_OVERFLOW")
    required_receiver = {"TRAVEL_TIME", "PEAK_COINCIDENCE", "MAINSTEM_STAGE_OR_DISCHARGE_RESPONSE", "RECEIVER_HYDRAULIC_CONTEXT"}
    if set(receiver.get("model_separately") or []) != required_receiver:
        fail("RECEIVER_MODEL_COMPONENTS_DRIFT")

    sg = arch.get("semantic_guardrails") or {}
    expected_false = {
        "faja_margin_is_event_footprint",
        "works_or_design_are_historical_capacity",
        "critical_point_is_observed_event",
        "cross_basin_threshold_transfer_allowed",
        "absence_of_report_is_negative_control",
        "distinct_hydrologic_units_may_be_artificially_connected",
    }
    for key in expected_false:
        if sg.get(key) is not False:
            fail(f"SEMANTIC_GUARD_DRIFT_{key}")

    mp = arch.get("map_policy") or {}
    if mp.get("parent_style") != "GREY_CONTEXT":
        fail("PARENT_MAP_STYLE_NOT_GREY_CONTEXT")
    for key in ("children_are_independent_layers", "historical_footprints_separate", "missing_geometry_is_not_drawn", "parent_composite_from_child_union_forbidden"):
        if mp.get(key) is not True:
            fail(f"MAP_POLICY_DRIFT_{key}")
    for key in ("risk_colors_forbidden", "alerts_forbidden"):
        if mp.get(key) is not True:
            fail(f"MAP_POLICY_DRIFT_{key}")


def validate_zone_contracts(arch: dict, inventory: dict) -> list[dict]:
    contract_dir = ROOT / arch["scope"]["zone_contract_directory"]
    rows = []
    ids = [row.get("candidate_id") for row in inventory.get("candidates") or []]
    if len(ids) != len(set(ids)) or any(not x for x in ids):
        fail("CANDIDATE_IDS_INVALID")
    for candidate_id in ids:
        path = contract_dir / f"{candidate_id}.json"
        if not path.is_file():
            fail(f"MISSING_ZONE_CONTRACT_{candidate_id}")
        c = load(path)
        if c.get("candidate_id") != candidate_id:
            fail(f"ZONE_CONTRACT_ID_DRIFT_{candidate_id}")
        reject_explicit_conflict(c, f"ZONE_{candidate_id}")
        # Parent rows are context containers under the overlay regardless of whether
        # their legacy geometry is an official whole-basin polygon or partial context.
        if c.get("activation_state") is not None or c.get("research_activation_state") is not None:
            fail(f"PARENT_STATE_PRESENT_{candidate_id}")
        rows.append({
            "parent_id": candidate_id,
            "parent_role": "CONTEXT_CONTAINER_NON_ACTIVATABLE",
            "activation_state_allowed": False,
            "geometry_role": "CONTEXT_ONLY_NEVER_ACTIVATION_GEOMETRY",
            "contract_path": rel(path),
            "contract_sha256": digest(path),
        })
    return rows


def validate_discovery_contracts(arch: dict, inventory: dict) -> tuple[list[dict], list[dict]]:
    contract_dir = ROOT / arch["scope"]["discovery_contract_directory"]
    parent_rows = []
    child_rows = []
    ids = [row.get("discovery_id") for row in inventory.get("discovery_units") or []]
    if len(ids) != len(set(ids)) or any(not x for x in ids):
        fail("DISCOVERY_IDS_INVALID")
    for key, expected in SAFE.items():
        if inventory.get(key) != expected:
            fail(f"DISCOVERY_INVENTORY_GUARD_DRIFT_{key}")
    item_by_id = {row["discovery_id"]: row for row in inventory.get("discovery_units") or []}
    for discovery_id in ids:
        path = contract_dir / f"{discovery_id}.json"
        contract = load(path) if path.is_file() else None
        if contract:
            if contract.get("discovery_id") != discovery_id:
                fail(f"DISCOVERY_CONTRACT_ID_DRIFT_{discovery_id}")
            reject_explicit_conflict(contract, f"DISCOVERY_{discovery_id}")
            if contract.get("activation_state") is not None or contract.get("research_activation_state") is not None:
                fail(f"DISCOVERY_PARENT_STATE_PRESENT_{discovery_id}")
        parent_rows.append({
            "parent_id": discovery_id,
            "parent_role": "CONTEXT_CONTAINER_NON_ACTIVATABLE",
            "activation_state_allowed": False,
            "geometry_role": "CONTEXT_ONLY_NEVER_ACTIVATION_GEOMETRY",
            "contract_path": rel(path) if contract else None,
            "contract_sha256": digest(path) if contract else None,
            "declared_hydrologic_components": item_by_id[discovery_id].get("hydrologic_components") or [],
        })
        if not contract:
            continue
        policy = contract.get("component_policy") or {}
        components = ((contract.get("assets") or {}).get("geometry_components") or [])
        if components:
            if policy.get("components_must_remain_separate") is not True:
                fail(f"DISCOVERY_CHILD_SEPARATION_MISSING_{discovery_id}")
            if policy.get("composite_union_forbidden") is not True:
                fail(f"DISCOVERY_COMPOSITE_UNION_ALLOWED_{discovery_id}")
            if policy.get("parent_is_map_polygon") is not False:
                fail(f"DISCOVERY_PARENT_MAP_POLYGON_{discovery_id}")
        parent_geom = ((contract.get("assets") or {}).get("geometry") or {})
        if policy.get("parent_is_map_polygon") is False and parent_geom.get("path") is not None:
            fail(f"DISCOVERY_GROUPER_PARENT_GEOMETRY_CREATED_{discovery_id}")
        local_seen = set()
        for component in components:
            cid = component.get("component_id")
            if not isinstance(cid, str) or not cid or cid in local_seen:
                fail(f"DISCOVERY_COMPONENT_ID_INVALID_{discovery_id}")
            local_seen.add(cid)
            geom = component.get("geometry") or {}
            if geom.get("counts_as_operational_geometry") is not False:
                fail(f"DISCOVERY_CHILD_OPERATIONAL_GEOMETRY_{discovery_id}_{cid}")
            if geom.get("counts_as_event_footprint") is not False:
                fail(f"DISCOVERY_CHILD_EVENT_FOOTPRINT_{discovery_id}_{cid}")
            status = str(geom.get("status", "MISSING"))
            raw = geom.get("path")
            reproducible = not status.startswith("MISSING")
            if reproducible:
                if not isinstance(raw, str) or not raw.startswith("site/data/phase2/geometries/"):
                    fail(f"DISCOVERY_CHILD_PATH_INVALID_{discovery_id}_{cid}")
                gp = ROOT / raw
                if not gp.is_file():
                    fail(f"DISCOVERY_CHILD_GEOMETRY_MISSING_{discovery_id}_{cid}")
                if geom.get("sha256") and geom.get("sha256") != digest(gp):
                    fail(f"DISCOVERY_CHILD_GEOMETRY_HASH_DRIFT_{discovery_id}_{cid}")
                vp_raw = geom.get("validation_path")
                if not isinstance(vp_raw, str) or not (ROOT / vp_raw).is_file():
                    fail(f"DISCOVERY_CHILD_VALIDATION_MISSING_{discovery_id}_{cid}")
                if geom.get("validation_sha256") and geom.get("validation_sha256") != digest(ROOT / vp_raw):
                    fail(f"DISCOVERY_CHILD_VALIDATION_HASH_DRIFT_{discovery_id}_{cid}")
            child_rows.append({
                "parent_id": discovery_id,
                "local_unit_id": f"{discovery_id}__{cid}",
                "component_id": cid,
                "activation_state_allowed": True,
                "allowed_research_states": ALLOWED_STATES,
                "geometry_status": status,
                "map_eligible": reproducible,
                "geometry_path": raw if reproducible else None,
            })
    return parent_rows, child_rows


def validate_demonstrators(arch: dict, candidate_inventory: dict) -> list[dict]:
    candidates = {row["candidate_id"]: row for row in candidate_inventory.get("candidates") or []}
    rows = []
    for parent_id, demo in (arch.get("demonstrators") or {}).items():
        if parent_id not in candidates:
            fail(f"DEMONSTRATOR_PARENT_NOT_IN_INVENTORY_{parent_id}")
        if demo.get("parent_role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE":
            fail(f"DEMONSTRATOR_PARENT_ROLE_DRIFT_{parent_id}")
        if demo.get("parent_activation_state") is not None:
            fail(f"DEMONSTRATOR_PARENT_STATE_ASSIGNED_{parent_id}")
        official = set(candidates[parent_id].get("official_sources") or [])
        seen = set()
        for child in demo.get("children") or []:
            cid = child.get("local_unit_id")
            if not isinstance(cid, str) or not cid or cid in seen:
                fail(f"DEMONSTRATOR_CHILD_ID_INVALID_{parent_id}")
            seen.add(cid)
            if child.get("unit_type") not in ALLOWED_TYPES:
                fail(f"DEMONSTRATOR_CHILD_TYPE_INVALID_{parent_id}_{cid}")
            state = child.get("evidence_state")
            if state is not None and state not in ALLOWED_STATES:
                fail(f"DEMONSTRATOR_CHILD_STATE_INVALID_{parent_id}_{cid}")
            source_ids = child.get("identity_source_ids") or []
            if not set(source_ids).issubset(official):
                fail(f"DEMONSTRATOR_SOURCE_NOT_REGISTERED_{parent_id}_{cid}")
            gs = str(child.get("geometry_status", ""))
            if "PENDING" in gs or "NOT_ASSERTED" in gs or gs.startswith("MISSING"):
                map_eligible = False
            else:
                fail(f"DEMONSTRATOR_GEOMETRY_UNVERIFIED_PROMOTION_{parent_id}_{cid}")
            rows.append({
                "parent_id": parent_id,
                "local_unit_id": cid,
                "unit_type": child["unit_type"],
                "activation_state_allowed": True,
                "evidence_state": state,
                "geometry_status": gs,
                "map_eligible": map_eligible,
            })
    return rows


def build_registry() -> dict:
    arch = load(ARCH_PATH)
    require_architecture_guards(arch)
    validate_architecture_semantics(arch)
    scope = arch.get("scope") or {}
    if scope.get("applies_to_current_and_future_units") is not True:
        fail("ARCHITECTURE_NOT_FUTURE_APPLICABLE")
    candidate_path = ROOT / scope["candidate_inventory"]
    discovery_path = ROOT / scope["discovery_inventory"]
    candidates = load(candidate_path)
    discovery = load(discovery_path)
    reject_explicit_conflict(candidates, "CANDIDATE_INVENTORY")
    zone_parents = validate_zone_contracts(arch, candidates)
    discovery_parents, discovery_children = validate_discovery_contracts(arch, discovery)
    demonstrator_children = validate_demonstrators(arch, candidates)
    parent_ids = [row["parent_id"] for row in zone_parents + discovery_parents]
    if len(parent_ids) != len(set(parent_ids)):
        fail("PARENT_ID_COLLISION_BETWEEN_INVENTORIES")
    return {
        "schema_version": "0.1",
        "status": "PASS_LOCAL_ACTIVATION_HIERARCHY",
        **SAFE,
        "architecture_path": rel(ARCH_PATH),
        "architecture_sha256": digest(ARCH_PATH),
        "candidate_inventory_sha256": digest(candidate_path),
        "discovery_inventory_sha256": digest(discovery_path),
        "summary": {
            "phase2_parent_count": len(zone_parents),
            "discovery_parent_count": len(discovery_parents),
            "reproducible_discovery_child_count": sum(row["map_eligible"] for row in discovery_children),
            "declared_discovery_child_contract_count": len(discovery_children),
            "demonstrator_local_unit_count": len(demonstrator_children),
            "parent_activation_state_assignments": 0,
            "new_operational_units": 0,
        },
        "parent_units": zone_parents + discovery_parents,
        "discovery_local_units": discovery_children,
        "demonstrator_local_units": demonstrator_children,
        "allowed_research_states": ALLOWED_STATES,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-registry", type=Path)
    args = ap.parse_args()
    registry = build_registry()
    if args.write_registry:
        out = args.write_registry
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(registry["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
