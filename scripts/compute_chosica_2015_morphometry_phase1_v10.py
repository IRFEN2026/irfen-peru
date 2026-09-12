#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.10.

Use one Pysheds Grid per target. For the five geometries frozen with Pysheds catchment
semantics, invoke the exact geometry-generation catchment call on that same Grid/fdir and
validate it against the unchanged frozen polygon. Compute weighted D8 path distance with a
deterministic graph traversal on that exact validated catchment, avoiding a redundant native
Grid/distance kernel. Cashahuacra retains its frozen manual reverse-D8 semantics.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import rasterio
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.features import geometry_mask
from shapely.ops import transform as shp_transform

import compute_chosica_2015_morphometry_phase1_v6 as v6

v4 = v6.v4
v3 = v6.v3
v2 = v6.v2
base = v6.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V10 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_10.json"
TARGET_KEYS = tuple(base.TARGET_KEYS)
GUARDS = {
    "RESEARCH_ONLY": True,
    "TEST_ONLY": True,
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
}
CATCHMENT_AUDIT: dict[str, dict] = {}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_frozen_gate() -> tuple[dict, dict, dict]:
    registry = load_json(base.REGISTRY)
    method = load_json(base.METHOD)
    execution = load_json(EXECUTION_V10)
    if registry["guards"] != GUARDS or method["guards"] != GUARDS or execution["guards"] != GUARDS:
        raise RuntimeError("FAIL_CLOSED_GUARD_MISMATCH")
    gate = registry["batch_gate"]
    if gate["frozen_outlet_count"] != 6 or gate["frozen_geometry_count"] != 6:
        raise RuntimeError("FAIL_CLOSED_FROZEN_BATCH_COUNT")
    if gate["batch_morphometry_allowed"] is not True or gate["unblind_allowed"] is not False:
        raise RuntimeError("FAIL_CLOSED_BATCH_GATE")
    if method["input_gate"]["a6680_numeric_reference_access_before_output_freeze"] is not False:
        raise RuntimeError("FAIL_CLOSED_A6680_GATE")
    phase = execution["phase_1_output"]
    if phase["a6680_numeric_reference_read"] is not False:
        raise RuntimeError("FAIL_CLOSED_EXECUTION_A6680_GUARD")
    if phase["outcome_evidence_read"] is not False or phase["post_anchor_predictor_read"] is not False:
        raise RuntimeError("FAIL_CLOSED_EXECUTION_BLIND_GUARD")
    if execution["revision_basis"]["prior_execution_target_count"] != 0:
        raise RuntimeError("FAIL_CLOSED_PRIOR_TARGET_COUNT")
    if execution["revision_basis"]["prior_execution_metrics_observed"] is not False:
        raise RuntimeError("FAIL_CLOSED_PRIOR_METRIC_OBSERVATION")
    for key in TARGET_KEYS:
        target = registry["targets"][key]
        if target["outlet_status"] != "FROZEN":
            raise RuntimeError(f"FAIL_CLOSED_OUTLET_NOT_FROZEN {key}")
        if target["geometry_status"] != "FROZEN_BY_REPRODUCIBLE_D8_HASH":
            raise RuntimeError(f"FAIL_CLOSED_GEOMETRY_NOT_FROZEN {key}")
    return registry, method, execution


def _distance_on_exact_catchment(
    fdir: np.ndarray,
    catchment: np.ndarray,
    outlet_rc: tuple[int, int],
    dx: float,
    dy: float,
) -> np.ndarray:
    rows, cols = fdir.shape
    orow, ocol = int(outlet_rc[0]), int(outlet_rc[1])
    if not (0 <= orow < rows and 0 <= ocol < cols):
        raise RuntimeError("FAIL_CLOSED_DISTANCE_OUTLET_OUTSIDE")
    if not catchment[orow, ocol]:
        raise RuntimeError("FAIL_CLOSED_EXACT_CATCHMENT_EXCLUDES_POURPOINT")
    upstream: dict[int, list[tuple[int, int, float]]] = {}
    for r, c in np.argwhere(catchment):
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if not (0 <= nr < rows and 0 <= nc < cols) or not catchment[nr, nc]:
            continue
        link = math.hypot(dx * step[1], dy * step[0])
        upstream.setdefault(nr * cols + nc, []).append((int(r), int(c), link))
    dist = np.full((rows, cols), np.nan, dtype="float64")
    dist[orow, ocol] = 0.0
    q = deque([(orow, ocol)])
    while q:
        r, c = q.popleft()
        downstream_distance = float(dist[r, c])
        for ur, uc, link in upstream.get(r * cols + c, []):
            if math.isnan(dist[ur, uc]):
                dist[ur, uc] = downstream_distance + link
                q.append((ur, uc))
    return dist


