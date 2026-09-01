#!/usr/bin/env python3
"""Audit cached Sentinel-1 R1 reproducibility with explicit numeric tolerance.

This is an engineering reproducibility audit only. It does not alter any
scientific window, threshold, pair identity, geometry, case/control role, or
outcome state. Non-numeric structure and integer counts must match exactly.
Floating diagnostics use a fixed 1e-10 absolute/relative tolerance solely to
allow machine-level floating-point variation across hosted runners.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import ibvf_sentinel1_r1_cache_equivalence as base

ABS_TOL = 1e-10
REL_TOL = 1e-10


def compare(a: Any, b: Any, path: str = "$", diffs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if diffs is None:
        diffs = []
    if isinstance(a, bool) or isinstance(b, bool):
        if type(a) is not type(b) or a != b:
            diffs.append({"path": path, "kind": "exact", "reference": a, "candidate": b})
        return diffs
    if isinstance(a, int) and isinstance(b, int):
        if a != b:
            diffs.append({"path": path, "kind": "integer_exact", "reference": a, "candidate": b})
        return diffs
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        af, bf = float(a), float(b)
        if not (math.isfinite(af) and math.isfinite(bf)):
            if af != bf:
                diffs.append({"path": path, "kind": "nonfinite_exact", "reference": a, "candidate": b})
            return diffs
        abs_diff = abs(af - bf)
        denom = max(abs(af), abs(bf), 1e-300)
        rel_diff = abs_diff / denom
        if not math.isclose(af, bf, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            diffs.append({
                "path": path,
                "kind": "float_tolerance",
                "reference": af,
                "candidate": bf,
                "abs_diff": abs_diff,
                "rel_diff": rel_diff,
            })
        return diffs
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            diffs.append({
                "path": path,
                "kind": "dict_keys_exact",
                "reference_only": sorted(set(a) - set(b)),
                "candidate_only": sorted(set(b) - set(a)),
            })
        for k in sorted(set(a) & set(b)):
            compare(a[k], b[k], f"{path}.{k}", diffs)
        return diffs
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append({"path": path, "kind": "list_length_exact", "reference": len(a), "candidate": len(b)})
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{path}[{i}]", diffs)
        return diffs
    if type(a) is not type(b) or a != b:
        diffs.append({"path": path, "kind": "exact", "reference": a, "candidate": b})
    return diffs


def all_float_deltas(a: Any, b: Any, path: str = "$", out: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if out is None:
        out = []
    if isinstance(a, bool) or isinstance(b, bool):
        return out
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and (isinstance(a, float) or isinstance(b, float)):
        af, bf = float(a), float(b)
        if math.isfinite(af) and math.isfinite(bf):
            ad = abs(af - bf)
            rd = ad / max(abs(af), abs(bf), 1e-300)
            out.append({"path": path, "abs_diff": ad, "rel_diff": rd})
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) & set(b)):
            all_float_deltas(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            all_float_deltas(x, y, f"{path}[{i}]", out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", required=True, type=Path)
    ap.add_argument("--basin", required=True, type=Path)
    ap.add_argument("--reference-r1", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--cache-dir", type=Path)
    args = ap.parse_args()

    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    reference = json.loads(args.reference_r1.read_text(encoding="utf-8"))
    base.guards(freeze)
    base.guards(reference)
    assert freeze["freeze_status"] == "ALL_REQUESTED_ASSETS_SHA256_FROZEN"
    assert reference["r1_status"] == "COMPLETE_BOTH_DATES_NO_COMPARISON"
    assert reference["comparison_performed"] is False
    assert reference["terrain_correction_performed"] is False
    assert reference["common_support_established"] is False
    assert reference["interpretation_forbidden"] is True

    bbox = base.r1.basin_bbox(args.basin)
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        ctx = None
        cache = args.cache_dir
    else:
        ctx = tempfile.TemporaryDirectory(prefix="irfen-ibvf-s1-cache-numeric-audit-")
        cache = Path(ctx.name)
    try:
        candidate: dict[str, Any] = {
            "case_id": freeze.get("case_id"),
            "basin_bbox_lonlat": list(bbox),
            "radiometric_equation": "sigma0_linear=(DN^2-noise_range_lut)/(sigmaNought_calibration_lut^2)",
            "invalid_signal_rule": "DN^2-noise<=0 -> INVALID_NAN_NEVER_ZERO",
        }
        candidate["pre"] = base.materialize_side("pre", freeze["pre"], bbox, cache)
        candidate["post"] = base.materialize_side("post", freeze["post"], bbox, cache)
    finally:
        if ctx is not None:
            ctx.cleanup()

    ref_view = base.scientific_view(reference)
    new_view = base.scientific_view(candidate)
    diffs = compare(ref_view, new_view)
    deltas = all_float_deltas(ref_view, new_view)
    max_abs = max((x["abs_diff"] for x in deltas), default=0.0)
    max_rel = max((x["rel_diff"] for x in deltas), default=0.0)
    exact_equal = ref_view == new_view
    status = "PASS_STRICT_NUMERIC_EQUIVALENCE" if not diffs else "FAIL_REPRODUCIBILITY_DIFFERENCE"

    report = {
        "schema_version": "irfen-ibvf-sentinel1-r1-cache-numeric-audit-v0.1",
        "generated_at": base.now(),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "case_id": freeze.get("case_id"),
        "audit_purpose": "VALIDATE_SINGLE_DOWNLOAD_SHA256_CACHE_WITH_FIXED_MACHINE_NUMERIC_TOLERANCE",
        "absolute_tolerance": ABS_TOL,
        "relative_tolerance": REL_TOL,
        "tolerance_scope": "FLOATING_DIAGNOSTICS_ONLY; NONNUMERIC_STRUCTURE_AND_INTEGER_COUNTS_EXACT",
        "source_freeze_sha256": hashlib.sha256(args.freeze.read_bytes()).hexdigest(),
        "source_reference_r1_sha256": hashlib.sha256(args.reference_r1.read_bytes()).hexdigest(),
        "source_basin_geometry_sha256": hashlib.sha256(args.basin.read_bytes()).hexdigest(),
        "reference_scientific_view_sha256": base.canonical_sha(ref_view),
        "cached_scientific_view_sha256": base.canonical_sha(new_view),
        "scientific_views_bitwise_json_equal": exact_equal,
        "max_absolute_float_difference": max_abs,
        "max_relative_float_difference": max_rel,
        "difference_count_beyond_tolerance": len(diffs),
        "differences_beyond_tolerance": diffs[:100],
        "assets_downloaded_once_per_side_and_key": True,
        "unchanged_science_processor": "scripts/ibvf_sentinel1_r1_radiometric.py::process_native",
        "stac_reselection_performed": False,
        "selected_window_changed": False,
        "compatible_pair_changed": False,
        "radiometric_equation_changed": False,
        "geometry_changed": False,
        "comparison_performed": False,
        "terrain_correction_performed": False,
        "common_support_established": False,
        "rainfall_values_read": False,
        "sar_change_values_used_for_selection": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_assignment_performed": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "equivalence_status": status,
    }
    base.guards(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "equivalence_status": status,
        "bitwise_json_equal": exact_equal,
        "difference_count_beyond_tolerance": len(diffs),
        "max_absolute_float_difference": max_abs,
        "max_relative_float_difference": max_rel,
        "first_differences": diffs[:20],
    }, indent=2))
    return 0 if not diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
