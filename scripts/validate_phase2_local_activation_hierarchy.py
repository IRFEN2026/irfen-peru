#!/usr/bin/env python3
"""Validate the universal Phase-2/discovery local-unit activation research architecture.

The hierarchy is a strict overlay over legacy Phase-2 contracts. Older contracts may omit
newer guard fields, but any explicit conflicting value fails closed. Existing reproducible
spatial subunits are registered as local research units without promoting their parent.
No outcome, threshold, capacity or operational state is derived here.
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
    required_receiver = {
        "TRAVEL_TIME",
        "PEAK_COINCIDENCE",
        "MAINSTEM_STAGE_OR_DISCHARGE_RESPONSE",
        "RECEIVER_HYDRAULIC_CONTEXT",
    }
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
    for key in (
        "children_are_independent_layers",
        "historical_footprints_separate",
        "missing_geometry_is_not_drawn",
        "parent_composite_from_child_union_forbidden",
    ):
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


def validate_spatial_subunits(arch: dict, candidate_inventory: dict) -> tuple[list[dict], dict[str, dict]]:
    path = ROOT / arch["scope"]["spatial_observation_contracts"]
    spatial = load(path)
    if spatial.get("deployment_status") != "RESEARCH_ONLY":
        fail("SPATIAL_CONTRACT_NOT_RESEARCH_ONLY")
    if spatial.get("test_mode") not in (True, "TEST_ONLY"):
        fail("SPATIAL_CONTRACT_NOT_TEST_ONLY")
    for key, expected in {
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "decision_thresholds": None,
    }.items():
        if spatial.get(key) != expected:
            fail(f"SPATIAL_CONTRACT_GUARD_DRIFT_{key}")
    guardrails = spatial.get("guardrails") or {}
    required_true = {
        "regulatory_corridor_is_not_catchment",
        "river_margin_is_not_catchment",
        "line_geometry_is_not_area_sampling_geometry",
        "subunit_contract_does_not_complete_parent_candidate",
        "cross_candidate_spatial_transfer_forbidden",
        "sampling_contract_is_not_activation_validation",
        "missing_geometry_is_blocked_not_low_risk",
    }
    for key in required_true:
        if guardrails.get(key) is not True:
            fail(f"SPATIAL_GUARD_DRIFT_{key}")

    candidate_ids = {x["candidate_id"] for x in candidate_inventory.get("candidates") or []}
    records = spatial.get("candidate_records") or []
    record_ids = [x.get("candidate_id") for x in records]
    if set(record_ids) != candidate_ids or len(record_ids) != len(set(record_ids)):
        fail("SPATIAL_CANDIDATE_COVERAGE_DRIFT")

    rows = []
    by_contract = {}
    for record in records:
        parent = record["candidate_id"]
        if record.get("production_use") is not False or record.get("production_ready") is not False:
            fail(f"SPATIAL_PARENT_UNSAFE_{parent}")
        if record.get("activation_gate") != "BLOCKED":
            fail(f"SPATIAL_PARENT_GATE_OPEN_{parent}")
        if record.get("candidate_wide_sampling_ready") is True and record.get("candidate_wide_contract") is None:
            fail(f"SPATIAL_PARENT_READY_WITHOUT_CONTRACT_{parent}")
        for sub in record.get("subunit_contracts") or []:
            contract_id = sub.get("contract_id")
            sid = sub.get("subunit_id")
            if not contract_id or contract_id in by_contract or not sid:
                fail(f"SPATIAL_SUBUNIT_ID_INVALID_{parent}")
            if sub.get("candidate_id") != parent:
                fail(f"SPATIAL_SUBUNIT_PARENT_DRIFT_{parent}_{sid}")
            scope = str(sub.get("contract_scope") or "")
            if not scope.endswith("_RESEARCH_ONLY") or "HYDROLOGIC" not in scope:
                fail(f"SPATIAL_SUBUNIT_SCOPE_DRIFT_{parent}_{sid}_{scope}")
            if sub.get("contract_status") != "RESEARCH_SAMPLING_ELIGIBLE":
                fail(f"SPATIAL_SUBUNIT_NOT_RESEARCH_ELIGIBLE_{parent}_{sid}")
            for key, expected in {
                "deployment_status": "RESEARCH_ONLY",
                "production_use": False,
                "production_ready": False,
                "operational_alerting_enabled": False,
                "activation_gate": "BLOCKED",
                "counts_as_candidate_wide_geometry": False,
                "counts_as_operational_geometry": False,
            }.items():
                if sub.get(key) != expected:
                    fail(f"SPATIAL_SUBUNIT_GUARD_DRIFT_{parent}_{sid}_{key}")
            ref = sub.get("geometry_ref") or {}
            raw = ref.get("path")
            if not isinstance(raw, str) or not raw.startswith("site/data/phase2/geometries/"):
                fail(f"SPATIAL_SUBUNIT_GEOMETRY_PATH_INVALID_{parent}_{sid}")
            gp = ROOT / raw
            if not gp.is_file():
                fail(f"SPATIAL_SUBUNIT_GEOMETRY_MISSING_{parent}_{sid}")
            selector = ref.get("feature_selector") or {}
            prop = selector.get("property")
            value = selector.get("value")
            if not isinstance(prop, str) or value is None:
                fail(f"SPATIAL_SUBUNIT_SELECTOR_MISSING_{parent}_{sid}")
            doc = load(gp)
            features = doc.get("features") if doc.get("type") == "FeatureCollection" else [doc]
            selected = [f for f in features if (f.get("properties") or {}).get(prop) == value]
            if len(selected) != 1:
                fail(f"SPATIAL_SUBUNIT_SELECTOR_NOT_UNIQUE_{parent}_{sid}_{len(selected)}")
            feature = selected[0]
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != ref.get("geometry_type"):
                fail(f"SPATIAL_SUBUNIT_GEOMETRY_TYPE_DRIFT_{parent}_{sid}")
            props = feature.get("properties") or {}
            if props.get("production_use") is True or props.get("production_ready") is True:
                fail(f"SPATIAL_SUBUNIT_FEATURE_PRODUCTION_FLAG_{parent}_{sid}")
            if props.get("loaded_into_operational_calculation") is True or props.get("carries_alert_values") is True or props.get("carries_risk_classification") is True:
                fail(f"SPATIAL_SUBUNIT_FEATURE_OPERATIONAL_FLAG_{parent}_{sid}")
            expected_hash = ref.get("geometry_sha256")
            hash_scope = ref.get("hash_scope")
            if hash_scope == "FEATURE_GEOMETRY_SHA256":
                if not expected_hash or props.get("geometry_sha256") != expected_hash:
                    fail(f"SPATIAL_SUBUNIT_FEATURE_HASH_REFERENCE_DRIFT_{parent}_{sid}")
            elif hash_scope == "GEOJSON_FILE_SHA256":
                if not expected_hash or digest(gp) != expected_hash:
                    fail(f"SPATIAL_SUBUNIT_FILE_HASH_DRIFT_{parent}_{sid}")
            else:
                fail(f"SPATIAL_SUBUNIT_HASH_SCOPE_UNSUPPORTED_{parent}_{sid}_{hash_scope}")
            row = {
                "parent_id": parent,
                "local_unit_id": sid,
                "spatial_contract_id": contract_id,
                "activation_state_allowed": True,
                "allowed_research_states": ALLOWED_STATES,
                "geometry_status": "REPRODUCIBLE_REVIEW_ONLY_LOCAL_GEOMETRY",
                "geometry_path": raw,
                "geometry_file_sha256": digest(gp),
                "feature_selector": selector,
                "declared_geometry_sha256": expected_hash,
                "hash_scope": hash_scope,
                "geometry_type": ref.get("geometry_type"),
                "confidence": ref.get("confidence"),
                "candidate_status": ref.get("candidate_status"),
                "map_eligible": True,
                "counts_as_parent_geometry": False,
                "counts_as_operational_geometry": False,
                "outlet_status": sub.get("outlet_status"),
            }
            rows.append(row)
            by_contract[contract_id] = row
    return rows, by_contract


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
                "counts_as_parent_geometry": False,
                "counts_as_operational_geometry": False,
            })
    return parent_rows, child_rows


def validate_demonstrators(arch: dict, candidate_inventory: dict, spatial_by_contract: dict[str, dict]) -> list[dict]:
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
            spatial_contract_id = child.get("spatial_contract_id")
            if gs == "REPRODUCIBLE_REVIEW_ONLY_LOCAL_GEOMETRY":
                linked = spatial_by_contract.get(spatial_contract_id)
                if not linked:
                    fail(f"DEMONSTRATOR_SPATIAL_CONTRACT_MISSING_{parent_id}_{cid}")
                if linked["parent_id"] != parent_id or linked["local_unit_id"] != cid:
                    fail(f"DEMONSTRATOR_SPATIAL_LINK_DRIFT_{parent_id}_{cid}")
                map_eligible = True
                geometry_path = linked["geometry_path"]
            elif "PENDING" in gs or "NOT_ASSERTED" in gs or gs.startswith("MISSING"):
                if spatial_contract_id is not None:
                    fail(f"DEMONSTRATOR_UNRESOLVED_HAS_SPATIAL_CONTRACT_{parent_id}_{cid}")
                map_eligible = False
                geometry_path = None
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
                "geometry_path": geometry_path,
                "spatial_contract_id": spatial_contract_id,
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
    spatial_path = ROOT / scope["spatial_observation_contracts"]
    candidates = load(candidate_path)
    discovery = load(discovery_path)
    reject_explicit_conflict(candidates, "CANDIDATE_INVENTORY")
    zone_parents = validate_zone_contracts(arch, candidates)
    phase2_local_units, spatial_by_contract = validate_spatial_subunits(arch, candidates)
    discovery_parents, discovery_children = validate_discovery_contracts(arch, discovery)
    demonstrator_children = validate_demonstrators(arch, candidates, spatial_by_contract)
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
        "spatial_observation_contracts_sha256": digest(spatial_path),
        "summary": {
            "phase2_parent_count": len(zone_parents),
            "discovery_parent_count": len(discovery_parents),
            "reproducible_phase2_local_unit_count": sum(row["map_eligible"] for row in phase2_local_units),
            "reproducible_discovery_child_count": sum(row["map_eligible"] for row in discovery_children),
            "declared_discovery_child_contract_count": len(discovery_children),
            "demonstrator_local_unit_count": len(demonstrator_children),
            "demonstrator_reproducible_local_unit_count": sum(row["map_eligible"] for row in demonstrator_children),
            "parent_activation_state_assignments": 0,
            "new_operational_units": 0,
        },
        "parent_units": zone_parents + discovery_parents,
        "phase2_local_units": phase2_local_units,
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
        out.write_text(
            json.dumps(registry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(registry["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
