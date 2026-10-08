#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.6.

Replays the exact Pysheds pour-point semantics used to create each frozen geometry on the
binary-identical geometry-generation DEM. The frozen polygon remains the sole metric mask;
the replayed catchment is used only to validate routing provenance and to compute weighted
D8 distance to the same geometry-generation pour-point coordinate. No outcome, A6680
numeric reference, rainfall, or post-anchor predictor is read.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from pysheds.grid import Grid

import compute_chosica_2015_morphometry_phase1_v4 as v4

v3 = v4.v3
v2 = v4.v2
base = v4.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V6 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_6.json"
DEM_PATH_BY_TARGET: dict[str, Path] = {}
REPLAY_AUDIT: dict[str, dict] = {}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_exact_dem_capture(td: Path, cache: Path, diagnostic_bbox, expected):
    target_id = v2.CURRENT_TARGET
    if target_id is None:
        raise RuntimeError("FAIL_CLOSED_REPLAY_TARGET_CONTEXT")
    dem_path, provenance = v4.build_exact_frozen_geometry_dem(td, cache, diagnostic_bbox, expected)
    DEM_PATH_BY_TARGET[target_id] = Path(dem_path)
    return dem_path, provenance


def _drainage_density_unchanged(
    fdir: np.ndarray,
    accumulation: np.ndarray,
    basin: np.ndarray,
    area_m2: float,
    dx: float,
    dy: float,
):
    rows, cols = fdir.shape
    threshold_m2 = 0.01 * area_m2
    acc_area = np.asarray(accumulation, dtype="float64") * base.CELL_AREA_M2
    channel = basin & (acc_area >= threshold_m2)
    channel_length = 0.0
    qualifying_links = 0
    for r, c in np.argwhere(channel):
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if 0 <= nr < rows and 0 <= nc < cols and basin[nr, nc]:
            channel_length += math.hypot(dx * step[1], dy * step[0])
            qualifying_links += 1
    return {
        "channel_contributing_area_threshold_m2": threshold_m2,
        "channel_qualifying_link_count": qualifying_links,
        "channel_length_km": channel_length / 1000.0,
        "drainage_density_km_per_km2": (channel_length / 1000.0) / (area_m2 / 1e6),
    }


