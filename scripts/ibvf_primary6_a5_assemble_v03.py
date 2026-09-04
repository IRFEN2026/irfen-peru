#!/usr/bin/env python3
"""Implementation-only compatibility layer for the frozen PRIMARY6 S1 accounting schema.

The per-window accounting records intentionally carry execution/accounting guards rather
than the full scientific-report guard header. R3/R4 reports still require the full guard
header from v0.1. This wrapper changes no window, pair, feature, threshold, missingness,
or territorial-outcome rule.
"""
from pathlib import Path

import ibvf_primary6_a5_assemble_v02 as v02
import ibvf_primary6_a5_assemble_v01 as base


def assert_accounting_guards(a, source):
    required_false = (
        "r4_feature_magnitudes_used_for_execution_decisions",
        "territorial_outcomes_read",
        "known_event_dates_read",
        "case_control_role_assigned",
        "activation_inference_allowed",
        "modeling_allowed",
    )
    for k in required_false:
        if a.get(k) is not False:
            raise RuntimeError(f"{source}: accounting guard {k}={a.get(k)!r}, expected false")
    if a.get("sar_execution_status") != "COMPATIBLE_PAIR_FROZEN_PENDING_R1_R4":
        raise RuntimeError(f"{source}: unexpected frozen S1 execution status")
    if a.get("r2_status") != "PASS_R2_V02_PRE_POST_INDEPENDENT_SNAP14_CANONICAL_POEORB_VERIFIED_NO_COMPARISON":
        raise RuntimeError(f"{source}: R2 accounting not PASS")
    status = a.get("r1_r4_accounting_status")
    if status not in {
        "PASS_R2_R3_R4_BLIND_ACCOUNTED",
        "PASS_R2_R3_ACCOUNTED_R4_EXPLICIT_UNKNOWN_BY_FROZEN_SUPPORT_GATE",
    }:
        raise RuntimeError(f"{source}: unsupported accounting status {status!r}")
    if status == "PASS_R2_R3_R4_BLIND_ACCOUNTED":
        if a.get("r3_status") != "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY":
            raise RuntimeError(f"{source}: numeric R4 accounting lacks R3 PASS")
        if a.get("r4_status") != "PASS_R4_BLIND_SAR_FEATURE_VECTOR_FROZEN_NO_INFERENCE":
            raise RuntimeError(f"{source}: numeric R4 accounting lacks R4 PASS")
        if not a.get("r4_report_sha256"):
            raise RuntimeError(f"{source}: numeric R4 accounting lacks R4 report hash")
    else:
        if a.get("r3_status") != "UNKNOWN_INSUFFICIENT_COMMON_SUPPORT":
            raise RuntimeError(f"{source}: explicit-UNKNOWN accounting lacks frozen R3 UNKNOWN")
        if a.get("r4_status") != "NOT_COMPUTED_EXPLICIT_R3_UNKNOWN" or a.get("r4_report_sha256") is not None:
            raise RuntimeError(f"{source}: explicit-UNKNOWN accounting improperly carries R4")


def s1_index(root):
    idx = {}
    for p in Path(root).rglob("accounting.json"):
        a = base.load_json(p)
        assert_accounting_guards(a, str(p))
        key = (a["unit_id"], a["season_id"], a["date_local"])
        if key in idx:
            raise RuntimeError(f"Duplicate S1 accounting key {key}")
        r4p, r3p = p.parent / "r4-v02.json", p.parent / "r3-v02.json"
        rec = {"accounting": a, "accounting_path": str(p)}
        if r4p.exists():
            r4 = base.load_json(r4p)
            base.assert_guards(r4, str(r4p))
            if base.sha256_file(r4p) != a["r4_report_sha256"]:
                raise RuntimeError(f"{key}: R4 report SHA-256 differs from accounting")
            rec["r4"] = r4
        elif r3p.exists():
            r3 = base.load_json(r3p)
            base.assert_guards(r3, str(r3p))
            if base.sha256_file(r3p) != a["r3_report_sha256"]:
                raise RuntimeError(f"{key}: R3 report SHA-256 differs from accounting")
            rec["r3"] = r3
        else:
            raise RuntimeError(f"Compatible S1 window lacks R3/R4 evidence: {key}")
        idx[key] = rec
    return idx


# Preserve the v0.2 GeoJSON-container correction and replace only S1 accounting parsing.
base.selected_feature = v02.selected_feature
base.s1_index = s1_index

if __name__ == "__main__":
    base.main()
