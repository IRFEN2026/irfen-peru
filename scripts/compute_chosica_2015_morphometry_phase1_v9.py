#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.9.

For the five geometries originally generated with Pysheds catchment semantics, replay the
same D8 topology directly from the already-computed first-pass flow-direction array instead
of constructing a redundant second native Pysheds grid. Cashahuacra retains its frozen
manual reverse-D8 semantics. Each target remains isolated in a fresh Python process.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio

import compute_chosica_2015_morphometry_phase1_v7 as v7

v6 = v7.v6
v4 = v7.v4
v3 = v7.v3
v2 = v7.v2
base = v7.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V9 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_9.json"
TARGET_KEYS = tuple(base.TARGET_KEYS)
GUARDS = {
    "RESEARCH_ONLY": True,
    "TEST_ONLY": True,
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
}
TOPOLOGY_REPLAY_AUDIT: dict[str, dict] = {}


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
    execution = load_json(EXECUTION_V9)
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


def _reverse_d8_replay(fdir: np.ndarray, outlet_rc: tuple[int, int], dx: float, dy: float):
    """Return exact upstream D8 reachability and distance to a fixed pour-point cell.

    A cell belongs iff repeatedly following the immutable D8 direction reaches the pour
    point. Reverse traversal is the topology-equivalent implementation of that definition.
    """
    rows, cols = fdir.shape
    orow, ocol = int(outlet_rc[0]), int(outlet_rc[1])
    if not (0 <= orow < rows and 0 <= ocol < cols):
        raise RuntimeError("FAIL_CLOSED_TOPOLOGY_REPLAY_OUTLET_OUTSIDE")
    reached = np.zeros((rows, cols), dtype=bool)
    dist = np.full((rows, cols), np.nan, dtype="float64")
    reached[orow, ocol] = True
    dist[orow, ocol] = 0.0
    q = deque([(orow, ocol)])
    while q:
        r, c = q.popleft()
        downstream_distance = float(dist[r, c])
        r0, r1 = max(0, r - 1), min(rows - 1, r + 1)
        c0, c1 = max(0, c - 1), min(cols - 1, c + 1)
        for ur in range(r0, r1 + 1):
            for uc in range(c0, c1 + 1):
                if ur == r and uc == c or reached[ur, uc]:
                    continue
                step = base.D8_STEPS.get(int(fdir[ur, uc]))
                if step is None:
                    continue
                if ur + step[0] != r or uc + step[1] != c:
                    continue
                link = math.hypot(dx * step[1], dy * step[0])
                reached[ur, uc] = True
                dist[ur, uc] = downstream_distance + link
                q.append((ur, uc))
    return reached, dist


