#!/usr/bin/env python3
"""Compute pre-registered Sentinel-1 R4 observational change features.

RESEARCH_ONLY / TEST_ONLY. This script may run only after the frozen R3 common
support gate passes. It computes the exact feature set in
``ibvf_sentinel1_r4_change_contract.json`` on the R3 common-support mask. It
never assigns activation, risk, alert, or case/control role.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_sha256(path: Path) -> str:
    obj = json.loads(path.read_text(encoding="utf-8"))
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def same_grid(a: rasterio.DatasetReader, b: rasterio.DatasetReader, tol: float = 1e-9) -> bool:
    return (
        a.crs == b.crs
        and a.width == b.width
        and a.height == b.height
        and all(abs(float(x) - float(y)) <= tol for x, y in zip(tuple(a.transform), tuple(b.transform)))
    )


def largest_8connected(mask: np.ndarray) -> int:
    """Return largest 8-connected True component size without morphology."""
    h, w = mask.shape
    visited = np.zeros(mask.shape, dtype=np.uint8)
    largest = 0
    rows, cols = np.nonzero(mask)
    for r0, c0 in zip(rows.tolist(), cols.tolist()):
        if visited[r0, c0]:
            continue
        visited[r0, c0] = 1
        q: deque[tuple[int, int]] = deque([(r0, c0)])
        size = 0
        while q:
            r, c = q.popleft()
            size += 1
            rmin, rmax = max(0, r - 1), min(h - 1, r + 1)
            cmin, cmax = max(0, c - 1), min(w - 1, c + 1)
            for rr in range(rmin, rmax + 1):
                for cc in range(cmin, cmax + 1):
                    if rr == r and cc == c:
                        continue
                    if mask[rr, cc] and not visited[rr, cc]:
                        visited[rr, cc] = 1
                        q.append((rr, cc))
        if size > largest:
            largest = size
    return largest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--r3-report", type=Path, required=True)
    ap.add_argument("--pre-crop", type=Path, required=True)
    ap.add_argument("--post-crop", type=Path, required=True)
    ap.add_argument("--support-mask", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    r3 = json.loads(args.r3_report.read_text(encoding="utf-8"))
    for d in (contract, r3):
        assert d["deployment_status"] == "RESEARCH_ONLY"
        assert d["production_use"] is False and d["production_ready"] is False and d["operational_alerting_enabled"] is False
        assert d["uses_operational_event_none_labels"] is False and d["territorial_activation_evidence_blinded"] is True
        assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"
    assert contract["execution_status"] == "PREREGISTERED_BEFORE_R3_RESULT_AND_BEFORE_ANY_R4_CHANGE_VALUE"
    assert contract["fixed_change_threshold_db"]["threshold_tuned_on_data"] is False
    required_r3 = "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY"
    if r3.get("status") != required_r3 or not r3.get("common_support_gate_pass") or float(r3.get("common_support_fraction", 0)) < float(contract["execution_prerequisites"]["minimum_common_support_fraction"]):
        raise SystemExit("R4 blocked: preregistered R3 common-support gate has not passed")
    assert r3["radiometric_difference_statistics_computed"] is False
    assert r3["r4_difference_computed"] is False
    assert r3["activation_inference_allowed"] is False

    expected_pre = r3["lossless_basin_crops"]["pre"]["sha256"]
    expected_post = r3["lossless_basin_crops"]["post"]["sha256"]
    expected_mask = r3["common_support_mask"]["sha256"]
    actual_pre = sha256_file(args.pre_crop)
    actual_post = sha256_file(args.post_crop)
    actual_mask = sha256_file(args.support_mask)
    if (actual_pre, actual_post, actual_mask) != (expected_pre, expected_post, expected_mask):
        raise ValueError("R4 input hashes do not match frozen R3 evidence")

    with rasterio.open(args.pre_crop) as pre_ds, rasterio.open(args.post_crop) as post_ds, rasterio.open(args.support_mask) as mask_ds:
        if not same_grid(pre_ds, post_ds) or not same_grid(pre_ds, mask_ds):
            raise ValueError("R4 input grids differ; post-hoc resampling is forbidden")
        pre = pre_ds.read(1, masked=False).astype("float64", copy=False)
        post = post_ds.read(1, masked=False).astype("float64", copy=False)
        support = mask_ds.read(1, masked=False) == 1

    n = int(support.sum())
    if n != int(r3["common_valid_pixel_count"]):
        raise ValueError(f"support mask count {n} differs from R3 common_valid_pixel_count {r3['common_valid_pixel_count']}")
    if n <= 0:
        raise ValueError("common support is empty")
    pre_v = pre[support]
    post_v = post[support]
    if not (np.all(np.isfinite(pre_v)) and np.all(np.isfinite(post_v)) and np.all(pre_v > 0) and np.all(post_v > 0)):
        raise ValueError("R4 support contains invalid/non-positive linear Gamma0 despite R3")

    pre_db = 10.0 * np.log10(pre_v)
    post_db = 10.0 * np.log10(post_v)
    delta = post_db - pre_db
    abs_delta = np.abs(delta)
    threshold = float(contract["fixed_change_threshold_db"]["absolute_value"])
    changed = abs_delta >= threshold
    negative = delta <= -threshold
    positive = delta >= threshold

    # Reconstruct changed mask strictly on the frozen R3 support grid for the
    # fixed 8-connected component metric. No opening/closing or size filtering.
    changed_grid = np.zeros(support.shape, dtype=bool)
    changed_grid[support] = changed
    largest = largest_8connected(changed_grid)

    dq = [float(x) for x in contract["fixed_diagnostic_quantiles"]["delta_db"]]
    aq = [float(x) for x in contract["fixed_diagnostic_quantiles"]["absolute_delta_db"]]
    delta_quantiles = {str(q): float(np.quantile(delta, q)) for q in dq}
    abs_quantiles = {str(q): float(np.quantile(abs_delta, q)) for q in aq}

    features = {
        "S1_DELTA_DB_MEDIAN": float(np.median(delta)),
        "S1_ABS_DELTA_DB_MEDIAN": float(np.median(abs_delta)),
        "S1_ABS_DELTA_GE_3DB_FRACTION": float(changed.sum() / n),
        "S1_DELTA_LE_MINUS3DB_FRACTION": float(negative.sum() / n),
        "S1_DELTA_GE_PLUS3DB_FRACTION": float(positive.sum() / n),
        "S1_ABS_DELTA_GE_3DB_LARGEST_8CONNECTED_FRACTION": float(largest / n),
    }
    expected_ids = [x["id"] for x in contract["primary_features"]]
    if list(features) != expected_ids:
        raise ValueError("implemented R4 feature ordering/identity differs from frozen contract")

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-sentinel1-r4-change-v0.1",
        "generated_at": now(),
        "case_id": r3["case_id"],
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "semantics": contract["r4_output_semantics"],
        "inputs": {
            "pre_crop_sha256": actual_pre,
            "post_crop_sha256": actual_post,
            "common_support_mask_sha256": actual_mask,
            "r3_report_sha256": sha256_file(args.r3_report),
            "metric_contract_sha256": canonical_json_sha256(args.contract),
            "common_support_pixel_count": n,
            "common_support_fraction": float(r3["common_support_fraction"]),
        },
        "radiometric_domain": "DB_FROM_LINEAR_TERRAIN_FLATTENED_GAMMA0",
        "delta_definition": "POST_DB_MINUS_PRE_DB",
        "fixed_absolute_change_threshold_db": threshold,
        "primary_features": features,
        "diagnostic_quantiles": {
            "delta_db": delta_quantiles,
            "absolute_delta_db": abs_quantiles,
        },
        "largest_8connected_changed_pixel_count": int(largest),
        "smoothing_applied": False,
        "speckle_filter_applied_after_r2": False,
        "morphological_filter_applied": False,
        "post_hoc_resampling_applied": False,
        "r4_difference_computed": True,
        "feature_vector_frozen": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "risk_or_alert_generated": False,
        "status": "PASS_R4_PREREGISTERED_REMOTE_OBSERVATIONAL_FEATURES_FROZEN_NO_OUTCOME_INTERPRETATION",
        "next_gate": "A5_HASH_REMOTE_FEATURE_VECTOR_THEN_ONLY_LATER_INDEPENDENT_TERRITORIAL_UNBLIND_PER_PROTOCOL"
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "common_support_pixel_count": n, "primary_features": features}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