def _exact_pysheds_routing_metrics(
    target_id: str,
    grid: Grid,
    replay_catch: np.ndarray,
    fdir: np.ndarray,
    accumulation: np.ndarray,
    basin: np.ndarray,
    outlet_rc,
    frozen_outlet: dict,
    area_m2: float,
    dx: float,
    dy: float,
    transform,
):
    rasterio_row, rasterio_col = int(outlet_rc[0]), int(outlet_rc[1])
    cx, cy = rasterio.transform.xy(transform, rasterio_row, rasterio_col, offset="center")
    cx, cy = float(cx), float(cy)
    nearest = grid.nearest_cell(cx, cy)
    if len(nearest) != 2:
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_NEAREST_CELL_SHAPE {target_id}")
    pysheds_col, pysheds_row = int(nearest[0]), int(nearest[1])
    if not (0 <= pysheds_row < fdir.shape[0] and 0 <= pysheds_col < fdir.shape[1]):
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_NEAREST_CELL_OUTSIDE {target_id}")
    pcx, pcy = rasterio.transform.xy(transform, pysheds_row, pysheds_col, offset="center")
    pcx, pcy = float(pcx), float(pcy)
    internal_distance = math.hypot(
        pcx - float(frozen_outlet["x_m"]),
        pcy - float(frozen_outlet["y_m"]),
    )
    if internal_distance > math.hypot(dx, dy) + 1e-6:
        raise RuntimeError(
            f"FAIL_CLOSED_SINGLE_GRID_INTERNAL_POURPOINT_TOLERANCE {target_id} {internal_distance:.9f}"
        )
    if replay_catch.shape != basin.shape:
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_CATCHMENT_SHAPE {target_id}")

    intersection = basin & replay_catch
    union = basin | replay_catch
    basin_count = int(basin.sum())
    replay_count = int(replay_catch.sum())
    intersection_count = int(intersection.sum())
    union_count = int(union.sum())
    coverage = intersection_count / basin_count if basin_count else 0.0
    jaccard = intersection_count / union_count if union_count else 0.0
    if coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_POLYGON_COVERAGE {target_id} {coverage:.9f}")
    if jaccard < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_POLYGON_JACCARD {target_id} {jaccard:.9f}")

    flow_dist = _distance_on_exact_catchment(
        fdir, replay_catch, (pysheds_row, pysheds_col), dx, dy
    )
    reached = intersection & np.isfinite(flow_dist)
    reached_count = int(reached.sum())
    routing_coverage = reached_count / basin_count if basin_count else 0.0
    if routing_coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_DISTANCE_COVERAGE {target_id} {routing_coverage:.9f}")
    main_length = float(np.max(flow_dist[reached])) if reached_count else float("nan")
    if not math.isfinite(main_length) or main_length < 0:
        raise RuntimeError(f"FAIL_CLOSED_SINGLE_GRID_MAIN_CHANNEL_LENGTH {target_id}")

    drainage = v6._drainage_density_unchanged(fdir, accumulation, basin, area_m2, dx, dy)
    audit = {
        "target_id": target_id,
        "replay_method": "EXACT_ORIGINAL_PYSHEDS_CATCHMENT_ON_SINGLE_GRID",
        "routing_replay_method": "FROZEN_GENERATOR_PYSHEDS_CATCHMENT_FROM_CONTAINING_CELL_CENTER",
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
        "pysheds_internal_cell_distance_to_frozen_outlet_m": internal_distance,
        "frozen_polygon_center_cell_count": basin_count,
        "replayed_catchment_cell_count": replay_count,
        "replay_intersection_cell_count": intersection_count,
        "replay_union_cell_count": union_count,
        "replay_polygon_coverage_fraction": coverage,
        "replay_polygon_jaccard": jaccard,
        "routing_coverage_fraction": routing_coverage,
        "single_grid_instance_used": True,
        "second_native_grid_invoked": False,
        "second_dem_conditioning_invoked": False,
        "second_flowdir_computation_invoked": False,
        "pysheds_catchment_api_invoked": True,
        "pysheds_distance_to_outlet_invoked": False,
        "weighted_distance_algorithm": "DETERMINISTIC_REVERSE_D8_ON_EXACT_PYSHEDS_CATCHMENT",
        "weighted_distance_orthogonal_link_m": float(min(dx, dy)),
        "weighted_distance_diagonal_link_m": float(math.hypot(dx, dy)),
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
        "drainage_density_rule_changed": False,
    }
    CATCHMENT_AUDIT[target_id] = dict(audit)
    return {
        "routing_coverage_fraction": routing_coverage,
        "routing_reached_cell_count": reached_count,
        "basin_center_cell_count": basin_count,
        "main_channel_length_m": main_length,
        **drainage,
        **audit,
    }