def d8_metrics_topology_equivalent(
    fdir: np.ndarray,
    accumulation: np.ndarray,
    basin: np.ndarray,
    outlet_rc,
    area_m2: float,
    dx: float,
    dy: float,
):
    target_id = v2.CURRENT_TARGET
    if target_id is None:
        raise RuntimeError("FAIL_CLOSED_TOPOLOGY_REPLAY_TARGET_CONTEXT")
    if target_id == "cashahuacra":
        out = v3.d8_metrics_with_frozen_pourpoint(
            fdir, accumulation, basin, outlet_rc, area_m2, dx, dy
        )
        audit = {
            "target_id": target_id,
            "routing_replay_method": "FROZEN_GENERATOR_MANUAL_REVERSE_D8_FROM_FROZEN_ROW_COL",
            "pysheds_catchment_api_invoked": False,
            "second_native_grid_invoked": False,
            "manual_reverse_d8_used": True,
            "frozen_polygon_mask_modified": False,
            "frozen_outlet_modified": False,
            "drainage_density_rule_changed": False,
            "routing_coverage_fraction": float(out["routing_coverage_fraction"]),
        }
        TOPOLOGY_REPLAY_AUDIT[target_id] = dict(audit)
        return {**out, **audit}

    if target_id not in v6.DEM_PATH_BY_TARGET:
        raise RuntimeError(f"FAIL_CLOSED_TOPOLOGY_REPLAY_MISSING_DEM {target_id}")
    dem_path = v6.DEM_PATH_BY_TARGET[target_id]
    registry = base.load_json(base.REGISTRY)
    frozen_outlet = registry["targets"][target_id]["accepted_outlet"]
    with rasterio.open(dem_path) as ds:
        rasterio_row, rasterio_col = int(outlet_rc[0]), int(outlet_rc[1])
        cx, cy = rasterio.transform.xy(ds.transform, rasterio_row, rasterio_col, offset="center")
    cx, cy = float(cx), float(cy)
    internal_cell_distance = math.hypot(
        cx - float(frozen_outlet["x_m"]), cy - float(frozen_outlet["y_m"])
    )
    if internal_cell_distance > math.hypot(dx, dy) + 1e-6:
        raise RuntimeError(
            f"FAIL_CLOSED_TOPOLOGY_REPLAY_INTERNAL_POURPOINT_TOLERANCE {target_id} {internal_cell_distance:.9f}"
        )

    replay_catch, flow_dist = _reverse_d8_replay(fdir, (rasterio_row, rasterio_col), dx, dy)
    intersection = basin & replay_catch
    union = basin | replay_catch
    basin_count = int(basin.sum())
    replay_count = int(replay_catch.sum())
    intersection_count = int(intersection.sum())
    union_count = int(union.sum())
    coverage = intersection_count / basin_count if basin_count else 0.0
    jaccard = intersection_count / union_count if union_count else 0.0
    if coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_TOPOLOGY_REPLAY_POLYGON_COVERAGE {target_id} {coverage:.9f}")
    if jaccard < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_TOPOLOGY_REPLAY_POLYGON_JACCARD {target_id} {jaccard:.9f}")

    reached = intersection & np.isfinite(flow_dist)
    reached_count = int(reached.sum())
    routing_coverage = reached_count / basin_count if basin_count else 0.0
    if routing_coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_TOPOLOGY_REPLAY_DISTANCE_COVERAGE {target_id} {routing_coverage:.9f}")
    main_length = float(np.max(flow_dist[reached])) if reached_count else float("nan")
    if not math.isfinite(main_length) or main_length < 0:
        raise RuntimeError(f"FAIL_CLOSED_TOPOLOGY_REPLAY_MAIN_CHANNEL_LENGTH {target_id}")

    drainage = v6._drainage_density_unchanged(fdir, accumulation, basin, area_m2, dx, dy)
    audit = {
        "target_id": target_id,
        "replay_method": "EXACT_PYSHEDS_CATCHMENT_SEMANTICS_TOPOLOGY_EQUIVALENT_REVERSE_D8",
        "routing_replay_method": "FROZEN_GENERATOR_PYSHEDS_SEMANTICS_REVERSE_D8_TO_CONTAINING_CELL_CENTER",
        "semantic_equivalence_basis": "ALL_CELLS_WHOSE_UNCHANGED_D8_PATH_REACHES_UNCHANGED_CONTAINING_CELL_CENTER",
        "rasterio_containing_cell_row": rasterio_row,
        "rasterio_containing_cell_col": rasterio_col,
        "geometry_generation_coordinate_x_m": cx,
        "geometry_generation_coordinate_y_m": cy,
        "pysheds_internal_cell_distance_to_frozen_outlet_m": internal_cell_distance,
        "frozen_polygon_center_cell_count": basin_count,
        "replayed_catchment_cell_count": replay_count,
        "replay_intersection_cell_count": intersection_count,
        "replay_union_cell_count": union_count,
        "replay_polygon_coverage_fraction": coverage,
        "replay_polygon_jaccard": jaccard,
        "routing_coverage_fraction": routing_coverage,
        "pysheds_catchment_api_invoked": False,
        "second_native_grid_invoked": False,
        "second_dem_conditioning_invoked": False,
        "second_flowdir_computation_invoked": False,
        "manual_reverse_d8_used": True,
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
        "drainage_density_rule_changed": False,
    }
    TOPOLOGY_REPLAY_AUDIT[target_id] = dict(audit)
    return {
        "routing_coverage_fraction": routing_coverage,
        "routing_reached_cell_count": reached_count,
        "basin_center_cell_count": basin_count,
        "main_channel_length_m": main_length,
        **drainage,
        **audit,
    }


def configure_runtime() -> None:
    base.EXECUTION = EXECUTION_V9
    base.build_exact_geometry_dem = v6.build_exact_dem_capture
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = d8_metrics_topology_equivalent


