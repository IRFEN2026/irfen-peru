#!/usr/bin/env python3
"""Validate the Phase-2 tributary-to-collector coupling research architecture.

This validator is intentionally fail-closed. It validates architecture, provenance and
scientific guardrails only; it does not infer connectivity, discharge, travel time,
capacity, risk, activation, or operational thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH_PATH = ROOT / "config/phase2_collector_coupling_architecture_v0_1.json"
HIERARCHY_PATH = ROOT / "config/phase2_local_activation_hierarchy_v0_1.json"
SPATIAL_PATH = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
DEMO_PATH = ROOT / "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_1.json"

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
EFFECT_STATES = [
    "NO_EVIDENCE",
    "HYDROLOGICALLY_CONNECTED",
    "CONTRIBUTION_PLAUSIBLE",
    "CONTRIBUTION_OBSERVED_OR_ROUTED",
    "COLLECTOR_LEVEL_RESPONSE_OBSERVED_OR_HYDRAULICALLY_REPRODUCED",
]
FORBIDDEN_SOURCE_FRAGMENTS = {
    "official_outcome_evidence",
    "contaminated",
    "do_not_use",
    "a6680",
}


class CouplingError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise CouplingError(message)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def require_safe(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            fail(f"GUARD_DRIFT_{label}_{key}")


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from iter_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from iter_strings(v)


def reject_forbidden_sources(value, label: str) -> None:
    for text in iter_strings(value):
        low = text.lower()
        for fragment in FORBIDDEN_SOURCE_FRAGMENTS:
            if fragment in low:
                fail(f"FORBIDDEN_SOURCE_REFERENCE_{label}_{fragment}")


def reject_arbitrary_weight_probability_keys(value, label: str) -> None:
    if isinstance(value, dict):
        for key, val in value.items():
            low = str(key).lower()
            if "weight" in low or "probab" in low or low in {"score", "coupling_score"}:
                fail(f"ARBITRARY_WEIGHT_OR_PROBABILITY_FIELD_{label}_{key}")
            reject_arbitrary_weight_probability_keys(val, label)
    elif isinstance(value, list):
        for val in value:
            reject_arbitrary_weight_probability_keys(val, label)


def validate_architecture(arch: dict, hierarchy: dict) -> None:
    require_safe(arch, "ARCH")
    require_safe(hierarchy, "HIERARCHY")
    if arch.get("inherits", {}).get("local_activation_hierarchy") != "config/phase2_local_activation_hierarchy_v0_1.json":
        fail("LOCAL_HIERARCHY_REFERENCE_DRIFT")
    if hierarchy.get("parent_policy", {}).get("role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE":
        fail("PARENT_ROLE_NOT_FAIL_CLOSED")
    if hierarchy.get("receiver_policy", {}).get("tributary_activation_implies_receiver_overflow") is not False:
        fail("TRIBUTARY_TO_RECEIVER_AUTO_PROMOTION_ENABLED")
    if arch.get("collector_effect_states") != EFFECT_STATES:
        fail("COLLECTOR_EFFECT_STATES_DRIFT")
    sem = arch.get("state_semantics") or {}
    for key in ("states_are_operational_alerts", "states_are_risk_classes", "states_are_probabilities"):
        if sem.get(key) is not False:
            fail(f"STATE_SEMANTICS_UNSAFE_{key}")
    if sem.get("state_order_must_not_be_used_as_numeric_weight") is not True:
        fail("STATE_ORDER_NUMERIC_WEIGHT_NOT_FORBIDDEN")
    if sem.get("no_evidence_is_not_negative_evidence") is not True:
        fail("NO_EVIDENCE_NEGATIVE_SEMANTICS_DRIFT")

    balance = arch.get("collector_balance") or {}
    if balance.get("conceptual_equation") != "Q_collector(t)=Q_upstream(t)+sum(route_i(Q_i,tau_i))+Q_lateral(t)-storage/diversions/regulation":
        fail("COLLECTOR_BALANCE_EQUATION_DRIFT")
    if balance.get("operational_rule") is not False:
        fail("COLLECTOR_BALANCE_PROMOTED_OPERATIONAL")
    if balance.get("direct_sum_of_tributary_outlets_equals_downstream_flow") is not False:
        fail("DIRECT_FLOW_SUM_ENABLED")
    if balance.get("peak_synchrony_required_for_peak_compounding_inference") is not True:
        fail("PEAK_SYNCHRONY_GUARD_MISSING")

    routing = arch.get("routing_policy") or {}
    for key in (
        "simplified_methods_must_be_labeled_simplified",
        "hec_hms_or_equivalent_allowed_only_with_reproducible_inputs",
        "travel_time_without_reproducible_basis_forbidden",
        "attenuation_without_reproducible_basis_forbidden",
        "routing_without_time_axis_forbidden",
    ):
        if routing.get(key) is not True:
            fail(f"ROUTING_POLICY_DRIFT_{key}")

    hydraulic = arch.get("hydraulic_policy") or {}
    if hydraulic.get("hec_ras_1d_2d_or_equivalent_allowed_only_with_sufficient_inputs") is not True:
        fail("HYDRAULIC_MODEL_INPUT_GATE_MISSING")
    if hydraulic.get("capacity_default") != "UNKNOWN":
        fail("HYDRAULIC_CAPACITY_DEFAULT_DRIFT")
    if hydraulic.get("works_or_design_are_historical_capacity") is not False:
        fail("WORKS_PROMOTED_TO_HISTORICAL_CAPACITY")
    if hydraulic.get("capacity_may_be_inferred_from_design_document_alone") is not False:
        fail("DESIGN_DOCUMENT_CAPACITY_INFERENCE_ENABLED")

    matrix = arch.get("collector_coupling_matrix") or {}
    if matrix.get("arbitrary_weights_forbidden") is not True or matrix.get("arbitrary_probabilities_forbidden") is not True:
        fail("MATRIX_ARBITRARY_WEIGHT_PROBABILITY_GUARD_MISSING")
    if matrix.get("absence_of_report_is_negative_control") is not False:
        fail("DOCUMENTARY_SILENCE_NEGATIVE_CONTROL_ENABLED")

    integrity = arch.get("data_integrity") or {}
    for key in ("sealed_outcome_inputs_forbidden", "contaminated_artifacts_forbidden", "a6680_numeric_values_as_calibration_target_forbidden"):
        if integrity.get(key) is not True:
            fail(f"DATA_INTEGRITY_GUARD_DRIFT_{key}")


def spatial_subunits(spatial: dict, parent_id: str) -> dict[str, dict]:
    for record in spatial.get("candidate_records") or []:
        if record.get("candidate_id") == parent_id:
            return {x.get("subunit_id"): x for x in record.get("subunit_contracts") or []}
    fail(f"SPATIAL_PARENT_NOT_FOUND_{parent_id}")


def validate_source_outlet(tributary: dict, spatial_sub: dict) -> None:
    if tributary.get("source_local_geometry_contract_or_explicit_missing_status") != spatial_sub.get("contract_id"):
        fail(f"LOCAL_GEOMETRY_CONTRACT_DRIFT_{tributary.get('local_unit_id')}")
    src = tributary.get("source_outlet_or_explicit_missing_status")
    expected = spatial_sub.get("outlet_status")
    if not isinstance(src, dict) or not isinstance(expected, dict):
        fail(f"SOURCE_OUTLET_MISSING_{tributary.get('local_unit_id')}")
    for key in ("lon", "lat", "official_confirmation", "selection"):
        if src.get(key) != expected.get(key):
            fail(f"SOURCE_OUTLET_DRIFT_{tributary.get('local_unit_id')}_{key}")
    if src.get("is_receiver_confluence") is not False:
        fail(f"UNVALIDATED_OUTLET_PROMOTED_TO_CONFLUENCE_{tributary.get('local_unit_id')}")


def confluence_ready(tributary: dict) -> bool:
    confluence = tributary.get("receiver_confluence_or_explicit_missing_status") or {}
    loc = confluence.get("location")
    prov = confluence.get("provenance") or []
    return isinstance(loc, dict) and loc.get("lon") is not None and loc.get("lat") is not None and bool(prov)


def validate_tributary_state(tributary: dict) -> None:
    tid = tributary.get("local_unit_id") or "UNKNOWN"
    state = tributary.get("collector_effect_state")
    if state not in EFFECT_STATES:
        fail(f"INVALID_COLLECTOR_EFFECT_STATE_{tid}_{state}")
    fields = ("q_i_t", "travel_time_tau", "routing_method", "attenuation_or_storage", "hydraulic_distance")
    paired = tributary.get("paired_observations") or []
    if state == "NO_EVIDENCE":
        if tributary.get("connectivity") != "UNRESOLVED_NOT_ASSUMED":
            fail(f"NO_EVIDENCE_CONNECTIVITY_ASSUMED_{tid}")
        if confluence_ready(tributary):
            fail(f"NO_EVIDENCE_WITH_READY_CONFLUENCE_{tid}")
        for field in fields:
            if tributary.get(field) is not None:
                fail(f"NO_EVIDENCE_HAS_UNSUPPORTED_{tid}_{field}")
        if paired:
            fail(f"NO_EVIDENCE_HAS_PAIRED_OBSERVATIONS_{tid}")
        return

    if not confluence_ready(tributary):
        fail(f"COUPLING_STATE_WITHOUT_REPRODUCIBLE_CONFLUENCE_{tid}")
    if state == "HYDROLOGICALLY_CONNECTED":
        return
    if state == "CONTRIBUTION_PLAUSIBLE":
        if not tributary.get("contribution_basis"):
            fail(f"PLAUSIBLE_CONTRIBUTION_WITHOUT_BASIS_{tid}")
        return
    if state in {"CONTRIBUTION_OBSERVED_OR_ROUTED", "COLLECTOR_LEVEL_RESPONSE_OBSERVED_OR_HYDRAULICALLY_REPRODUCED"}:
        if tributary.get("q_i_t") is None:
            fail(f"OBSERVED_OR_ROUTED_WITHOUT_QIT_{tid}")
        if tributary.get("routing_method") is None:
            fail(f"OBSERVED_OR_ROUTED_WITHOUT_METHOD_{tid}")
        if not paired and not tributary.get("routing_provenance"):
            fail(f"OBSERVED_OR_ROUTED_WITHOUT_PROVENANCE_{tid}")


def validate_model_gate(model: dict, family: str) -> None:
    method = str(model.get("method") or "")
    status = str(model.get("status") or "")
    bundle = model.get("reproducible_input_bundle")
    if method and family.lower() in method.lower() and bundle is None:
        fail(f"{family.upper()}_WITHOUT_REPRODUCIBLE_INPUT_BUNDLE")
    if any(word in status.upper() for word in ("VALIDATED", "REPRODUCED")) and bundle is None:
        fail(f"{family.upper()}_VALIDATION_CLAIM_WITHOUT_INPUT_BUNDLE")


def validate_demonstrator(demo: dict, arch: dict, hierarchy: dict, spatial: dict) -> dict:
    require_safe(demo, "DEMO")
    if demo.get("parent_id") != "lima_este_santa_eulalia_rimac":
        fail("DEMONSTRATOR_PARENT_DRIFT")
    if demo.get("parent_role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE":
        fail("DEMONSTRATOR_PARENT_ROLE_DRIFT")
    if demo.get("parent_activation_state") is not None:
        fail("DEMONSTRATOR_PARENT_ACTIVATION_ASSIGNED")
    if demo.get("architecture_ref") != "config/phase2_collector_coupling_architecture_v0_1.json":
        fail("DEMONSTRATOR_ARCHITECTURE_REF_DRIFT")
    if demo.get("local_hierarchy_ref") != "config/phase2_local_activation_hierarchy_v0_1.json":
        fail("DEMONSTRATOR_HIERARCHY_REF_DRIFT")

    hierarchy_demo = (hierarchy.get("demonstrators") or {}).get("lima_este_santa_eulalia_rimac") or {}
    registered_children = {x.get("local_unit_id") for x in hierarchy_demo.get("children") or []}
    subunits = spatial_subunits(spatial, demo["parent_id"])

    sources = demo.get("input_sources") or []
    if not sources:
        fail("DEMONSTRATOR_INPUT_SOURCE_MISSING")
    reject_forbidden_sources(sources, "DEMO_INPUTS")
    for source in sources:
        raw = source.get("path")
        if not isinstance(raw, str):
            fail("INPUT_SOURCE_PATH_MISSING")
        path = ROOT / raw
        if not path.is_file():
            fail(f"INPUT_SOURCE_NOT_FOUND_{raw}")
        if source.get("git_blob_sha") != git_blob_sha(path):
            fail(f"INPUT_SOURCE_GIT_BLOB_SHA_DRIFT_{raw}")
        if source.get("outcome_source") is not False:
            fail(f"INPUT_SOURCE_OUTCOME_FLAG_UNSAFE_{raw}")

    collectors = demo.get("collector_targets") or []
    collector_ids = [x.get("collector_id") for x in collectors]
    if len(collector_ids) != len(set(collector_ids)) or any(not x for x in collector_ids):
        fail("COLLECTOR_IDS_INVALID")
    for collector in collectors:
        if collector.get("capacity_status") != "UNKNOWN" and not collector.get("capacity_evidence"):
            fail(f"COLLECTOR_CAPACITY_WITHOUT_VALIDATION_{collector.get('collector_id')}")
        if collector.get("geometry") is None and collector.get("map_eligible") is not False:
            fail(f"MISSING_COLLECTOR_GEOMETRY_MARKED_MAP_ELIGIBLE_{collector.get('collector_id')}")

    tributaries = demo.get("tributaries") or []
    tids = [x.get("local_unit_id") for x in tributaries]
    if len(tids) != len(set(tids)) or any(not x for x in tids):
        fail("TRIBUTARY_IDS_INVALID")
    for tributary in tributaries:
        tid = tributary["local_unit_id"]
        if tid not in registered_children:
            fail(f"TRIBUTARY_NOT_IN_LOCAL_HIERARCHY_{tid}")
        if tid not in subunits:
            fail(f"TRIBUTARY_WITHOUT_REPRODUCIBLE_SPATIAL_SUBUNIT_{tid}")
        if tributary.get("parent_id") != demo["parent_id"]:
            fail(f"TRIBUTARY_PARENT_DRIFT_{tid}")
        validate_source_outlet(tributary, subunits[tid])
        validate_tributary_state(tributary)
        reject_forbidden_sources(tributary.get("receiver_confluence_or_explicit_missing_status"), f"CONFLUENCE_{tid}")
        reject_forbidden_sources(tributary.get("paired_observations"), f"PAIRED_{tid}")

    cells = demo.get("collector_coupling_matrix") or []
    expected_pairs = {(t, c) for t in tids for c in collector_ids}
    pairs = {(x.get("local_unit_id"), x.get("collector_id")) for x in cells}
    if pairs != expected_pairs or len(cells) != len(expected_pairs):
        fail("COUPLING_MATRIX_NOT_COMPLETE_CARTESIAN_PRODUCT")
    by_tid = {x["local_unit_id"]: x for x in tributaries}
    for cell in cells:
        tid = cell["local_unit_id"]
        if cell.get("collector_effect_state") != by_tid[tid].get("collector_effect_state"):
            fail(f"MATRIX_TRIBUTARY_STATE_DRIFT_{tid}")
        if cell.get("collector_effect_state") == "NO_EVIDENCE":
            if cell.get("connectivity") != "UNRESOLVED_NOT_ASSUMED":
                fail(f"MATRIX_NO_EVIDENCE_CONNECTIVITY_ASSUMED_{tid}")
            for field in ("hydraulic_distance", "travel_time_tau", "attenuation_or_storage", "joint_historical_event"):
                if cell.get(field) is not None:
                    fail(f"MATRIX_NO_EVIDENCE_HAS_UNSUPPORTED_{tid}_{field}")
            if cell.get("paired_observations") or cell.get("provenance"):
                fail(f"MATRIX_NO_EVIDENCE_HAS_UNSUPPORTED_PROVENANCE_{tid}")
        reject_forbidden_sources(cell.get("provenance"), f"MATRIX_{tid}")

    balance = demo.get("collector_balance_status") or {}
    if balance.get("calculation_performed") is not False:
        fail("COLLECTOR_BALANCE_CALCULATION_UNEXPECTED")
    for key in ("q_upstream", "q_lateral", "storage_diversions_regulation", "synchrony_analysis", "downstream_flow_estimate"):
        if balance.get(key) is not None:
            fail(f"COLLECTOR_BALANCE_UNSUPPORTED_VALUE_{key}")

    validate_model_gate(demo.get("hydrologic_routing") or {}, "HEC_HMS")
    validate_model_gate(demo.get("hydraulic_model") or {}, "HEC_RAS")
    reject_arbitrary_weight_probability_keys(demo, "DEMO")

    map_updates = demo.get("map_updates") or {}
    if map_updates.get("new_collector_nodes_published") != 0 or map_updates.get("new_collector_reaches_published") != 0:
        fail("MAP_PUBLISHED_UNSUPPORTED_COLLECTOR_GEOMETRY")

    return {
        "parent_id": demo["parent_id"],
        "tributary_count": len(tributaries),
        "collector_target_count": len(collectors),
        "matrix_cell_count": len(cells),
        "effect_state_counts": {state: sum(1 for x in tributaries if x["collector_effect_state"] == state) for state in EFFECT_STATES},
        "routing_models_run": 0,
        "hydraulic_models_run": 0,
        "new_map_geometries": 0,
    }


def build_report() -> dict:
    arch = load(ARCH_PATH)
    hierarchy = load(HIERARCHY_PATH)
    spatial = load(SPATIAL_PATH)
    demo = load(DEMO_PATH)
    validate_architecture(arch, hierarchy)
    summary = validate_demonstrator(demo, arch, hierarchy, spatial)
    return {
        "schema_version": "0.1",
        "status": "PASS_PHASE2_COLLECTOR_COUPLING_FAIL_CLOSED",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "artifacts": {
            "architecture": {"path": ARCH_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(ARCH_PATH)},
            "local_hierarchy": {"path": HIERARCHY_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(HIERARCHY_PATH)},
            "spatial_registry": {"path": SPATIAL_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(SPATIAL_PATH), "git_blob_sha": git_blob_sha(SPATIAL_PATH)},
            "demonstrator": {"path": DEMO_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(DEMO_PATH)},
        },
        "summary": summary,
        "scientific_interpretation": "Architecture and provenance gates passed. No collector contribution, discharge, travel time, capacity, synchrony, overflow, risk or operational state is inferred by this validation.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