def target_metrics_single_grid(
    key: str,
    geom_path: Path,
    registry: dict,
    expected_tiles: dict,
    cache: Path,
    work: Path,
):
    if v2.CURRENT_TARGET is not None:
        raise RuntimeError("FAIL_CLOSED_SINGLE_GRID_NESTED_TARGET_CONTEXT")
    v2.CURRENT_TARGET = key
    try:
        frozen = registry["targets"][key]
        gfreeze = frozen["geometry_freeze"]
        if base.sha256_path(geom_path) != gfreeze["geometry_geojson_sha256"]:
            raise RuntimeError(f"FAIL_CLOSED_FROZEN_GEOMETRY_HASH {key}")
        geom_wgs = base.load_geometry(geom_path)
        geom_utm = shp_transform(
            Transformer.from_crs("EPSG:4326", base.DST, always_xy=True).transform,
            geom_wgs,
        )
        if geom_utm.geom_type not in {"Polygon", "MultiPolygon"}:
            raise RuntimeError(f"FAIL_CLOSED_NONPOLYGON_GEOMETRY {key}")
        area_m2 = float(geom_utm.area)
        perimeter_m = float(geom_utm.length)
        if area_m2 <= 0 or perimeter_m <= 0:
            raise RuntimeError(f"FAIL_CLOSED_NONPOSITIVE_GEOMETRY_METRIC {key}")

        report_path = ROOT / gfreeze["diagnostic_path"]
        report = base.load_json(report_path)
        diagnostic_bbox = base.geometry_bbox_from_report(report)
        td = work / key
        td.mkdir(parents=True, exist_ok=True)
        dem_path, provenance = v6.build_exact_dem_capture(td, cache, diagnostic_bbox, expected_tiles)
        legacy_dem_file_sha256 = base.sha256_path(dem_path)
        semantic_sha256, semantic_meta = base.semantic_dem_fingerprint(dem_path)

        with rasterio.open(dem_path) as ds:
            z = ds.read(1).astype("float64")
            transform = ds.transform
            nodata = ds.nodata
            dx, dy = abs(float(transform.a)), abs(float(transform.e))
            valid = np.isfinite(z)
            if nodata is not None:
                valid &= z != float(nodata)
            basin_mask = geometry_mask(
                [geom_utm.__geo_interface__],
                out_shape=z.shape,
                transform=transform,
                invert=True,
                all_touched=False,
            )
            basin = basin_mask & valid
            values = z[basin]
            if values.size == 0:
                raise RuntimeError(f"FAIL_CLOSED_EMPTY_ELEVATION_MASK {key}")
            slopes = base.horn_slope_deg(z, valid, dx, dy)
            slope_values = slopes[basin & np.isfinite(slopes)]
            if slope_values.size == 0:
                raise RuntimeError(f"FAIL_CLOSED_EMPTY_SLOPE_MASK {key}")
            outlet = frozen["accepted_outlet"]
            outlet_rc = ds.index(float(outlet["x_m"]), float(outlet["y_m"]))
            outlet_center = rasterio.transform.xy(transform, *outlet_rc, offset="center")
            outlet_distance = math.hypot(
                float(outlet_center[0]) - float(outlet["x_m"]),
                float(outlet_center[1]) - float(outlet["y_m"]),
            )
            if outlet_distance > math.hypot(dx, dy):
                raise RuntimeError(f"FAIL_CLOSED_OUTLET_MAPPING_TOLERANCE {key}")

        grid = Grid.from_raster(str(dem_path))
        dem = grid.read_raster(str(dem_path))
        dem = grid.fill_pits(dem)
        dem = grid.fill_depressions(dem)
        dem = grid.resolve_flats(dem)
        fdir_raster = grid.flowdir(dem, dirmap=base.D8)
        fdir = np.asarray(fdir_raster)

        if key == "cashahuacra":
            accumulation = np.asarray(grid.accumulation(fdir_raster, dirmap=base.D8))
            hydro = v3.d8_metrics_with_frozen_pourpoint(
                fdir, accumulation, basin, outlet_rc, area_m2, dx, dy
            )
            audit = {
                "target_id": key,
                "replay_method": "FROZEN_GENERATOR_MANUAL_REVERSE_D8_FROM_FROZEN_ROW_COL",
                "routing_replay_method": "FROZEN_GENERATOR_MANUAL_REVERSE_D8_FROM_FROZEN_ROW_COL",
                "routing_coverage_fraction": float(hydro["routing_coverage_fraction"]),
                "single_grid_instance_used": True,
                "second_native_grid_invoked": False,
                "second_dem_conditioning_invoked": False,
                "second_flowdir_computation_invoked": False,
                "pysheds_catchment_api_invoked": False,
                "pysheds_distance_to_outlet_invoked": False,
                "frozen_polygon_mask_modified": False,
                "frozen_outlet_modified": False,
                "drainage_density_rule_changed": False,
            }
            CATCHMENT_AUDIT[key] = dict(audit)
            hydro = {**hydro, **audit}
        else:
            # Exact frozen generator order: conditioning -> flowdir -> catchment.
            replay_catch = np.asarray(
                grid.catchment(
                    x=float(outlet_center[0]),
                    y=float(outlet_center[1]),
                    fdir=fdir_raster,
                    dirmap=base.D8,
                    xytype="coordinate",
                )
            ).astype(bool)
            accumulation = np.asarray(grid.accumulation(fdir_raster, dirmap=base.D8))
            hydro = _exact_pysheds_routing_metrics(
                key,
                grid,
                replay_catch,
                fdir,
                accumulation,
                basin,
                outlet_rc,
                outlet,
                area_m2,
                dx,
                dy,
                transform,
            )

        return {
            "target_id": key,
            "hydrologic_identity": "corrales" if key == "rayos_de_sol" else key,
            "geometry_geojson_sha256": base.sha256_path(geom_path),
            "geometry_diagnostic_sha256": base.sha256_path(report_path),
            "legacy_dem_geotiff_sha256": legacy_dem_file_sha256,
            "legacy_geometry_registry_dem_geotiff_sha256": gfreeze["dem_utm_sha256"],
            "legacy_geotiff_binary_equality_required": True,
            "semantic_dem_sha256": semantic_sha256,
            "semantic_dem_metadata": semantic_meta,
            "dem_bbox_wgs84": [round(v, 8) for v in diagnostic_bbox],
            "source_tiles": provenance,
            "outlet_grid_cell": {
                "row": int(outlet_rc[0]),
                "col": int(outlet_rc[1]),
                "center_distance_to_frozen_outlet_m": round(outlet_distance, 6),
            },
            "area_km2": round(area_m2 / 1e6, 9),
            "perimeter_km": round(perimeter_m / 1000.0, 9),
            "elevation_min_m": round(float(np.min(values)), 6),
            "elevation_max_m": round(float(np.max(values)), 6),
            "relief_m": round(float(np.max(values) - np.min(values)), 6),
            "mean_basin_slope_deg": round(float(np.mean(slope_values)), 9),
            "median_basin_slope_deg": round(float(np.median(slope_values)), 9),
            "p90_basin_slope_deg": round(float(np.percentile(slope_values, 90)), 9),
            "slope_valid_cell_count": int(slope_values.size),
            **{k: (round(v, 9) if isinstance(v, float) else v) for k, v in hydro.items()},
        }
    finally:
        v2.CURRENT_TARGET = None