def d8_metrics_exact_geometry_replay(
    fdir: np.ndarray,
    accumulation: np.ndarray,
    basin: np.ndarray,
    outlet_rc,
    area_m2: float,
    dx: float,
    dy: float,
):
    target_id = v2.CURRENT_TARGET
    if target_id is None or target_id not in DEM_PATH_BY_TARGET:
        raise RuntimeError("FAIL_CLOSED_REPLAY_MISSING_DEM_CONTEXT")
    dem_path = DEM_PATH_BY_TARGET[target_id]
    registry = base.load_json(base.REGISTRY)
    frozen_outlet = registry["targets"][target_id]["accepted_outlet"]

    with rasterio.open(dem_path) as ds:
        transform = ds.transform
        rasterio_row, rasterio_col = int(outlet_rc[0]), int(outlet_rc[1])
        cx, cy = rasterio.transform.xy(transform, rasterio_row, rasterio_col, offset="center")
        cx, cy = float(cx), float(cy)

    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))
    dem = grid.fill_pits(dem)
    dem = grid.fill_depressions(dem)
    dem = grid.resolve_flats(dem)
    replay_fdir = grid.flowdir(dem, dirmap=base.D8)
    replay_fdir_arr = np.asarray(replay_fdir)
    if replay_fdir_arr.shape != fdir.shape or not np.array_equal(replay_fdir_arr, fdir):
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_FLOWDIR_MISMATCH {target_id}")

    nearest = grid.nearest_cell(cx, cy)
    if len(nearest) != 2:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_NEAREST_CELL_SHAPE {target_id}")
    pysheds_col, pysheds_row = int(nearest[0]), int(nearest[1])
    if not (0 <= pysheds_row < fdir.shape[0] and 0 <= pysheds_col < fdir.shape[1]):
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_NEAREST_CELL_OUTSIDE {target_id}")
    with rasterio.open(dem_path) as ds:
        pcx, pcy = rasterio.transform.xy(ds.transform, pysheds_row, pysheds_col, offset="center")
    pcx, pcy = float(pcx), float(pcy)
    internal_cell_distance_to_frozen_outlet_m = math.hypot(
        pcx - float(frozen_outlet["x_m"]),
        pcy - float(frozen_outlet["y_m"]),
    )
    if internal_cell_distance_to_frozen_outlet_m > math.hypot(dx, dy) + 1e-6:
        raise RuntimeError(
            f"FAIL_CLOSED_REPLAY_INTERNAL_POURPOINT_TOLERANCE {target_id} "
            f"{internal_cell_distance_to_frozen_outlet_m:.9f}"
        )

    replay_catch = np.asarray(
        grid.catchment(
            x=cx,
            y=cy,
            fdir=replay_fdir,
            dirmap=base.D8,
            xytype="coordinate",
        )
    ).astype(bool)
    if replay_catch.shape != basin.shape:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_CATCHMENT_SHAPE {target_id}")

    intersection = basin & replay_catch
    union = basin | replay_catch
    basin_count = int(basin.sum())
    replay_count = int(replay_catch.sum())
    intersection_count = int(intersection.sum())
    union_count = int(union.sum())
    coverage = intersection_count / basin_count if basin_count else 0.0
    jaccard = intersection_count / union_count if union_count else 0.0
    if coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_POLYGON_COVERAGE {target_id} {coverage:.9f}")
    if jaccard < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_POLYGON_JACCARD {target_id} {jaccard:.9f}")

    cell_dist = grid.cell_distances(replay_fdir, dirmap=base.D8)
    cell_dist_arr = np.asarray(cell_dist, dtype="float64")
    finite_positive = cell_dist_arr[np.isfinite(cell_dist_arr) & (cell_dist_arr > 0)]
    if finite_positive.size == 0:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_EMPTY_CELL_DISTANCES {target_id}")
    min_positive = float(np.min(finite_positive))
    max_positive = float(np.max(finite_positive))
    if min_positive < min(dx, dy) - 1e-6 or max_positive > math.hypot(dx, dy) + 1e-6:
        raise RuntimeError(
            f"FAIL_CLOSED_REPLAY_CELL_DISTANCE_RANGE {target_id} "
            f"{min_positive:.9f} {max_positive:.9f}"
        )

    flow_dist = np.asarray(
        grid.distance_to_outlet(
            x=cx,
            y=cy,
            fdir=replay_fdir,
            weights=cell_dist,
            dirmap=base.D8,
            xytype="coordinate",
        ),
        dtype="float64",
    )
    reached = intersection & np.isfinite(flow_dist)
    reached_count = int(reached.sum())
    routing_coverage = reached_count / basin_count if basin_count else 0.0
    if routing_coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_DISTANCE_COVERAGE {target_id} {routing_coverage:.9f}")
    main_length = float(np.max(flow_dist[reached])) if reached_count else float("nan")
    if not math.isfinite(main_length) or main_length < 0:
        raise RuntimeError(f"FAIL_CLOSED_REPLAY_MAIN_CHANNEL_LENGTH {target_id}")

    drainage = _drainage_density_unchanged(fdir, accumulation, basin, area_m2, dx, dy)
    audit = {
        "target_id": target_id,
        "replay_method": "EXACT_ORIGINAL_PYSHEDS_GEOMETRY_POURPOINT_SEMANTICS",
        "rasterio_containing_cell_row": rasterio_row,
        "rasterio_containing_cell_col": rasterio_col,
        "geometry_generation_coordinate_x_m": cx,
        "geometry_generation_coordinate_y_m": cy,
        "pysheds_nearest_cell_row": pysheds_row,
        "pysheds_nearest_cell_col": pysheds_col,
        "pysheds_nearest_cell_center_x_m": pcx,
        "pysheds_nearest_cell_center_y_m": pcy,
        "pysheds_cell_row_offset_from_rasterio": pysheds_row - rasterio_row,
        "pysheds_cell_col_offset_from_rasterio": pysheds_col - rasterio_col,
        "pysheds_internal_cell_distance_to_frozen_outlet_m": internal_cell_distance_to_frozen_outlet_m,
        "frozen_polygon_center_cell_count": basin_count,
        "replayed_catchment_cell_count": replay_count,
        "replay_intersection_cell_count": intersection_count,
        "replay_union_cell_count": union_count,
        "replay_polygon_coverage_fraction": coverage,
        "replay_polygon_jaccard": jaccard,
        "weighted_distance_cell_min_positive_m": min_positive,
        "weighted_distance_cell_max_positive_m": max_positive,
        "manual_reverse_d8_used": False,
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
        "drainage_density_rule_changed": False,
    }
    REPLAY_AUDIT[target_id] = dict(audit)
    return {
        "routing_coverage_fraction": routing_coverage,
        "routing_reached_cell_count": reached_count,
        "basin_center_cell_count": basin_count,
        "main_channel_length_m": main_length,
        **drainage,
        **audit,
    }


def annotate_report(report_path: Path) -> None:
    v4.annotate_report(report_path)
    if not report_path.exists():
        return
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    doc["execution_revision"] = "0.6_EXACT_GEOMETRY_POURPOINT_REPLAY"
    doc["replay_implementation_sha256"] = sha256_path(Path(__file__).resolve())
    doc["original_geometry_pourpoint_replay_audit"] = REPLAY_AUDIT
    doc["revision_guards"] = {
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "selection_or_tuning_from_metric_values": False,
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
    }
    report_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    base.EXECUTION = EXECUTION_V6
    base.build_exact_geometry_dem = build_exact_dem_capture
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = d8_metrics_exact_geometry_replay
    base.__file__ = str(Path(__file__).resolve())

    import sys
    report_path = None
    for idx, arg in enumerate(sys.argv[:-1]):
        if arg == "--report":
            report_path = Path(sys.argv[idx + 1])
            break

    rc = base.main()
    if report_path is not None:
        annotate_report(report_path)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
