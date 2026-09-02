#!/usr/bin/env python3
"""Build generic PRIMARY6 Sentinel-1 R3 common support under frozen anchor rules.

RESEARCH_ONLY / TEST_ONLY. The script inherits the Cashahuacra R3 lattice and
support rules exactly, while substituting only the frozen PRIMARY6 unit geometry
and case/output paths. It never computes a pre/post radiometric difference.
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
from rasterio.windows import Window, bounds as window_bounds, from_bounds
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


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


def select_geometry(path: Path, selector: dict[str, Any] | None) -> dict[str, Any]:
    doc = load(path)
    if doc.get("type") == "Feature":
        features = [doc]
    elif doc.get("type") == "FeatureCollection":
        features = doc.get("features") or []
    else:
        raise ValueError("basin file must be GeoJSON Feature or FeatureCollection")
    if selector is not None:
        prop, value = selector["property"], selector["value"]
        features = [f for f in features if (f.get("properties") or {}).get(prop) == value]
    if not features:
        raise ValueError("frozen basin selector returned no features")
    geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:
        raise ValueError("selected basin has no geometry")
    merged = unary_union(geoms)
    if merged.is_empty:
        raise ValueError("selected basin union is empty")
    if not merged.is_valid:
        merged = merged.buffer(0)
    if merged.is_empty or not merged.is_valid:
        raise ValueError("selected basin geometry is invalid")
    return mapping(merged)


def transform_equal(a: rasterio.Affine, b: rasterio.Affine, tol: float) -> bool:
    return all(abs(float(x) - float(y)) <= tol for x, y in zip(tuple(a), tuple(b)))


def near_integer(value: float, tol_pixels: float) -> tuple[bool, int]:
    nearest = int(round(value))
    return abs(value - nearest) <= tol_pixels, nearest


def integer_window(window: Window, tol_pixels: float) -> Window:
    vals = [float(window.col_off), float(window.row_off), float(window.width), float(window.height)]
    out: list[int] = []
    for value in vals:
        ok, iv = near_integer(value, tol_pixels)
        if not ok:
            raise ValueError(f"window coordinate is not integer-lattice aligned: {value}")
        out.append(iv)
    return Window(out[0], out[1], out[2], out[3])


def window_inside(ds: rasterio.DatasetReader, window: Window) -> bool:
    return (
        int(window.col_off) >= 0
        and int(window.row_off) >= 0
        and int(window.width) > 0
        and int(window.height) > 0
        and int(window.col_off + window.width) <= ds.width
        and int(window.row_off + window.height) <= ds.height
    )


def write_lossless_crop(src: rasterio.DatasetReader, arr: np.ndarray, mask: np.ndarray, window: Window, path: Path) -> dict[str, Any]:
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
            raise ValueError(f"lossless crop pixel identity failed: {path}")
        if not np.array_equal(remask, mask.astype("uint8", copy=False)):
            raise ValueError(f"lossless crop mask identity failed: {path}")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "dtype": src.dtypes[0],
        "nodata": src.nodata,
        "pixel_identity_check": "PASS_EXACT_ARRAY_EQUAL",
        "mask_identity_check": "PASS_EXACT_ARRAY_EQUAL",
        "resampling_performed": False,
        "radiometric_transformation_performed": False,
    }


def write_report(args: argparse.Namespace, report: dict[str, Any]) -> int:
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "case_id": report["case_id"],
        "common_support_fraction": report.get("common_support_fraction"),
        "radiometric_difference_statistics_computed": False,
        "activation_inference_allowed": False,
    }, indent=2))
    return 0 if report["status"] == "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY" else 2


def blocked_base(case_id: str, unit_id: str, status: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-r3-v0.1",
        "generated_at": now(),
        "case_id": case_id,
        "unit_id": unit_id,
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "status": status,
        "target_pixel_lattice_pass": False,
        "zero_resampling": True,
        "r3_common_support_built": False,
        "radiometric_difference_statistics_computed": False,
        "comparison_performed": False,
        "r4_difference_computed": False,
        "territorial_outcomes_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
    }
    if details:
        out["diagnostic_details"] = details
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--global-contract", type=Path, required=True)
    ap.add_argument("--anchor-r3-contract", type=Path, required=True)
    ap.add_argument("--r2-report", type=Path, required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--basin", type=Path, required=True)
    ap.add_argument("--pre-crop-output", type=Path, required=True)
    ap.add_argument("--post-crop-output", type=Path, required=True)
    ap.add_argument("--mask-output", type=Path, required=True)
    ap.add_argument("--report-output", type=Path, required=True)
    args = ap.parse_args()

    global_contract = load(args.global_contract)
    anchor = load(args.anchor_r3_contract)
    r2 = load(args.r2_report)
    for d in (global_contract, anchor, r2):
        guard(d)
    if global_contract["inheritance"]["cashahuacra_anchor_r3_common_support_algorithm_changed"] is not False:
        raise SystemExit("global contract does not preserve anchor R3 algorithm")
    if global_contract["bulk_gate"]["bulk_rules_locked_to_this_contract"] is not True:
        raise SystemExit("bulk R3 rules are not locked")
    if anchor["target_pixel_lattice_gate"]["resampling_allowed"] is not False:
        raise SystemExit("anchor R3 resampling guard changed")
    if float(anchor["common_support"]["minimum_fraction"]) != float(global_contract["r3_rule"]["minimum_common_support_fraction"]):
        raise SystemExit("global/anchor R3 support threshold mismatch")
    if anchor["basin_pixelization"]["all_touched"] is not False:
        raise SystemExit("anchor basin pixelization changed")

    if r2["case_id"] != args.case_id:
        raise SystemExit("R2 report case mismatch")
    if r2["status"] != "PASS_R2_PRE_POST_INDEPENDENT_PROCESSING_POEORB_VERIFIED_NO_COMPARISON":
        raise SystemExit("R3 blocked: generic PRIMARY6 R2 gate has not passed")
    if not r2["r2_processing_executed"] or not r2["poeorb_consumption_verified_both_dates"]:
        raise SystemExit("R3 blocked: R2 execution/orbit verification incomplete")
    assert r2["comparison_performed"] is False
    assert r2["r4_difference_computed"] is False
    assert r2["territorial_outcomes_read"] is False
    assert r2["case_control_role_assigned"] is False

    unit_id = r2["unit_id"]
    unit = global_contract["unit_geometry_and_projection"][unit_id]
    if Path(unit["geometry_path"]) != args.basin:
        raise SystemExit("basin path differs from frozen unit geometry")
    if sha256_file(args.pre) != r2["pre"]["output"]["sha256"] or sha256_file(args.post) != r2["post"]["output"]["sha256"]:
        raise SystemExit("R2 raster byte identities differ from R2 report")

    tol = float(anchor["target_pixel_lattice_gate"]["absolute_coordinate_tolerance"])
    tol_pixels = float(anchor["target_pixel_lattice_gate"]["integer_phase_tolerance_pixels"])
    threshold = float(anchor["common_support"]["minimum_fraction"])
    selector = unit.get("geometry_selector")

    with rasterio.open(args.pre) as pre_ds, rasterio.open(args.post) as post_ds:
        same_crs = pre_ds.crs == post_ds.crs
        no_rotation = (
            abs(float(pre_ds.transform.b)) <= tol
            and abs(float(pre_ds.transform.d)) <= tol
            and abs(float(post_ds.transform.b)) <= tol
            and abs(float(post_ds.transform.d)) <= tol
        )
        same_pixel_vectors = (
            abs(float(pre_ds.transform.a) - float(post_ds.transform.a)) <= tol
            and abs(float(pre_ds.transform.e) - float(post_ds.transform.e)) <= tol
        )
        if not same_crs or not no_rotation or not same_pixel_vectors:
            report = blocked_base(args.case_id, unit_id, anchor["target_pixel_lattice_gate"]["lattice_mismatch_status"], {
                "same_crs": same_crs, "no_rotation": no_rotation, "same_pixel_vectors": same_pixel_vectors
            })
            return write_report(args, report)

        col_phase = (float(pre_ds.transform.c) - float(post_ds.transform.c)) / float(pre_ds.transform.a)
        row_phase = (float(pre_ds.transform.f) - float(post_ds.transform.f)) / float(pre_ds.transform.e)
        col_ok, col_phase_i = near_integer(col_phase, tol_pixels)
        row_ok, row_phase_i = near_integer(row_phase, tol_pixels)
        if not (col_ok and row_ok):
            report = blocked_base(args.case_id, unit_id, anchor["target_pixel_lattice_gate"]["noninteger_phase_status"], {
                "column_phase_pixels": col_phase, "row_phase_pixels": row_phase
            })
            return write_report(args, report)

        geom_wgs84 = select_geometry(args.basin, selector)
        geom_crs = transform_geom("EPSG:4326", pre_ds.crs, geom_wgs84, precision=-1)
        pre_window = geometry_window(pre_ds, [geom_crs], pad_x=0.0, pad_y=0.0, north_up=True, rotated=False)
        pre_window = integer_window(pre_window.round_offsets().round_lengths(), tol_pixels)
        if not window_inside(pre_ds, pre_window):
            report = blocked_base(args.case_id, unit_id, anchor["basin_window_preservation"]["window_outside_status"])
            return write_report(args, report)

        common_bounds = window_bounds(pre_window, pre_ds.transform)
        post_window_float = from_bounds(*common_bounds, transform=post_ds.transform)
        try:
            post_window = integer_window(post_window_float, tol_pixels)
        except ValueError:
            report = blocked_base(args.case_id, unit_id, anchor["target_pixel_lattice_gate"]["noninteger_window_mapping_status"], {
                "pre_window_bounds": [float(x) for x in common_bounds],
                "post_window_float": [
                    float(post_window_float.col_off), float(post_window_float.row_off),
                    float(post_window_float.width), float(post_window_float.height)
                ],
            })
            return write_report(args, report)
        if not window_inside(post_ds, post_window):
            report = blocked_base(args.case_id, unit_id, anchor["basin_window_preservation"]["window_outside_status"])
            return write_report(args, report)

        pre_transform = pre_ds.window_transform(pre_window)
        post_transform = post_ds.window_transform(post_window)
        same_output_transform = transform_equal(pre_transform, post_transform, tol)
        same_output_shape = int(pre_window.width) == int(post_window.width) and int(pre_window.height) == int(post_window.height)
        if not same_output_transform or not same_output_shape:
            report = blocked_base(args.case_id, unit_id, anchor["target_pixel_lattice_gate"]["co_window_mismatch_status"], {
                "same_output_transform": same_output_transform, "same_output_shape": same_output_shape
            })
            return write_report(args, report)

        shape_out = (int(pre_window.height), int(pre_window.width))
        basin_mask = rasterize(
            [(geom_crs, 1)],
            out_shape=shape_out,
            transform=pre_transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
        basin_count = int(basin_mask.sum())
        if basin_count <= 0:
            raise ValueError("frozen basin rasterizes to zero pixels")

        pre_arr = pre_ds.read(1, window=pre_window, masked=False)
        post_arr = post_ds.read(1, window=post_window, masked=False)
        pre_mask_raw = pre_ds.dataset_mask(window=pre_window)
        post_mask_raw = post_ds.dataset_mask(window=post_window)
        pre_valid = basin_mask & (pre_mask_raw > 0) & np.isfinite(pre_arr) & (pre_arr > 0)
        post_valid = basin_mask & (post_mask_raw > 0) & np.isfinite(post_arr) & (post_arr > 0)
        common = pre_valid & post_valid

        pre_count = int(pre_valid.sum())
        post_count = int(post_valid.sum())
        common_count = int(common.sum())
        common_fraction = common_count / basin_count
        passed = common_fraction >= threshold

        pre_crop = write_lossless_crop(pre_ds, pre_arr, pre_mask_raw, pre_window, args.pre_crop_output)
        post_crop = write_lossless_crop(post_ds, post_arr, post_mask_raw, post_window, args.post_crop_output)

        args.mask_output.parent.mkdir(parents=True, exist_ok=True)
        profile = pre_ds.profile.copy()
        profile.update(
            driver="GTiff", width=shape_out[1], height=shape_out[0], transform=pre_transform,
            dtype="uint8", count=1, nodata=0, compress="deflate"
        )
        with rasterio.open(args.mask_output, "w", **profile) as dst:
            dst.write(common.astype("uint8"), 1)

        report = {
            "schema_version": "irfen-ibvf-primary6-sentinel1-r3-v0.1",
            "generated_at": now(),
            "case_id": args.case_id,
            "unit_id": unit_id,
            "season_id": r2["season_id"],
            "date_local": r2["date_local"],
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "uses_operational_event_none_labels": False,
            "territorial_activation_evidence_blinded": True,
            "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
            "global_contract_sha256": sha256_file(args.global_contract),
            "anchor_r3_contract_sha256": sha256_file(args.anchor_r3_contract),
            "r2_report_sha256": sha256_file(args.r2_report),
            "basin_geometry_path": str(args.basin),
            "basin_geometry_sha256": sha256_file(args.basin),
            "basin_geometry_selector": selector,
            "target_pixel_lattice_pass": True,
            "zero_resampling": True,
            "target_pixel_lattice": {
                "crs": str(pre_ds.crs),
                "pixel_size_x": float(pre_ds.transform.a),
                "pixel_size_y": float(pre_ds.transform.e),
                "pre_to_post_column_phase_pixels": col_phase,
                "pre_to_post_row_phase_pixels": row_phase,
                "integer_column_phase_pixels": col_phase_i,
                "integer_row_phase_pixels": row_phase_i,
                "absolute_coordinate_tolerance": tol,
                "integer_phase_tolerance_pixels": tol_pixels,
            },
            "co_window": {
                "shape": list(shape_out),
                "transform": [float(x) for x in tuple(pre_transform)],
                "bounds": [float(x) for x in common_bounds],
                "pre_window": [int(pre_window.col_off), int(pre_window.row_off), int(pre_window.width), int(pre_window.height)],
                "post_window": [int(post_window.col_off), int(post_window.row_off), int(post_window.width), int(post_window.height)],
            },
            "basin_pixel_count": basin_count,
            "pre_valid_pixel_count": pre_count,
            "pre_valid_fraction": pre_count / basin_count,
            "post_valid_pixel_count": post_count,
            "post_valid_fraction": post_count / basin_count,
            "common_support_pixel_count": common_count,
            "common_support_fraction": common_fraction,
            "minimum_common_support_fraction": threshold,
            "common_support_gate_pass": passed,
            "pre_lossless_crop": pre_crop,
            "post_lossless_crop": post_crop,
            "common_support_mask": {
                "path": str(args.mask_output),
                "bytes": args.mask_output.stat().st_size,
                "sha256": sha256_file(args.mask_output),
                "pixel_count": common_count,
            },
            "r3_common_support_built": True,
            "radiometric_difference_statistics_computed": False,
            "comparison_performed": False,
            "r4_difference_computed": False,
            "territorial_outcomes_read": False,
            "known_event_dates_read": False,
            "case_control_role_assigned": False,
            "activation_inference_allowed": False,
            "modeling_allowed": False,
            "status": (
                "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY"
                if passed else anchor["common_support"]["below_gate_status"]
            ),
            "next_gate": (
                "R4_FROZEN_FIVE_FEATURE_VECTOR_ALLOWED_NO_INFERENCE"
                if passed else "R4_BLOCKED_UNKNOWN_INSUFFICIENT_COMMON_SUPPORT"
            ),
        }
        return write_report(args, report)


if __name__ == "__main__":
    raise SystemExit(main())