def worker_main(args: argparse.Namespace) -> int:
    registry, _method, _execution = validate_frozen_gate()
    args.worker_report.parent.mkdir(parents=True, exist_ok=True)
    args.cache_root.mkdir(parents=True, exist_ok=True)
    args.worker_work.mkdir(parents=True, exist_ok=True)
    expected = base.expected_tile_hashes(registry)
    geom_path = base.find_geometry(args.geometry_root, args.worker_target)
    target = target_metrics_single_grid(
        args.worker_target,
        geom_path,
        registry,
        expected,
        args.cache_root,
        args.worker_work,
    )
    if set(v4.EXACT_DEM_AUDIT) != {args.worker_target}:
        raise RuntimeError(f"FAIL_CLOSED_WORKER_EXACT_DEM_AUDIT {args.worker_target}")
    if set(CATCHMENT_AUDIT) != {args.worker_target}:
        raise RuntimeError(f"FAIL_CLOSED_WORKER_CATCHMENT_AUDIT {args.worker_target}")
    if args.worker_target == "cashahuacra" and set(v3.POURPOINT_AUDIT) != {args.worker_target}:
        raise RuntimeError("FAIL_CLOSED_CASHAHUACRA_POURPOINT_AUDIT")
    doc = {
        "schema_version": "0.10-worker",
        "target_id": args.worker_target,
        "guards": GUARDS,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "target": target,
        "exact_geometry_dem_audit": v4.EXACT_DEM_AUDIT[args.worker_target],
        "exact_pysheds_catchment_audit": CATCHMENT_AUDIT[args.worker_target],
        "pourpoint_semantics_audit": v3.POURPOINT_AUDIT.get(args.worker_target),
    }
    args.worker_report.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def coordinator_main(args: argparse.Namespace) -> int:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    registry, _method, execution = validate_frozen_gate()
    result = {
        "schema_version": "0.10",
        "batch_id": registry["batch_id"],
        "status": "PENDING",
        "phase": "PHASE_1_PREUNBLIND_DEM_MORPHOMETRY",
        "execution_revision": "0.10_SINGLE_GRID_EXACT_PYSHEDS_CATCHMENT",
        "guards": GUARDS,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "registry_sha256": sha256_path(base.REGISTRY),
        "morphometry_contract_sha256": sha256_path(base.METHOD),
        "execution_contract_sha256": sha256_path(EXECUTION_V10),
        "implementation_sha256": sha256_path(Path(__file__).resolve()),
        "target_count": 0,
        "targets": [],
        "worker_execution_audit": {},
        "exact_geometry_dem_audit": {},
        "exact_pysheds_catchment_audit": {},
        "pourpoint_semantics_audit": {},
        "revision_guards": {
            "a6680_numeric_reference_read": False,
            "outcome_evidence_read": False,
            "post_anchor_predictor_read": False,
            "selection_or_tuning_from_metric_values": False,
            "frozen_polygon_mask_modified": False,
            "frozen_outlet_modified": False,
            "scientific_quantity_changed": False,
            "single_grid_exact_pysheds_catchment": True,
            "pysheds_distance_kernel_removed": True,
            "one_target_per_fresh_python_process": True,
        },
    }
    try:
        with tempfile.TemporaryDirectory(prefix="irfen_chosica_2015_morphometry_v10_") as raw:
            root = Path(raw)
            cache = root / "tile_cache"; cache.mkdir()
            reports = root / "worker_reports"; reports.mkdir()
            work = root / "worker_work"; work.mkdir()
            completed: list[str] = []
            for key in TARGET_KEYS:
                worker_report = reports / f"{key}.json"
                cmd = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--geometry-root", str(args.geometry_root),
                    "--worker-target", key,
                    "--worker-report", str(worker_report),
                    "--cache-root", str(cache),
                    "--worker-work", str(work / key),
                ]
                proc = subprocess.run(cmd, text=True, capture_output=True)
                result["worker_execution_audit"][key] = {
                    "return_code": int(proc.returncode),
                    "fresh_python_process": True,
                    "worker_report_persisted": worker_report.exists(),
                }
                if proc.returncode != 0:
                    result["status"] = "FAIL_CLOSED_PHASE1_MORPHOMETRY"
                    result["error"] = f"FAIL_CLOSED_WORKER_PROCESS {key} return_code={proc.returncode}"
                    result["failed_worker_target"] = key
                    result["completed_worker_ids_before_failure"] = completed
                    result["worker_stderr_tail"] = proc.stderr[-4000:]
                    result["worker_stdout_tail"] = proc.stdout[-4000:]
                    args.report.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return 2
                if not worker_report.exists():
                    raise RuntimeError(f"FAIL_CLOSED_MISSING_WORKER_REPORT {key}")
                completed.append(key)

            docs = {key: load_json(reports / f"{key}.json") for key in TARGET_KEYS}
            for key in TARGET_KEYS:
                doc = docs[key]
                if doc["target_id"] != key or doc["guards"] != GUARDS:
                    raise RuntimeError(f"FAIL_CLOSED_WORKER_REPORT_IDENTITY {key}")
                if doc["a6680_numeric_reference_read"] is not False or doc["outcome_evidence_read"] is not False or doc["post_anchor_predictor_read"] is not False:
                    raise RuntimeError(f"FAIL_CLOSED_WORKER_BLIND_GUARD {key}")
                result["targets"].append(doc["target"])
                result["exact_geometry_dem_audit"][key] = doc["exact_geometry_dem_audit"]
                result["exact_pysheds_catchment_audit"][key] = doc["exact_pysheds_catchment_audit"]
                if doc["pourpoint_semantics_audit"] is not None:
                    result["pourpoint_semantics_audit"][key] = doc["pourpoint_semantics_audit"]

        result["target_count"] = len(result["targets"])
        if result["target_count"] != execution["phase_1_output"]["required_target_count"]:
            raise RuntimeError("FAIL_CLOSED_TARGET_COUNT")
        result["status"] = "PASS_CHOSICA_2015_PHASE1_MORPHOMETRY"
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": result["status"], "target_count": result["target_count"]}, sort_keys=True))
        return 0
    except Exception as exc:
        result["status"] = "FAIL_CLOSED_PHASE1_MORPHOMETRY"
        result["error"] = str(exc)
        result["targets"] = []
        result["target_count"] = 0
        result["exact_geometry_dem_audit"] = {}
        result["exact_pysheds_catchment_audit"] = {}
        result["pourpoint_semantics_audit"] = {}
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 2


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry-root", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--worker-target", choices=TARGET_KEYS)
    ap.add_argument("--worker-report", type=Path)
    ap.add_argument("--cache-root", type=Path)
    ap.add_argument("--worker-work", type=Path)
    args = ap.parse_args()
    if args.worker_target is None:
        if args.report is None:
            ap.error("--report is required in coordinator mode")
    else:
        for name in ("worker_report", "cache_root", "worker_work"):
            if getattr(args, name) is None:
                ap.error(f"--{name.replace('_', '-')} is required in worker mode")
    return args


def main() -> int:
    args = parse_args()
    return worker_main(args) if args.worker_target is not None else coordinator_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
