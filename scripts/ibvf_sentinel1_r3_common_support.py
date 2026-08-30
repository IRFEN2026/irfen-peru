#!/usr/bin/env python3
"""Build Cashahuacra Sentinel-1 R3 common support without change metrics.

RESEARCH_ONLY / TEST_ONLY. Enforces the pre-registered R3 spatial-support
contract. Pixel values are inspected only to establish per-date validity
(finite, dataset-valid, linear Gamma0 > 0). It does not calculate, report, or
persist any pre/post radiometric difference statistic.

To avoid multi-GB R2 artifacts, the script derives one deterministic target-
grid window solely from the frozen basin geometry and writes lossless pre and
post crops with no resampling or radiometric transformation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_window, rasterize
from rasterio.warp import transform_geom


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def select_geometry(path: Path, prop: str, value: str) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    features = doc.get("features", []) if doc.get("type") == "FeatureCollection" else [doc]
    matches = [f for f in features if (f.get("properties") or {}).get(prop) == value]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one basin feature for {prop}={value}, got {len(matches)}")
    geom = matches[0].get("geometry")
    if not geom:
        raise ValueError("selected basin feature has no geometry")
    return geom


def transform_equal(a: rasterio.Affine, b: rasterio.Affine, tol: float) -> bool:
    return all(abs(float(x) - float(y)) <= tol for x, y in zip(tuple(a), tuple(b)))


def write_lossless_crop(src: rasterio.DatasetReader, arr: np.ndarray, mask: np.ndarray, window: rasterio.windows.Window, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = src.profile.copy()
    profile.update(
        driver="GTiff",
        width=int(window.width),
        height=int(window.height),
        transform=src.window_transform(window),
        count=1,
        dtype=src.dtypes[0],
        compress="deflate",
    )
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr.astype(src.dtypes[0], copy=False), 1)
            dst.write_mask(mask.astype("uint8", copy=False))
    with rasterio.open(path) as check:
        reread = check.read(1, masked=False)
        remask = check.dataset_mask()
        if not np.array_equal(reread, arr.astype(src.dtypes[0], copy=False), equal_nan=True):
            raise ValueError(f"lossless crop pixel identity check failed for {path}")
        if not np.array_equal(remask, mask.astype("uint8", copy=False)):
            raise ValueError(f"lossless crop mask identity check failed for {path}")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "dtype": src.dtypes[0],
        "nodata": src.nodata,
        "pixel_identity_check": "PASS_EXACT_ARRAY_EQUAL",
        "mask_identity_check": "PASS_EXACT_ARRAY_EQUAL",
    }


def blocked_report(args: argparse.Namespace, contract: dict[str, Any], status: str) -> int:
    report = {
        "schema_version": "irfen-ibvf-cashahuacra-sentinel1-r3-v0.2",
        "generated_at": now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "status": status,
        "grid_identity_pass": False,
        "r3_common_support_built": False,
        "r4_difference_computed": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
    }
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(status)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--r2-report", type=Path, required=True)
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--basin", type=Path, required=True)
    ap.add_argument("--pre-crop-output", type=Path, required=True)
    ap.add_argument("--post-crop-output", type=Path, required=True)
    ap.add_argument("--mask-output", type=Path, required=True)
    ap.add_argument("--report-output", type=Path, required=True)
    args = ap.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    r2 = json.loads(args.r2_report.read_text(encoding="utf-8"))
    for d in (contract, r2):
        assert d["deployment_status"] == "RESEARCH_ONLY"
        assert d["production_use"] is False and d["production_ready"] is False and d["operational_alerting_enabled"] is False
        assert d["uses_operational_event_none_labels"] is False and d["territorial_activation_evidence_blinded"] is True
        assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"
    required = contract["r2_prerequisite_status_required"]
    if r2.get("status") != required or not r2.get("r2_processing_executed") or not r2.get("poeorb_consumption_verified_both_dates"):
        raise SystemExit("R3 blocked: R2 exact-graph + precise-orbit consumption gate has not passed")
    assert r2["comparison_performed"] is False and r2["r4_difference_computed"] is False

    tol = float(contract["grid_identity_gate"]["transform_absolute_tolerance"])
    with rasterio.open(args.pre) as pre_ds, rasterio.open(args.post) as post_ds:
        grid_equal = (
            pre_ds.crs == post_ds.crs
            and pre_ds.width == post_ds.width
            and pre_ds.height == post_ds.height
            and transform_equal(pre_ds.transform, post_ds.transform, tol)
        )
        if not grid_equal:
            return blocked_report(args, contract, contract["grid_identity_gate"]["grid_mismatch"])

        geom = select_geometry(args.basin, contract["basin_geometry"]["selector_property"], contract["basin_geometry"]["selector_value"])
        geom_in_crs = transform_geom("EPSG:4326", pre_ds.crs, geom, precision=-1)
        window = geometry_window(pre_ds, [geom_in_crs], pad_x=0.0, pad_y=0.0, north_up=True, rotated=False)
        window = window.round_offsets().round_lengths()
        if window.width <= 0 or window.height <= 0:
            raise ValueError("deterministic basin window is empty")
        wtransform = pre_ds.window_transform(window)
        shape = (int(window.height), int(window.width))

        basin = rasterize(
            [(geom_in_crs, 1)],
            out_shape=shape,
            transform=wtransform,
            fill=0,
            all_touched=bool(contract["basin_pixelization"]["all_touched"]),
            dtype="uint8",
        ).astype(bool)
        basin_count = int(basin.sum())
        if basin_count <= 0:
            raise ValueError("frozen basin rasterizes to zero target-grid pixels")

        pre_arr = pre_ds.read(1, window=window, masked=False)
        post_arr = post_ds.read(1, window=window, masked=False)
        pre_mask_raw = pre_ds.dataset_mask(window=window)
        post_mask_raw = post_ds.dataset_mask(window=window)
        pre_valid = basin & (pre_mask_raw > 0) & np.isfinite(pre_arr) & (pre_arr > 0)
        post_valid = basin & (post_mask_raw > 0) & np.isfinite(post_arr) & (post_arr > 0)
        common = pre_valid & post_valid
        pre_count = int(pre_valid.sum())
        post_count = int(post_valid.sum())
        common_count = int(common.sum())
        pre_fraction = pre_count / basin_count
        post_fraction = post_count / basin_count
        common_fraction = common_count / basin_count
        threshold = float(contract["common_support"]["minimum_fraction"])
        passed = common_fraction >= threshold

        pre_crop = write_lossless_crop(pre_ds, pre_arr, pre_mask_raw, window, args.pre_crop_output)
        post_crop = write_lossless_crop(post_ds, post_arr, post_mask_raw, window, args.post_crop_output)

        args.mask_output.parent.mkdir(parents=True, exist_ok=True)
        profile = pre_ds.profile.copy()
        profile.update(
            driver="GTiff",
            width=shape[1],
            height=shape[0],
            transform=wtransform,
            dtype="uint8",
            count=1,
            nodata=0,
            compress="deflate",
        )
        with rasterio.open(args.mask_output, "w", **profile) as out:
            out.write(common.astype("uint8"), 1)

        report = {
            "schema_version": "irfen-ibvf-cashahuacra-sentinel1-r3-v0.2",
            "generated_at": now(),
            "case_id": "cashahuacra_2015-03-23",
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "uses_operational_event_none_labels": False,
            "territorial_activation_evidence_blinded": True,
            "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
            "r2_status_required": required,
            "r2_status_observed": r2["status"],
            "grid_identity_pass": True,
            "full_r2_grid": {
                "crs": str(pre_ds.crs),
                "width": pre_ds.width,
                "height": pre_ds.height,
                "transform": [float(x) for x in tuple(pre_ds.transform)],
            },
            "deterministic_basin_window": {
                "column_offset": int(window.col_off),
                "row_offset": int(window.row_off),
                "width": int(window.width),
                "height": int(window.height),
                "transform": [float(x) for x in tuple(wtransform)],
                "depends_on_signal_values": False,
                "depends_on_outcome": False,
            },
            "lossless_basin_crops": {"pre": pre_crop, "post": post_crop},
            "basin_pixel_count": basin_count,
            "pre_valid_pixel_count": pre_count,
            "pre_valid_fraction": pre_fraction,
            "post_valid_pixel_count": post_count,
            "post_valid_fraction": post_fraction,
            "common_valid_pixel_count": common_count,
            "common_support_fraction": common_fraction,
            "minimum_common_support_fraction": threshold,
            "common_support_gate_pass": passed,
            "common_support_mask": {
                "path": str(args.mask_output),
                "bytes": args.mask_output.stat().st_size,
                "sha256": sha256_file(args.mask_output),
            },
            "radiometric_difference_statistics_computed": False,
            "comparison_performed": False,
            "r3_common_support_built": True,
            "r4_difference_computed": False,
            "case_control_role_assigned": False,
            "activation_inference_allowed": False,
            "status": contract["common_support"]["above_gate_status"] if passed else contract["common_support"]["below_gate_status"],
            "next_gate": "R4_MAY_BE_EXECUTED_ONLY_FROM_THE_FROZEN_LOSSLESS_CROPS_AND_COMMON_SUPPORT_MASK_USING_A_SEPARATELY_PREREGISTERED_CHANGE_METRIC_CONTRACT" if passed else "R4_BLOCKED_DO_NOT_RESELECT_DATES_OR_RESAMPLE_POST_HOC",
        }
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "common_support_fraction": common_fraction, "basin_pixel_count": basin_count, "window": report["deterministic_basin_window"]}, indent=2))
        return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
