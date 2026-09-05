#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.2.

This wrapper preserves the frozen morphometry formulas from revision 0.1 and changes only
raster-grid alignment. Frozen geometry diagnostics store their WGS84 bboxes rounded to
8 decimals; reconstructing directly from those rounded values can shift a projected 30 m
grid by millimetres. Revision 0.2 recovers the canonical grid origin from an already-frozen
outlet row/column and cell-center coordinates recorded in the geometry diagnostic or, for
the legacy Cashahuacra diagnostic that predates that field, the frozen outlet registry.
No A6680 numeric reference, observed 2015 outcome, or post-anchor predictor is read.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

import compute_chosica_2015_morphometry_phase1 as base

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V2 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_2.json"
BASE_IMPLEMENTATION = ROOT / "scripts/compute_chosica_2015_morphometry_phase1.py"
MAX_ORIGIN_ADJUSTMENT_M = 0.1
ALIGNMENT_AUDIT: dict[str, dict] = {}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _chosen_attempt(report: dict) -> dict | None:
    chosen = report.get("chosen_margin_degrees")
    if chosen is None:
        return None
    attempts = [
        a for a in report.get("attempts", [])
        if abs(float(a.get("margin_degrees", 1e99)) - float(chosen)) < 1e-12
    ]
    if len(attempts) != 1 or attempts[0].get("status") != "COMPLETE":
        raise RuntimeError("FAIL_CLOSED_ALIGNMENT_CHOSEN_ATTEMPT")
    return attempts[0]


def _report_anchor(report: dict, frozen_target: dict) -> dict:
    anchor = report.get("outlet_grid_cell")
    source = "GEOMETRY_DIAGNOSTIC_TOP_LEVEL"
    if anchor is None:
        chosen_attempt = _chosen_attempt(report)
        if chosen_attempt is not None:
            anchor = chosen_attempt.get("outlet_grid_cell")
            source = "GEOMETRY_DIAGNOSTIC_CHOSEN_ATTEMPT"
    if anchor is None:
        accepted = frozen_target.get("accepted_outlet")
        if isinstance(accepted, dict) and all(k in accepted for k in ("row", "col", "x_m", "y_m")):
            anchor = {
                "row": accepted["row"],
                "col": accepted["col"],
                "center_x_m": accepted["x_m"],
                "center_y_m": accepted["y_m"],
            }
            source = "FROZEN_OUTLET_REGISTRY_ACCEPTED_CELL"
    if not isinstance(anchor, dict):
        raise RuntimeError("FAIL_CLOSED_ALIGNMENT_NO_FROZEN_OUTLET_CELL")
    required = ("row", "col", "center_x_m", "center_y_m")
    if any(k not in anchor for k in required):
        raise RuntimeError("FAIL_CLOSED_ALIGNMENT_INCOMPLETE_OUTLET_GRID_CELL")
    return {
        "row": int(anchor["row"]),
        "col": int(anchor["col"]),
        "center_x_m": float(anchor["center_x_m"]),
        "center_y_m": float(anchor["center_y_m"]),
        "source": source,
    }


def _alignment_index() -> dict[tuple[float, float, float, float], dict]:
    registry = base.load_json(base.REGISTRY)
    out: dict[tuple[float, float, float, float], dict] = {}
    for key in base.TARGET_KEYS:
        frozen_target = registry["targets"][key]
        gfreeze = frozen_target["geometry_freeze"]
        report = base.load_json(ROOT / gfreeze["diagnostic_path"])
        bbox = tuple(float(v) for v in base.geometry_bbox_from_report(report))
        if bbox in out:
            raise RuntimeError("FAIL_CLOSED_ALIGNMENT_DUPLICATE_BBOX")
        out[bbox] = {
            "target_id": key,
            "anchor": _report_anchor(report, frozen_target),
        }
    return out


ALIGNMENT_INDEX = _alignment_index()


