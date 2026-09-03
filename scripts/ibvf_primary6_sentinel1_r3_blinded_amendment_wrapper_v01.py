#!/usr/bin/env python3
"""Apply the preregistered signal-blind R3 footprint amendment only on blockers.

The unchanged legacy/tiled R3 implementation is executed first. Only when it
returns the preidentified rectangular basin-window containment blocker may this
wrapper apply the frozen amendment. For a joint R2 metadata footprint below
0.95 it returns UNKNOWN without reading raster pixels. Otherwise it computes
native, zero-resampled common-valid support on a full frozen-basin denominator;
pixels outside either R2 footprint are unsupported. No radiometric difference,
R4 value, territorial outcome, event label, or case/control role is read here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from rasterio.windows import Window
from shapely.geometry import box, mapping, shape

import ibvf_primary6_sentinel1_r3_common_support as legacy

LEGACY_BLOCKER = "R3_BLOCKED_FROZEN_BASIN_WINDOW_NOT_CONTAINED_IN_BOTH_R2_PRODUCTS"
PASS = "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY"
UNKNOWN = "UNKNOWN_INSUFFICIENT_COMMON_SUPPORT"
SPATIAL_UNKNOWN = "R3_UNKNOWN_INSUFFICIENT_SPATIAL_FOOTPRINT_NO_R4"
AMENDMENT_STATUS = "FROZEN_SIGNAL_BLIND_BLOCKER_AMENDMENT_BEFORE_REPAIR_RERUN_NO_OUTCOMES_NO_R4_MAGNITUDES"


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
    assert d["territorial_activation_evidence_blinded"] is True


def write(path: Path, d: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def integer_phase(pre: rasterio.DatasetReader, post: rasterio.DatasetReader, tol: float, tol_pixels: float) -> tuple[int, int, float, float]:
    if pre.crs != post.crs:
        raise ValueError("PRE/POST CRS mismatch")
    if any(abs(float(x)) > tol for x in (pre.transform.b, pre.transform.d, post.transform.b, post.transform.d)):
        raise ValueError("rotated R2 grids are forbidden")
    if abs(float(pre.transform.a) - float(post.transform.a)) > tol or abs(float(pre.transform.e) - float(post.transform.e)) > tol:
        raise ValueError("PRE/POST pixel vectors differ")
    col_phase = (float(pre.transform.c) - float(post.transform.c)) / float(pre.transform.a)
    row_phase = (float(pre.transform.f) - float(post.transform.f)) / float(pre.transform.e)
    ci, ri = int(round(col_phase)), int(round(row_phase))
    if abs(col_phase - ci) > tol_pixels or abs(row_phase - ri) > tol_pixels:
        raise ValueError("PRE/POST grids have noninteger phase")
    return ci, ri, col_phase, row_phase


def full_geometry_window(transform: rasterio.Affine, geom_bounds: tuple[float, float, float, float]) -> Window:
    minx, miny, maxx, maxy = geom_bounds
    inv = ~transform
    c_a, r_a = inv * (minx, maxy)
    c_b, r_b = inv * (maxx, miny)
    c0 = math.floor(min(c_a, c_b))
    c1 = math.ceil(max(c_a, c_b))
    r0 = math.floor(min(r_a, r_b))
    r1 = math.ceil(max(r_a, r_b))
    if c1 <= c0 or r1 <= r0:
        raise ValueError("full frozen basin raster window is empty")
    return Window(c0, r0, c1 - c0, r1 - r0)


def native_into_full(
    ds: rasterio.DatasetReader,
    full: Window,
    canonical_to_ds_col_phase: int,
    canonical_to_ds_row_phase: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    h, w = int(full.height), int(full.width)
    arr = np.zeros((h, w), dtype=np.dtype(ds.dtypes[0]))
    raw_mask = np.zeros((h, w), dtype="uint8")
    fc0, fr0 = int(full.col_off), int(full.row_off)
    fc1, fr1 = fc0 + w, fr0 + h

    p_c0 = max(fc0, -canonical_to_ds_col_phase)
    p_c1 = min(fc1, ds.width - canonical_to_ds_col_phase)
    p_r0 = max(fr0, -canonical_to_ds_row_phase)
    p_r1 = min(fr1, ds.height - canonical_to_ds_row_phase)
    if p_c1 <= p_c0 or p_r1 <= p_r0:
        return arr, raw_mask, {"native_overlap_pixel_count": 0, "dataset_window": null_json(), "target_slice": null_json()}

    q_c0 = p_c0 + canonical_to_ds_col_phase
    q_r0 = p_r0 + canonical_to_ds_row_phase
    width, height = p_c1 - p_c0, p_r1 - p_r0
    src_win = Window(q_c0, q_r0, width, height)
    native = ds.read(1, window=src_win, masked=False)
    native_mask = ds.dataset_mask(window=src_win)
    t_c0, t_r0 = p_c0 - fc0, p_r0 - fr0
    t_c1, t_r1 = t_c0 + width, t_r0 + height
    if native.shape != (height, width) or native_mask.shape != (height, width):
        raise ValueError("native read shape mismatch")
    arr[t_r0:t_r1, t_c0:t_c1] = native
    raw_mask[t_r0:t_r1, t_c0:t_c1] = native_mask
    return arr, raw_mask, {
        "native_overlap_pixel_count": int(width * height),
        "dataset_window": [int(q_c0), int(q_r0), int(width), int(height)],
        "target_slice": [int(t_c0), int(t_r0), int(width), int(height)],
    }


def null_json():
    return None


def write_full_grid(src: rasterio.DatasetReader, arr: np.ndarray, raw_mask: np.ndarray, transform: rasterio.Affine, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = src.profile.copy()
    profile.update(
        driver="GTiff", width=arr.shape[1], height=arr.shape[0], transform=transform,
        count=1, dtype=src.dtypes[0], compress="deflate", tiled=True,
        blockxsize=512, blockysize=512,
    )
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr.astype(src.dtypes[0], copy=False), 1)
            dst.write_mask(raw_mask.astype("uint8", copy=False))
    with rasterio.open(path) as check:
        reread = check.read(1, masked=False)
        remask = check.dataset_mask()
        if not np.array_equal(reread, arr.astype(src.dtypes[0], copy=False), equal_nan=True):
            raise ValueError("amended R3 crop array identity failed")
        if not np.array_equal(remask, raw_mask.astype("uint8", copy=False)):
            raise ValueError("amended R3 crop mask identity failed")
    return {
        "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path),
        "dtype": src.dtypes[0], "nodata": src.nodata,
        "pixel_identity_check": "PASS_EXACT_ARRAY_EQUAL_INCLUDING_ZERO_FILLED_OUTSIDE_NATIVE_FOOTPRINT",
        "mask_identity_check": "PASS_EXACT_ARRAY_EQUAL",
        "native_overlap_resampling_performed": False,
        "outside_native_footprint_filled_zero_and_masked_invalid": True,
        "radiometric_transformation_performed": False,
    }


def amended_report_base(args: argparse.Namespace, r2: dict[str, Any], amendment: dict[str, Any], unit_id: str) -> dict[str, Any]:
    return {
        "schema_version": "irfen-ibvf-primary6-sentinel1-r3-v0.2-signal-blind-footprint-amendment",
        "generated_at": now(), "case_id": args.case_id, "unit_id": unit_id,
        "season_id": r2["season_id"], "date_local": r2["date_local"],
        "deployment_status": "RESEARCH_ONLY", "test_only": True,
        "production_use": False, "production_ready": False,
        "operational_alerting_enabled": False, "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "global_contract_sha256": sha256_file(args.global_contract),
        "anchor_r3_contract_sha256": sha256_file(args.anchor_r3_contract),
        "r2_report_sha256": sha256_file(args.r2_report),
        "basin_geometry_path": str(args.basin), "basin_geometry_sha256": sha256_file(args.basin),
        "signal_blind_blocker_amendment_path": str(args.blocker_amendment),
        "signal_blind_blocker_amendment_sha256": sha256_file(args.blocker_amendment),
        "legacy_r3_blocker_confirmed_before_amendment": True,
        "r3_threshold_changed": False, "selected_window_changed": False,
        "sentinel1_pair_changed": False, "replacement_performed": False,
        "reselection_performed": False, "imputation_performed": False,
        "zero_resampling": True,
        "radiometric_difference_statistics_computed": False, "comparison_performed": False,
        "r4_difference_computed": False, "r4_values_read_for_amendment_decision": False,
        "territorial_outcomes_read": False, "known_event_dates_read": False,
        "case_control_role_assigned": False, "activation_inference_allowed": False,
        "modeling_allowed": False,
    }


def apply_amendment(args: argparse.Namespace, legacy_report: dict[str, Any]) -> int:
    contract, anchor, r2, amendment = map(load, [args.global_contract, args.anchor_r3_contract, args.r2_report, args.blocker_amendment])
    for d in (contract, anchor, r2, amendment):
        guard(d)
    if amendment["status"] != AMENDMENT_STATUS:
        raise SystemExit("signal-blind blocker amendment is not frozen")
    if amendment["r4_values_read_during_amendment_design"] is not False or amendment["territorial_outcomes_read_during_amendment_design"] is not False:
        raise SystemExit("amendment blindness provenance invalid")
    if legacy_report.get("status") != LEGACY_BLOCKER:
        raise SystemExit("amendment may run only after exact legacy containment blocker")
    if r2["case_id"] != args.case_id or r2["territorial_outcomes_read"] is not False:
        raise SystemExit("R2 identity/blindness mismatch")
    unit_id = r2["unit_id"]
    unit = contract["unit_geometry_and_projection"][unit_id]
    if Path(unit["geometry_path"]) != args.basin:
        raise SystemExit("basin differs from frozen geometry")
    threshold = float(contract["r3_rule"]["minimum_common_support_fraction"])
    if threshold != 0.95 or float(anchor["common_support"]["minimum_fraction"]) != threshold:
        raise SystemExit("R3 0.95 threshold changed")
    frozen_cases = {x["case_id"]: x for x in amendment["r3_spatial_footprint_amendment"]["diagnostic_cases_frozen_before_amendment"]}
    if args.case_id not in frozen_cases:
        raise SystemExit("containment blocker case was not preregistered for amended path")
    expected_diag = frozen_cases[args.case_id]
    geom_wgs84 = legacy.select_geometry(args.basin, unit.get("geometry_selector"))

    with rasterio.open(args.pre) as pre_ds, rasterio.open(args.post) as post_ds:
        if sha256_file(args.pre) != r2["pre"]["output"]["sha256"] or sha256_file(args.post) != r2["post"]["output"]["sha256"]:
            raise SystemExit("R2 raster identities differ from accepted blind R2 report")
        tol = float(anchor["target_pixel_lattice_gate"]["absolute_coordinate_tolerance"])
        tol_pixels = float(anchor["target_pixel_lattice_gate"]["integer_phase_tolerance_pixels"])
        ci, ri, col_phase, row_phase = integer_phase(pre_ds, post_ds, tol, tol_pixels)
        geom_crs_json = transform_geom("EPSG:4326", pre_ds.crs, geom_wgs84, precision=-1)
        geom = shape(geom_crs_json)
        if geom.is_empty or geom.area <= 0:
            raise SystemExit("projected frozen basin geometry invalid")
        pre_fp, post_fp = box(*pre_ds.bounds), box(*post_ds.bounds)
        joint_fraction = float(geom.intersection(pre_fp).intersection(post_fp).area / geom.area)
        if abs(joint_fraction - float(expected_diag["joint_geometry_footprint_coverage_fraction"])) > 1e-9:
            raise SystemExit("recomputed geometry footprint fraction differs from preregistered blinded diagnostic")

        report = amended_report_base(args, r2, amendment, unit_id)
        report["target_pixel_lattice_pass"] = True
        report["target_pixel_lattice"] = {
            "crs": str(pre_ds.crs), "pixel_size_x": float(pre_ds.transform.a), "pixel_size_y": float(pre_ds.transform.e),
            "pre_to_post_column_phase_pixels": col_phase, "pre_to_post_row_phase_pixels": row_phase,
            "integer_column_phase_pixels": ci, "integer_row_phase_pixels": ri,
        }
        report["joint_geometry_footprint_coverage_fraction"] = joint_fraction
        report["joint_geometry_footprint_coverage_pct"] = 100.0 * joint_fraction
        report["minimum_common_support_fraction"] = threshold
        report["geometry_footprint_is_upper_bound_only"] = True

        if joint_fraction < threshold:
            report.update({
                "amended_spatial_gate_status": SPATIAL_UNKNOWN,
                "common_support_fraction": joint_fraction,
                "common_support_fraction_semantics": "MAXIMUM_POSSIBLE_SUPPORT_UPPER_BOUND_FROM_JOINT_GEOMETRY_FOOTPRINT_NO_RASTER_PIXEL_READ",
                "common_support_gate_pass": False,
                "raster_pixels_read_by_amended_path": False,
                "r3_common_support_built": False,
                "status": UNKNOWN,
                "next_gate": "R4_BLOCKED_EXPLICIT_SPATIAL_FOOTPRINT_UNKNOWN_NO_REPLACEMENT_NO_IMPUTATION",
            })
            write(args.report_output, report)
            print(json.dumps({"case_id": args.case_id, "status": report["status"], "amended_spatial_gate_status": SPATIAL_UNKNOWN, "joint_geometry_footprint_coverage_fraction": joint_fraction, "raster_pixels_read": False}, indent=2))
            return 2

        full = full_geometry_window(pre_ds.transform, geom.bounds)
        full_transform = pre_ds.window_transform(full)
        shape_out = (int(full.height), int(full.width))
        basin_mask = rasterize([(mapping(geom), 1)], out_shape=shape_out, transform=full_transform, fill=0, all_touched=False, dtype="uint8").astype(bool)
        basin_count = int(basin_mask.sum())
        if basin_count <= 0:
            raise SystemExit("full frozen basin rasterized to zero pixels")

        pre_arr, pre_mask_raw, pre_overlap = native_into_full(pre_ds, full, 0, 0)
        post_arr, post_mask_raw, post_overlap = native_into_full(post_ds, full, ci, ri)
        pre_valid = basin_mask & (pre_mask_raw > 0) & np.isfinite(pre_arr) & (pre_arr > 0)
        post_valid = basin_mask & (post_mask_raw > 0) & np.isfinite(post_arr) & (post_arr > 0)
        common = pre_valid & post_valid
        pre_count, post_count, common_count = int(pre_valid.sum()), int(post_valid.sum()), int(common.sum())
        common_fraction = float(common_count / basin_count)
        passed = common_fraction >= threshold

        pre_crop = write_full_grid(pre_ds, pre_arr, pre_mask_raw, full_transform, args.pre_crop_output)
        post_crop = write_full_grid(post_ds, post_arr, post_mask_raw, full_transform, args.post_crop_output)
        args.mask_output.parent.mkdir(parents=True, exist_ok=True)
        mask_profile = pre_ds.profile.copy()
        mask_profile.update(driver="GTiff", width=shape_out[1], height=shape_out[0], transform=full_transform,
                            dtype="uint8", count=1, nodata=0, compress="deflate", tiled=True,
                            blockxsize=512, blockysize=512)
        with rasterio.open(args.mask_output, "w", **mask_profile) as dst:
            dst.write(common.astype("uint8"), 1)

        report.update({
            "amended_spatial_gate_status": "AMENDED_FULL_BASIN_VALID_PIXEL_SUPPORT_COMPUTED",
            "full_frozen_basin_denominator": True,
            "missing_r2_footprint_pixels_count_as_supported": False,
            "raster_pixels_read_by_amended_path": True,
            "co_window": {
                "shape": list(shape_out), "transform": [float(x) for x in tuple(full_transform)],
                "canonical_pre_lattice_full_basin_window": [int(full.col_off), int(full.row_off), int(full.width), int(full.height)],
                "pre_native_overlap": pre_overlap, "post_native_overlap": post_overlap,
            },
            "basin_pixel_count": basin_count,
            "pre_valid_pixel_count": pre_count, "pre_valid_fraction": pre_count / basin_count,
            "post_valid_pixel_count": post_count, "post_valid_fraction": post_count / basin_count,
            "common_support_pixel_count": common_count, "common_support_fraction": common_fraction,
            "common_support_fraction_semantics": "COMMON_VALID_NATIVE_PIXELS_DIVIDED_BY_FULL_FROZEN_BASIN_PIXEL_DENOMINATOR",
            "common_support_gate_pass": passed,
            "pre_lossless_crop": pre_crop, "post_lossless_crop": post_crop,
            "common_support_mask": {"path": str(args.mask_output), "bytes": args.mask_output.stat().st_size, "sha256": sha256_file(args.mask_output), "pixel_count": common_count},
            "r3_common_support_built": True,
            "status": PASS if passed else UNKNOWN,
            "next_gate": "R4_FROZEN_FIVE_FEATURE_VECTOR_ALLOWED_NO_INFERENCE" if passed else "R4_BLOCKED_UNKNOWN_INSUFFICIENT_COMMON_SUPPORT",
        })
        write(args.report_output, report)
        print(json.dumps({"case_id": args.case_id, "status": report["status"], "common_support_fraction": common_fraction, "full_basin_denominator": True, "radiometric_difference_statistics_computed": False, "territorial_outcomes_read": False}, indent=2))
        return 0 if passed else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--global-contract", type=Path, required=True)
    ap.add_argument("--anchor-r3-contract", type=Path, required=True)
    ap.add_argument("--r2-report", type=Path, required=True)
    ap.add_argument("--blocker-amendment", type=Path, required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--basin", type=Path, required=True)
    ap.add_argument("--pre-crop-output", type=Path, required=True)
    ap.add_argument("--post-crop-output", type=Path, required=True)
    ap.add_argument("--mask-output", type=Path, required=True)
    ap.add_argument("--report-output", type=Path, required=True)
    args = ap.parse_args()

    legacy_cmd = [
        sys.executable, "scripts/ibvf_primary6_sentinel1_r3_tiled_storage_wrapper.py",
        "--global-contract", str(args.global_contract), "--anchor-r3-contract", str(args.anchor_r3_contract),
        "--r2-report", str(args.r2_report), "--case-id", args.case_id,
        "--pre", str(args.pre), "--post", str(args.post), "--basin", str(args.basin),
        "--pre-crop-output", str(args.pre_crop_output), "--post-crop-output", str(args.post_crop_output),
        "--mask-output", str(args.mask_output), "--report-output", str(args.report_output),
    ]
    proc = subprocess.run(legacy_cmd, check=False)
    if not args.report_output.is_file():
        return proc.returncode
    legacy_report = load(args.report_output)
    if legacy_report.get("status") != LEGACY_BLOCKER:
        return proc.returncode
    if proc.returncode != 2:
        raise SystemExit("legacy containment blocker returned unexpected exit code")
    return apply_amendment(args, legacy_report)


if __name__ == "__main__":
    raise SystemExit(main())
