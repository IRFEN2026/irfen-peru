#!/usr/bin/env python3
"""Compute the frozen five-feature PRIMARY6 Sentinel-1 R4 vector, blind.

RESEARCH_ONLY / TEST_ONLY. Runs only after the inherited R3 spatial-support
gate passes. It computes exactly the five Cashahuacra-preregistered metrics
under the global PRIMARY6 execution contract, with no outcome read, no
case/control assignment, and no magnitude-based decision.
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


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def guard(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True


def raster_identity(a: rasterio.DatasetReader, b: rasterio.DatasetReader) -> bool:
    return a.crs == b.crs and a.width == b.width and a.height == b.height and tuple(a.transform) == tuple(b.transform)


def largest_cluster(mask: np.ndarray) -> tuple[int, int]:
    if mask.ndim != 2:
        raise ValueError("cluster mask must be 2-D")
    h, w = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    largest = 0
    n_components = 0
    offsets = ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        n_components += 1
        seen[y0, x0] = True
        q: deque[tuple[int, int]] = deque([(y0, x0)])
        size = 0
        while q:
            y, x = q.pop()
            size += 1
            for dy, dx in offsets:
                yy, xx = y + dy, x + dx
                if yy < 0 or yy >= h or xx < 0 or xx >= w:
                    continue
                if mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    q.append((yy, xx))
        largest = max(largest, size)
    return largest, n_components


def write_delta(src: rasterio.DatasetReader, delta: np.ndarray, common: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.full(delta.shape, np.nan, dtype="float32")
    out[common] = delta[common].astype("float32")
    profile = src.profile.copy()
    profile.update(driver="GTiff", dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(out, 1)
            dst.write_mask(common.astype("uint8") * 255)


def write_factor2(src: rasterio.DatasetReader, changed: np.ndarray, common: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.full(changed.shape, 255, dtype="uint8")
    out[common] = changed[common].astype("uint8")
    profile = src.profile.copy()
    profile.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(out, 1)
            dst.write_mask(common.astype("uint8") * 255)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--global-contract", type=Path, required=True)
    ap.add_argument("--anchor-r4-contract", type=Path, required=True)
    ap.add_argument("--r3-report", type=Path, required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--common-mask", type=Path, required=True)
    ap.add_argument("--delta-output", type=Path, required=True)
    ap.add_argument("--factor2-mask-output", type=Path, required=True)
    ap.add_argument("--report-output", type=Path, required=True)
    args = ap.parse_args()

    global_contract = load(args.global_contract)
    anchor = load(args.anchor_r4_contract)
    r3 = load(args.r3_report)
    for d in (global_contract, anchor, r3):
        guard(d)
    if global_contract["inheritance"]["cashahuacra_anchor_r4_feature_definitions_changed"] is not False:
        raise SystemExit("global contract does not preserve anchor R4 definitions")
    if r3["case_id"] != args.case_id:
        raise SystemExit("R3 case identity mismatch")
    if r3["status"] != "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY":
        raise SystemExit("R4 blocked: R3 support gate has not passed")
    if not r3["r3_common_support_built"] or not r3["common_support_gate_pass"]:
        raise SystemExit("R4 blocked: R3 support evidence incomplete")
    if float(r3["common_support_fraction"]) < float(global_contract["r3_rule"]["minimum_common_support_fraction"]):
        raise SystemExit("R4 blocked: R3 support below global threshold")
    assert r3["radiometric_difference_statistics_computed"] is False
    assert r3["comparison_performed"] is False
    assert r3["r4_difference_computed"] is False
    assert r3["territorial_outcomes_read"] is False
    assert r3["case_control_role_assigned"] is False

    frozen_names = [x["id"] for x in anchor["primary_r4_feature_vector"]]
    if frozen_names != global_contract["r4_rule"]["primary_features"]:
        raise SystemExit("global/anchor R4 primary feature list mismatch")
    threshold = float(anchor["factor_two_threshold"]["absolute_db"])
    if threshold != float(global_contract["r4_rule"]["factor_two_absolute_db"]):
        raise SystemExit("global/anchor factor-two threshold mismatch")
    if anchor["cluster_contract"]["connectivity"] != 8 or anchor["cluster_contract"]["minimum_cluster_size_filter"] != 0:
        raise SystemExit("anchor cluster contract changed")
    if anchor["cluster_contract"]["morphological_cleanup"] is not False:
        raise SystemExit("anchor morphology contract changed")

    expected = {
        "pre": r3["pre_lossless_crop"]["sha256"],
        "post": r3["post_lossless_crop"]["sha256"],
        "mask": r3["common_support_mask"]["sha256"],
    }
    actual = {
        "pre": sha256_file(args.pre),
        "post": sha256_file(args.post),
        "mask": sha256_file(args.common_mask),
    }
    if expected != actual:
        raise SystemExit("R4 blocked: R3 frozen artifact identity mismatch")

    with rasterio.open(args.pre) as pre_ds, rasterio.open(args.post) as post_ds, rasterio.open(args.common_mask) as mask_ds:
        if not raster_identity(pre_ds, post_ds) or not raster_identity(pre_ds, mask_ds):
            raise SystemExit("R4 blocked: R3 crops/mask lack exact grid identity")
        pre = pre_ds.read(1, masked=False).astype("float64")
        post = post_ds.read(1, masked=False).astype("float64")
        common = mask_ds.read(1, masked=False) == 1
        common_count = int(common.sum())
        if common_count != int(r3["common_support_pixel_count"]):
            raise SystemExit("R4 blocked: common support count changed")
        if not np.all(np.isfinite(pre[common])) or not np.all(np.isfinite(post[common])):
            raise SystemExit("R4 blocked: non-finite Gamma0 inside support")
        if not np.all(pre[common] > 0) or not np.all(post[common] > 0):
            raise SystemExit("R4 blocked: non-positive Gamma0 inside support")

        delta = np.full(pre.shape, np.nan, dtype="float64")
        delta[common] = 10.0 * np.log10(post[common] / pre[common])
        values = delta[common]
        if values.size != common_count or not np.all(np.isfinite(values)):
            raise SystemExit("R4 blocked: invalid delta values")

        qs = np.quantile(values, [0.05,0.10,0.25,0.50,0.75,0.90,0.95], method="linear")
        p05,p10,p25,p50,p75,p90,p95 = [float(x) for x in qs]
        decreased = common & (delta <= -threshold)
        increased = common & (delta >= threshold)
        factor2 = common & (np.abs(delta) >= threshold)
        dec_count = int(decreased.sum())
        inc_count = int(increased.sum())
        factor_count = int(factor2.sum())
        largest, component_count = largest_cluster(factor2)

        metrics = {
            "MEDIAN_DELTA_DB": p50,
            "IQR_DELTA_DB": p75 - p25,
            "DECREASE_FACTOR2_FRACTION": dec_count / common_count,
            "INCREASE_FACTOR2_FRACTION": inc_count / common_count,
            "LARGEST_FACTOR2_CLUSTER_FRACTION": largest / common_count,
        }
        diagnostics = {
            "P05_DELTA_DB": p05,
            "P10_DELTA_DB": p10,
            "P25_DELTA_DB": p25,
            "P50_DELTA_DB": p50,
            "P75_DELTA_DB": p75,
            "P90_DELTA_DB": p90,
            "P95_DELTA_DB": p95,
            "ABS_FACTOR2_FRACTION": factor_count / common_count,
            "LARGEST_FACTOR2_CLUSTER_PIXEL_COUNT": largest,
            "NUMBER_OF_FACTOR2_CLUSTERS": component_count,
        }
        write_delta(pre_ds, delta, common, args.delta_output)
        write_factor2(pre_ds, factor2, common, args.factor2_mask_output)

    report = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-r4-v0.1",
        "generated_at": now(),
        "case_id": args.case_id,
        "unit_id": r3["unit_id"],
        "season_id": r3["season_id"],
        "date_local": r3["date_local"],
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "global_contract_sha256": sha256_file(args.global_contract),
        "anchor_r4_contract_sha256": sha256_file(args.anchor_r4_contract),
        "r3_report_sha256": sha256_file(args.r3_report),
        "r3_artifact_identities": actual,
        "common_support_fraction": float(r3["common_support_fraction"]),
        "common_support_pixel_count": common_count,
        "delta_definition": global_contract["r4_rule"]["delta_definition"],
        "factor_two_threshold_db": threshold,
        "quantile_method": "numpy_quantile_linear",
        "primary_r4_feature_vector": metrics,
        "fixed_diagnostics": diagnostics,
        "delta_db_geotiff": {
            "path": str(args.delta_output),
            "bytes": args.delta_output.stat().st_size,
            "sha256": sha256_file(args.delta_output),
            "masked_outside_common_support": True,
        },
        "factor2_binary_mask": {
            "path": str(args.factor2_mask_output),
            "bytes": args.factor2_mask_output.stat().st_size,
            "sha256": sha256_file(args.factor2_mask_output),
            "masked_outside_common_support": True,
            "connectivity_for_cluster_metric": 8,
            "morphological_cleanup_performed": False,
        },
        "clipping_performed": False,
        "smoothing_performed": False,
        "additional_resampling_performed": False,
        "posthoc_terrain_or_landcover_masking_performed": False,
        "r4_difference_computed": True,
        "r4_is_observational_not_decisional": True,
        "r4_feature_magnitude_pass_fail_threshold": None,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "risk_classification_computed": False,
        "alert_value_computed": False,
        "status": "PASS_R4_BLIND_SAR_FEATURE_VECTOR_FROZEN_NO_INFERENCE",
        "next_gate": "CONTINUE_SAME_FROZEN_R2_R3_R4_CONTRACT_ACROSS_ALL_PRIMARY6_COMPATIBLE_WINDOWS_BEFORE_A5_AND_UNBLIND"
    }
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "case_id": args.case_id,
        "primary_feature_count": len(metrics),
        "activation_inference_allowed": False
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