def build_canonical_geometry_dem(td: Path, cache: Path, bbox, expected):
    key = tuple(float(v) for v in bbox)
    entry = ALIGNMENT_INDEX.get(key)
    if entry is None:
        raise RuntimeError("FAIL_CLOSED_ALIGNMENT_UNKNOWN_BBOX")
    target_id = entry["target_id"]
    anchor = entry["anchor"]

    srcs = []
    provenance = []
    try:
        for lat0, lon0 in base.relevant_tiles(bbox):
            path, prov = base.get_tile(cache, lat0, lon0, expected)
            provenance.append(prov)
            srcs.append(rasterio.open(path))
        if not srcs:
            raise RuntimeError("FAIL_CLOSED_NO_DEM_TILES")

        arr, src_transform = merge(srcs, bounds=bbox)
        profile = srcs[0].profile.copy()
        src_crs = srcs[0].crs
        h, w = arr.shape[1:]
        left, bottom, right, top = array_bounds(h, w, src_transform)
        calculated_transform, dst_w, dst_h = calculate_default_transform(
            src_crs, base.DST, w, h, left, bottom, right, top, resolution=base.RES
        )

        row = int(anchor["row"])
        col = int(anchor["col"])
        center_x = float(anchor["center_x_m"])
        center_y = float(anchor["center_y_m"])
        if not (0 <= row < dst_h and 0 <= col < dst_w):
            raise RuntimeError(f"FAIL_CLOSED_ALIGNMENT_ANCHOR_OUTSIDE_RASTER {target_id}")

        canonical_transform = Affine(
            base.RES,
            0.0,
            center_x - (col + 0.5) * base.RES,
            0.0,
            -base.RES,
            center_y + (row + 0.5) * base.RES,
        )
        origin_adjustment_m = math.hypot(
            float(canonical_transform.c) - float(calculated_transform.c),
            float(canonical_transform.f) - float(calculated_transform.f),
        )
        if origin_adjustment_m > MAX_ORIGIN_ADJUSTMENT_M:
            raise RuntimeError(
                f"FAIL_CLOSED_ALIGNMENT_ORIGIN_ADJUSTMENT {target_id} {origin_adjustment_m:.9f}"
            )

        canonical_center = rasterio.transform.xy(canonical_transform, row, col, offset="center")
        center_recovery_error_m = math.hypot(
            float(canonical_center[0]) - center_x,
            float(canonical_center[1]) - center_y,
        )
        if center_recovery_error_m > 1e-6:
            raise RuntimeError(f"FAIL_CLOSED_ALIGNMENT_CENTER_RECOVERY {target_id}")

        src_nodata = profile.get("nodata")
        dst_nodata = -9999.0 if src_nodata is None else float(src_nodata)
        out_arr = np.full((dst_h, dst_w), dst_nodata, dtype="float32")
        reproject(
            source=arr[0],
            destination=out_arr,
            src_transform=src_transform,
            src_crs=src_crs,
            src_nodata=src_nodata,
            dst_transform=canonical_transform,
            dst_crs=base.DST,
            dst_nodata=dst_nodata,
            resampling=Resampling.bilinear,
        )
        out = td / "dem.tif"
        profile.update(
            driver="GTiff",
            width=dst_w,
            height=dst_h,
            count=1,
            dtype="float32",
            crs=base.DST,
            transform=canonical_transform,
            nodata=dst_nodata,
            compress="deflate",
        )
        with rasterio.open(out, "w", **profile) as ds:
            ds.write(out_arr, 1)

        ALIGNMENT_AUDIT[target_id] = {
            "source": anchor["source"],
            "anchor_row": row,
            "anchor_col": col,
            "anchor_center_x_m": center_x,
            "anchor_center_y_m": center_y,
            "calculated_origin_x_m": float(calculated_transform.c),
            "calculated_origin_y_m": float(calculated_transform.f),
            "canonical_origin_x_m": float(canonical_transform.c),
            "canonical_origin_y_m": float(canonical_transform.f),
            "origin_adjustment_m": origin_adjustment_m,
            "max_allowed_origin_adjustment_m": MAX_ORIGIN_ADJUSTMENT_M,
            "center_recovery_error_m": center_recovery_error_m,
            "width": int(dst_w),
            "height": int(dst_h),
        }
        return out, provenance
    finally:
        for src in srcs:
            try:
                src.close()
            except Exception:
                pass


def _annotate_report(report_path: Path) -> None:
    if not report_path.exists():
        return
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    doc["execution_revision"] = "0.2_CANONICAL_GRID_ALIGNMENT_ONLY"
    doc["base_implementation_sha256"] = sha256_path(BASE_IMPLEMENTATION)
    doc["alignment_audit"] = ALIGNMENT_AUDIT
    doc["alignment_revision_guards"] = {
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "selection_or_tuning_from_metric_values": False,
    }
    report_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    base.EXECUTION = EXECUTION_V2
    base.build_exact_geometry_dem = build_canonical_geometry_dem
    base.__file__ = str(Path(__file__).resolve())

    import sys
    report_path = None
    for idx, arg in enumerate(sys.argv[:-1]):
        if arg == "--report":
            report_path = Path(sys.argv[idx + 1])
            break

    rc = base.main()
    if report_path is not None:
        _annotate_report(report_path)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
