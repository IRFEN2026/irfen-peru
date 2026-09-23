#!/usr/bin/env python3
"""Validate explicit local-unit activation packages linked from Phase-2 zone contracts.

This is an overlay on the universal hierarchy. It never derives activation, geometry,
thresholds or hydraulic capacity. It only verifies that explicit child-level research
records remain local, source-traceable, non-operational and fail closed when geometry
or data are missing.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "config/phase2_local_activation_hierarchy_v0_1.json"
ZONE_DIR = ROOT / "site/data/validation/phase2_zone_contracts"

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
ALLOWED_STATES = {
    "METEOROLOGICAL_CONDITIONS_PRESENT",
    "RUNOFF_RESPONSE_PLAUSIBLE",
    "DIRECT_FLOW_EVIDENCE",
    "IMPACT_CONFIRMED",
}
ALLOWED_TYPES = {
    "LOCAL_CATCHMENT_OR_RAVINE_POLYGON",
    "MAIN_CHANNEL_LINE",
    "OUTLET_OR_CONTROL_POINT",
    "HISTORICAL_FAN_DEPOSIT_OR_EVENT_FOOTPRINT",
    "RECEIVER_CONFLUENCE_NODE",
}


class LocalPackageError(RuntimeError):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(msg: str) -> None:
    raise LocalPackageError(msg)


def require_safe(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            fail(f"UNSAFE_{label}_{key}")


def repo_json_path(raw: str, prefix: str, label: str) -> Path:
    if not isinstance(raw, str) or not raw.startswith(prefix) or not raw.endswith(".json"):
        fail(f"{label}_PATH_INVALID")
    p = ROOT / raw
    if not p.is_file():
        fail(f"{label}_MISSING_{raw}")
    return p


def package_path(raw: str) -> Path:
    return repo_json_path(
        raw,
        "site/data/validation/phase2_registered_unit_packages/",
        "LOCAL_PACKAGE",
    )


def validate_one(candidate_id: str, zone: dict, link: dict) -> dict:
    if link.get("architecture_path") != "config/phase2_local_activation_hierarchy_v0_1.json":
        fail(f"ARCHITECTURE_LINK_DRIFT_{candidate_id}")
    if link.get("parent_role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE":
        fail(f"PARENT_ROLE_DRIFT_{candidate_id}")
    if link.get("parent_research_evidence_state") is not None:
        fail(f"PARENT_STATE_ASSIGNED_{candidate_id}")
    if link.get("child_evidence_promotes_parent_activation") is not False:
        fail(f"CHILD_TO_PARENT_PROMOTION_{candidate_id}")
    if link.get("whole_basin_activation_statement_forbidden") is not True:
        fail(f"WHOLE_BASIN_ACTIVATION_ALLOWED_{candidate_id}")
    if link.get("allowed_parent_summary") != "N_SUBUNITS_WITH_EVIDENCE":
        fail(f"PARENT_SUMMARY_DRIFT_{candidate_id}")
    if link.get("children_must_remain_independent") is not True:
        fail(f"CHILD_SEPARATION_MISSING_{candidate_id}")
    if link.get("synthetic_child_union_forbidden") is not True:
        fail(f"SYNTHETIC_UNION_ALLOWED_{candidate_id}")

    ppath = package_path(link.get("package_path"))
    package = load(ppath)
    require_safe(package, f"PACKAGE_{candidate_id}")
    if package.get("candidate_id") != candidate_id:
        fail(f"PACKAGE_CANDIDATE_DRIFT_{candidate_id}")
    if package.get("architecture_path") != link.get("architecture_path"):
        fail(f"PACKAGE_ARCHITECTURE_DRIFT_{candidate_id}")

    evidence_path = repo_json_path(
        package.get("evidence_registry_path"),
        "site/data/phase2/sources/",
        f"EVIDENCE_REGISTRY_{candidate_id}",
    )
    evidence = load(evidence_path)
    require_safe(evidence, f"EVIDENCE_REGISTRY_{candidate_id}")
    if evidence.get("candidate_id") != candidate_id:
        fail(f"EVIDENCE_REGISTRY_CANDIDATE_DRIFT_{candidate_id}")
    source_rows = evidence.get("sources") or []
    source_ids = [row.get("source_id") for row in source_rows]
    if any(not isinstance(x, str) or not x for x in source_ids) or len(source_ids) != len(set(source_ids)):
        fail(f"EVIDENCE_SOURCE_IDS_INVALID_{candidate_id}")
    source_id_set = set(source_ids)

    strengthening_raw = package.get("strengthening_package_path")
    if strengthening_raw is not None:
        strengthening_path = repo_json_path(
            strengthening_raw,
            "site/data/validation/phase2_registered_unit_packages/",
            f"STRENGTHENING_PACKAGE_{candidate_id}",
        )
        strengthening = load(strengthening_path)
        require_safe(strengthening, f"STRENGTHENING_PACKAGE_{candidate_id}")
        if strengthening.get("candidate_id") != candidate_id:
            fail(f"STRENGTHENING_PACKAGE_CANDIDATE_DRIFT_{candidate_id}")

    parent = package.get("parent") or {}
    if parent.get("parent_id") != candidate_id:
        fail(f"PACKAGE_PARENT_ID_DRIFT_{candidate_id}")
    if parent.get("role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE":
        fail(f"PACKAGE_PARENT_ROLE_DRIFT_{candidate_id}")
    if parent.get("research_evidence_state") is not None or parent.get("activation_state") is not None:
        fail(f"PACKAGE_PARENT_STATE_ASSIGNED_{candidate_id}")
    if parent.get("child_evidence_promotes_parent_activation") is not False:
        fail(f"PACKAGE_PARENT_PROMOTION_ENABLED_{candidate_id}")
    if parent.get("whole_basin_activation_statement_forbidden") is not True:
        fail(f"PACKAGE_WHOLE_BASIN_ACTIVATION_ALLOWED_{candidate_id}")
    if parent.get("official_basin_geometry_is_event_footprint") is not False:
        fail(f"PACKAGE_PARENT_GEOMETRY_PROMOTED_TO_EVENT_{candidate_id}")

    children = package.get("children") or []
    ids = [c.get("local_unit_id") for c in children]
    if not children or any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        fail(f"CHILD_IDS_INVALID_{candidate_id}")
    if set(ids) != set(link.get("current_child_ids") or []):
        fail(f"CHILD_REGISTRY_LINK_DRIFT_{candidate_id}")

    evidence_count = 0
    for child in children:
        cid = child["local_unit_id"]
        if child.get("unit_type") not in ALLOWED_TYPES:
            fail(f"CHILD_TYPE_INVALID_{candidate_id}_{cid}")
        identity_source_ids = child.get("identity_source_ids") or []
        if any(source_id not in source_id_set for source_id in identity_source_ids):
            fail(f"CHILD_IDENTITY_SOURCE_NOT_FROZEN_{candidate_id}_{cid}")
        state = child.get("current_research_evidence_state")
        if state is not None and state not in ALLOWED_STATES:
            fail(f"CURRENT_STATE_INVALID_{candidate_id}_{cid}")
        historical = child.get("historical_event_states") or {}
        if historical:
            evidence_count += 1
        for event_key, record in historical.items():
            record = record or {}
            event_state = record.get("state")
            if event_state not in ALLOWED_STATES:
                fail(f"HISTORICAL_STATE_INVALID_{candidate_id}_{cid}_{event_key}")
            event_sources = record.get("source_ids") or []
            if not event_sources:
                fail(f"HISTORICAL_STATE_SOURCE_MISSING_{candidate_id}_{cid}_{event_key}")
            if any(source_id not in source_id_set for source_id in event_sources):
                fail(f"HISTORICAL_STATE_SOURCE_NOT_FROZEN_{candidate_id}_{cid}_{event_key}")
        if child.get("state_is_operational_alert") is not False:
            fail(f"CHILD_STATE_ALERT_SEMANTICS_{candidate_id}_{cid}")
        if child.get("state_is_risk_class") is not False:
            fail(f"CHILD_STATE_RISK_SEMANTICS_{candidate_id}_{cid}")
        if child.get("absence_of_report_is_negative_control") is True:
            fail(f"NEGATIVE_FROM_SILENCE_{candidate_id}_{cid}")
        raw = child.get("geometry_path")
        map_eligible = child.get("map_eligible")
        status = str(child.get("geometry_status") or "")
        if raw is None:
            if map_eligible is not False:
                fail(f"MISSING_GEOMETRY_MAP_ELIGIBLE_{candidate_id}_{cid}")
            if not status.startswith("MISSING"):
                fail(f"MISSING_GEOMETRY_STATUS_DRIFT_{candidate_id}_{cid}")
        else:
            if not isinstance(raw, str) or not raw.startswith("site/data/phase2/geometries/"):
                fail(f"CHILD_GEOMETRY_PATH_INVALID_{candidate_id}_{cid}")
            if not (ROOT / raw).is_file():
                fail(f"CHILD_GEOMETRY_FILE_MISSING_{candidate_id}_{cid}")
            if map_eligible is not True:
                fail(f"REPRODUCIBLE_GEOMETRY_NOT_MAP_ELIGIBLE_{candidate_id}_{cid}")

    summary = parent.get("parent_summary") or {}
    if summary.get("type") != "N_SUBUNITS_WITH_EVIDENCE":
        fail(f"PACKAGE_PARENT_SUMMARY_TYPE_DRIFT_{candidate_id}")
    if summary.get("subunits_with_historical_evidence") != evidence_count:
        fail(f"PACKAGE_PARENT_SUMMARY_COUNT_DRIFT_{candidate_id}")
    if summary.get("activation_statement") is not None:
        fail(f"PACKAGE_PARENT_ACTIVATION_STATEMENT_PRESENT_{candidate_id}")

    receiver = package.get("receiver_response") or {}
    if receiver.get("tributary_activation_implies_receiver_overflow") is not False:
        fail(f"RECEIVER_AUTO_OVERFLOW_{candidate_id}")
    if receiver.get("hydraulic_capacity_values") is not None:
        fail(f"RECEIVER_CAPACITY_INFERRED_{candidate_id}")

    meteorology = package.get("meteorology_policy") or {}
    if meteorology.get("imerg_role") != "REGIONAL_OR_SUBBASIN_CONTEXT_ONLY":
        fail(f"IMERG_ROLE_DRIFT_{candidate_id}")
    if meteorology.get("imerg_alone_selects_small_ravine_activation") is not False:
        fail(f"IMERG_LOCAL_SELECTION_ENABLED_{candidate_id}")

    mp = package.get("map_policy") or {}
    if mp.get("parent_style") != "GREY_CONTEXT":
        fail(f"PARENT_STYLE_DRIFT_{candidate_id}")
    if mp.get("children_published_only_when_geometry_reproducible") is not True:
        fail(f"MAP_CHILD_GEOMETRY_GATE_MISSING_{candidate_id}")
    if mp.get("risk_colors_forbidden") is not True or mp.get("alerts_forbidden") is not True:
        fail(f"MAP_OPERATIONAL_SEMANTICS_ENABLED_{candidate_id}")

    qa = package.get("qa") or {}
    required_false = [
        "parent_state_assigned",
        "child_to_parent_activation_promoted",
        "approximate_geometry_created",
        "synthetic_parent_union_created",
        "event_footprint_invented",
        "hydraulic_capacity_inferred",
        "threshold_inferred",
        "negative_control_from_silence_created",
        "mainstem_overflow_inferred_from_huerequeque",
    ]
    for key in required_false:
        if qa.get(key) is not False:
            fail(f"QA_GUARD_DRIFT_{candidate_id}_{key}")

    return {
        "candidate_id": candidate_id,
        "package_path": link["package_path"],
        "evidence_registry_path": package["evidence_registry_path"],
        "frozen_source_count": len(source_id_set),
        "child_count": len(children),
        "subunits_with_historical_evidence": evidence_count,
        "map_eligible_child_count": sum(c.get("map_eligible") is True for c in children),
        "parent_activation_state": None,
        "activation_gate": "BLOCKED",
    }


def validate_all() -> dict:
    arch = load(ARCH)
    require_safe(arch, "ARCHITECTURE")
    if arch.get("scope", {}).get("applies_to_current_and_future_units") is not True:
        fail("ARCHITECTURE_NOT_FUTURE_APPLICABLE")
    rows = []
    for path in sorted(ZONE_DIR.glob("*.json")):
        zone = load(path)
        candidate_id = zone.get("candidate_id")
        if not candidate_id:
            fail(f"ZONE_ID_MISSING_{path.name}")
        link = zone.get("local_activation_hierarchy")
        if link is not None:
            rows.append(validate_one(candidate_id, zone, link))
    return {
        "status": "PASS_LINKED_LOCAL_ACTIVATION_PACKAGES",
        **SAFE,
        "linked_package_count": len(rows),
        "packages": rows,
    }


def main() -> None:
    result = validate_all()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