def worker_main(args: argparse.Namespace) -> int:
    registry, _method, _execution = validate_frozen_gate()
    configure_runtime()
    args.worker_report.parent.mkdir(parents=True, exist_ok=True)
    args.cache_root.mkdir(parents=True, exist_ok=True)
    args.worker_work.mkdir(parents=True, exist_ok=True)
    expected = base.expected_tile_hashes(registry)
    geom_path = base.find_geometry(args.geometry_root, args.worker_target)
    target = base.target_metrics(
        args.worker_target, geom_path, registry, expected, args.cache_root, args.worker_work
    )
    if set(v4.EXACT_DEM_AUDIT) != {args.worker_target}:
        raise RuntimeError(f"FAIL_CLOSED_WORKER_EXACT_DEM_AUDIT {args.worker_target}")
    if set(TOPOLOGY_REPLAY_AUDIT) != {args.worker_target}:
        raise RuntimeError(f"FAIL_CLOSED_WORKER_TOPOLOGY_AUDIT {args.worker_target}")
    if args.worker_target == "cashahuacra" and set(v3.POURPOINT_AUDIT) != {args.worker_target}:
        raise RuntimeError("FAIL_CLOSED_CASHAHUACRA_POURPOINT_AUDIT")
    doc = {
        "schema_version": "0.9-worker",
        "target_id": args.worker_target,
        "guards": GUARDS,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "target": target,
        "exact_geometry_dem_audit": v4.EXACT_DEM_AUDIT[args.worker_target],
        "geometry_generation_routing_replay_audit": TOPOLOGY_REPLAY_AUDIT[args.worker_target],
        "pourpoint_semantics_audit": v3.POURPOINT_AUDIT.get(args.worker_target),
    }
    args.worker_report.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def coordinator_main(args: argparse.Namespace) -> int:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    registry, _method, execution = validate_frozen_gate()
    result = {
        "schema_version": "0.9",
        "batch_id": registry["batch_id"],
        "status": "PENDING",
        "phase": "PHASE_1_PREUNBLIND_DEM_MORPHOMETRY",
        "execution_revision": "0.9_TOPOLOGY_EQUIVALENT_REPLAY_NO_SECOND_NATIVE_GRID",
        "guards": GUARDS,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "registry_sha256": sha256_path(base.REGISTRY),
        "morphometry_contract_sha256": sha256_path(base.METHOD),
        "execution_contract_sha256": sha256_path(EXECUTION_V9),
        "implementation_sha256": sha256_path(Path(__file__).resolve()),
        "target_count": 0,
        "targets": [],
        "worker_execution_audit": {},
        "exact_geometry_dem_audit": {},
        "geometry_generation_routing_replay_audit": {},
        "pourpoint_semantics_audit": {},
        "revision_guards": {
            "a6680_numeric_reference_read": False,
            "outcome_evidence_read": False,
            "post_anchor_predictor_read": False,
            "selection_or_tuning_from_metric_values": False,
            "frozen_polygon_mask_modified": False,
            "frozen_outlet_modified": False,
            "scientific_semantics_changed_from_v0_8": False,
            "second_native_grid_replay_removed": True,
            "one_target_per_fresh_python_process": True,
        },
    }
    try:
        with tempfile.TemporaryDirectory(prefix="irfen_chosica_2015_morphometry_v9_") as raw:
            root = Path(raw)
            cache = root / "tile_cache"; cache.mkdir()
            reports = root / "worker_reports"; reports.mkdir()
            work = root / "worker_work"; work.mkdir()
            completed: list[str] = []
            for key in TARGET_KEYS:
                worker_report = reports / f"{key}.json"
                cmd = [
                    sys.executable, str(Path(__file__).resolve()),
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
                    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
                result["geometry_generation_routing_replay_audit"][key] = doc["geometry_generation_routing_replay_audit"]
                if doc["pourpoint_semantics_audit"] is not None:
                    result["pourpoint_semantics_audit"][key] = doc["pourpoint_semantics_audit"]
        result["target_count"] = len(result["targets"])
        if result["target_count"] != execution["phase_1_output"]["required_target_count"]:
            raise RuntimeError("FAIL_CLOSED_TARGET_COUNT")
        result["status"] = "PASS_CHOSICA_2015_PHASE1_MORPHOMETRY"
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], "target_count": result["target_count"]}, sort_keys=True))
        return 0
    except Exception as exc:
        result["status"] = "FAIL_CLOSED_PHASE1_MORPHOMETRY"
        result["error"] = str(exc)
        result["targets"] = []
        result["target_count"] = 0
        result["exact_geometry_dem_audit"] = {}
        result["geometry_generation_routing_replay_audit"] = {}
        result["pourpoint_semantics_audit"] = {}
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
