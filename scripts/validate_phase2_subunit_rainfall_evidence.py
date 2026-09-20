#!/usr/bin/env python3
"""Validate Claude G Phase-2 subunit rainfall evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/phase2/subunit_rainfall_evidence_v0_1.json"
LATE = ROOT / "site/data/phase2/subunit_imerg_late_v0_1.json"
SPATIAL = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
CLIMATE_MATRIX = ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"

ERRORS = []


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"cannot read {path.relative_to(ROOT)}: {exc}")
        return None


def optional(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def expected_target_ids(spatial):
    out = set()
    for candidate in spatial.get("candidate_records") or []:
        for contract in candidate.get("subunit_contracts") or []:
            if contract.get("contract_status") != "RESEARCH_SAMPLING_ELIGIBLE":
                continue
            out.add(
                f"phase2_subunit:{candidate.get('candidate_id')}:{contract.get('subunit_id')}"
            )
    return out


def check_phase2_guardrails(catalog, climate_matrix):
    zones = catalog.get("zones") or []
    if len(zones) != 18:
        ERRORS.append(f"Phase-2 registered candidate count changed: {len(zones)}")
    if (catalog.get("summary") or {}).get("contracts_approved") != 0:
        ERRORS.append("contracts_approved must remain 0")
    if (catalog.get("summary") or {}).get("operational_candidates") != 0:
        ERRORS.append("operational_candidates must remain 0")
    if any(zone.get("activation_gate") != "BLOCKED" for zone in zones):
        ERRORS.append("all Phase-2 activation gates must remain BLOCKED")
    if any((zone.get("promotion_gate") or {}).get("promotion_gate_met") is True for zone in zones):
        ERRORS.append("no Phase-2 promotion gate may be met")
    if catalog.get("production_use") is not False or catalog.get("production_ready") is not False:
        ERRORS.append("Phase-2 production flags changed")
    if (catalog.get("guardrails") or {}).get("alerts_disabled") is not True:
        ERRORS.append("Phase-2 alert guardrail changed")

    records = climate_matrix.get("records") or []
    if len(records) != 18:
        ERRORS.append("Claude D matrix must remain at 18 candidates")
    for record in records:
        assessment = record.get("physical_plausibility_assessment") or {}
        if assessment.get("classification_method_status") != "NOT_YET_CALIBRATED":
            ERRORS.append(f"{record.get('candidate_id')}: Claude D unexpectedly calibrated")
        if assessment.get("physical_response_plausibility_score") is not None:
            ERRORS.append(f"{record.get('candidate_id')}: plausibility score unexpectedly populated")


def check_spatial(spatial):
    summary = spatial.get("summary") or {}
    if summary.get("research_subunit_contract_count") != 2:
        ERRORS.append("Claude F research subunit count must remain 2")
    if summary.get("candidate_wide_ready_count") != 0:
        ERRORS.append("candidate-wide spatial readiness must remain 0")
    if summary.get("operational_spatial_contract_count") != 0:
        ERRORS.append("operational spatial contract count must remain 0")


def check_late(late, expected):
    if not late:
        return
    if late.get("deployment_status") != "RESEARCH_ONLY":
        ERRORS.append("Late artifact must remain RESEARCH_ONLY")
    if late.get("production_use") is not False or late.get("production_ready") is not False:
        ERRORS.append("Late artifact production flags must remain false")
    if late.get("activation_gate") != "BLOCKED":
        ERRORS.append("Late artifact activation gate must remain BLOCKED")
    actual = {row.get("target_id") for row in late.get("targets") or []}
    if actual and actual != expected:
        ERRORS.append(f"Late target set mismatch: {sorted(actual)}")
    for row in late.get("targets") or []:
        for window_id, window in (row.get("windows") or {}).items():
            available = window.get("available") is True
            accum = window.get("accum_mm")
            if available and accum is None:
                ERRORS.append(f"{row.get('target_id')}/{window_id}: available without accumulation")
            if not available and accum is not None:
                ERRORS.append(f"{row.get('target_id')}/{window_id}: unavailable with accumulation")


def check_consolidated(result, expected):
    if result.get("deployment_status") != "RESEARCH_ONLY":
        ERRORS.append("consolidated artifact must remain RESEARCH_ONLY")
    if result.get("production_use") is not False or result.get("production_ready") is not False:
        ERRORS.append("consolidated production flags must remain false")
    if result.get("operational_alerting_enabled") is not False:
        ERRORS.append("operational alerting must remain false")
    if result.get("activation_gate") != "BLOCKED":
        ERRORS.append("consolidated activation gate must remain BLOCKED")
    if result.get("decision_thresholds") is not None:
        ERRORS.append("decision thresholds must remain null")

    rows = result.get("targets") or []
    actual = {row.get("target_id") for row in rows}
    if actual != expected:
        ERRORS.append(f"consolidated target set mismatch: {sorted(actual)}")
    if len(rows) != 2:
        ERRORS.append(f"expected 2 research subunit rows, found {len(rows)}")

    for row in rows:
        tid = row.get("target_id")
        if row.get("deployment_status") != "RESEARCH_ONLY":
            ERRORS.append(f"{tid}: must remain RESEARCH_ONLY")
        if row.get("counts_as_candidate_wide_rainfall") is not False:
            ERRORS.append(f"{tid}: must not count as candidate-wide rainfall")
        if row.get("counts_as_operational_evidence") is not False:
            ERRORS.append(f"{tid}: must not count as operational evidence")

        early = ((row.get("near_real_time_imerg_early") or {}).get("windows") or {})
        for window_id, window in early.items():
            available = window.get("available") is True
            accum = window.get("accum_mm")
            status = window.get("evidence_status")
            if available:
                if window.get("continuous") is not True or accum is None:
                    ERRORS.append(f"{tid}/{window_id}: Early available state is incomplete")
                if status != "OBSERVED_NEAR_REAL_TIME":
                    ERRORS.append(f"{tid}/{window_id}: Early status mismatch")
            else:
                if accum is not None:
                    ERRORS.append(f"{tid}/{window_id}: Early unavailable accumulation must be null")
                if status != "INSUFFICIENT_EVIDENCE":
                    ERRORS.append(f"{tid}/{window_id}: missing Early evidence status mismatch")

        daily = ((row.get("daily_imerg_late") or {}).get("windows") or {})
        for window_id, window in daily.items():
            available = window.get("available") is True
            accum = window.get("accum_mm")
            status = window.get("evidence_status")
            if available:
                if accum is None or status != "OBSERVED_DAILY_SATELLITE":
                    ERRORS.append(f"{tid}/{window_id}: Late available state mismatch")
            else:
                if accum is not None or status != "INSUFFICIENT_EVIDENCE":
                    ERRORS.append(f"{tid}/{window_id}: Late unavailable state mismatch")

    summary = result.get("summary") or {}
    if summary.get("research_subunit_count") != 2:
        ERRORS.append("summary research_subunit_count must be 2")
    for key in (
        "candidate_wide_rainfall_outputs",
        "operational_activations",
        "thresholds_created",
    ):
        if summary.get(key) != 0:
            ERRORS.append(f"summary.{key} must remain 0")


def walk_forbidden(node, path="root"):
    forbidden = {
        "risk_score",
        "activation_score",
        "alert_score",
        "physical_response_plausibility_score",
        "promotion_gate_met",
        "decision_threshold_mm",
        "activation_threshold_mm",
    }
    if isinstance(node, dict):
        for key, value in node.items():
            if key in forbidden:
                ERRORS.append(f"forbidden decision key in rainfall evidence: {path}.{key}")
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
    import build_phase2_subunit_rainfall_evidence as builder

    fresh = builder.generate(write=False)
    left = dict(result)
    right = dict(fresh)
    left.pop("generated_at", None)
    right.pop("generated_at", None)
    if left != right:
        ERRORS.append(
            "committed consolidated rainfall evidence differs from regeneration: "
            + (first_difference(left, right) or "unknown difference")
        )


def main():
    ERRORS.clear()
    result = load(OUT)
    spatial = load(SPATIAL)
    catalog = load(CATALOG)
    climate_matrix = load(CLIMATE_MATRIX)
    late = optional(LATE)
    if any(value is None for value in (result, spatial, catalog, climate_matrix)):
        for error in ERRORS:
            print("ERROR:", error)
        return 1

    expected = expected_target_ids(spatial)
    if len(expected) != 2:
        ERRORS.append(f"expected exactly 2 research subunit target ids, found {len(expected)}")

    check_phase2_guardrails(catalog, climate_matrix)
    check_spatial(spatial)
    check_late(late, expected)
    check_consolidated(result, expected)
    walk_forbidden(result)
    check_determinism(result)

    for error in ERRORS:
        print("ERROR:", error)
    if ERRORS:
        print(f"validate_phase2_subunit_rainfall_evidence: FAILED with {len(ERRORS)} error(s).")
        return 1
    print("validate_phase2_subunit_rainfall_evidence: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
