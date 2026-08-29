#!/usr/bin/env python3
"""Validate the independent-basin multipista manifest guardrails.

RESEARCH_ONLY / TEST_ONLY. This validator is intentionally structural: it does
not infer activation, risk, or scientific outcome. Its purpose is to prevent
case-by-case contract drift while the blind remote assessment grows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_CASE_FIELDS = {
    "case_id", "unit_id", "name", "blind_window", "framework_stage",
    "geometry_status", "geometry_path", "imerg_status", "remote_sensing_status",
    "smap_status", "blind_status", "production_use", "production_ready",
    "operational_alerting_enabled",
}
FORBIDDEN_CASE_KEYS = {
    "event_label", "event_none", "operational_label", "risk", "risk_score",
    "risk_class", "alert", "alert_level", "priority", "priority_score",
    "activation_label", "activation_probability", "operational_threshold",
}
ALLOWED_BLIND_STATUS = {"TERRITORIAL_EVIDENCE_SEALED"}


def walk_keys(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k).lower())
            out.update(walk_keys(v))
    elif isinstance(obj, list):
        for v in obj:
            out.update(walk_keys(v))
    return out


def validate(path: Path) -> dict[str, Any]:
    d = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    top_expected = {
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
    }
    for k, expected in top_expected.items():
        if d.get(k) != expected:
            errors.append(f"top-level {k}={d.get(k)!r}, expected {expected!r}")

    guard = d.get("guardrails") or {}
    for k in (
        "no_risk_colors", "no_operational_thresholds", "no_alert_values",
        "missing_is_never_zero", "unknown_is_preserved",
        "map_does_not_enter_operational_calculation",
        "case_role_is_not_inferred_from_territorial_outcome",
    ):
        if guard.get(k) is not True:
            errors.append(f"guardrail {k} must be true")

    cases = d.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
        cases = []

    seen: set[str] = set()
    for i, case in enumerate(cases):
        cid = case.get("case_id", f"index-{i}")
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{cid}: missing required fields {missing}")
        if cid in seen:
            errors.append(f"duplicate case_id {cid}")
        seen.add(cid)
        if case.get("production_use") is not False:
            errors.append(f"{cid}: production_use must be false")
        if case.get("production_ready") is not False:
            errors.append(f"{cid}: production_ready must be false")
        if case.get("operational_alerting_enabled") is not False:
            errors.append(f"{cid}: operational_alerting_enabled must be false")
        if case.get("blind_status") not in ALLOWED_BLIND_STATUS:
            errors.append(f"{cid}: blind_status must remain TERRITORIAL_EVIDENCE_SEALED")
        forbidden = sorted(FORBIDDEN_CASE_KEYS & walk_keys(case))
        if forbidden:
            errors.append(f"{cid}: forbidden operational/result keys {forbidden}")
        if case.get("unit_id") == "cashahuacra" and case.get("smap_status") != "MISSING_FOR_EVENT_WINDOW":
            errors.append("cashahuacra: SMAP must remain MISSING_FOR_EVENT_WINDOW")
        if case.get("blind_window") == "NOT_YET_FROZEN" and case.get("framework_stage") not in {
            "PARALLEL_INTAKE", "PARALLEL_GEOMETRY_RESOLUTION"
        }:
            errors.append(f"{cid}: unfrozen blind window cannot advance beyond parallel intake/geometry resolution")

    return {
        "manifest": str(path),
        "case_count": len(cases),
        "case_ids": [c.get("case_id") for c in cases],
        "valid": not errors,
        "errors": errors,
        "guardrail_mode": "RESEARCH_ONLY_TEST_ONLY_NO_OPERATIONAL_LABELS",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    args = ap.parse_args()
    result = validate(args.manifest)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
