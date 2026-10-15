#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.8.

Revision 0.8 changes execution isolation only. Each frozen target is computed in a fresh
Python process using the unchanged revision-0.7 target functions. This prevents native
library state from leaking across targets while preserving the frozen geometry, exact DEM
reconstruction, routing replay and metric semantics. No A6680 numeric reference, sealed
outcome, rainfall or post-anchor predictor is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import compute_chosica_2015_morphometry_phase1_v7 as v7

v6 = v7.v6
v4 = v7.v4
v3 = v7.v3
v2 = v7.v2
base = v7.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V8 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_8.json"
TARGET_KEYS = tuple(base.TARGET_KEYS)
GUARDS = {
    "RESEARCH_ONLY": True,
    "TEST_ONLY": True,
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
}


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
    execution = load_json(EXECUTION_V8)
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


def configure_v7_target_runtime() -> None:
    # Scientific functions are deliberately unchanged from revision 0.7.
    base.EXECUTION = EXECUTION_V8
    base.build_exact_geometry_dem = v6.build_exact_dem_capture
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = v7.d8_metrics_provenance_dispatch


def worker_main(args: argparse.Namespace) -> int:
    if args.worker_target not in TARGET_KEYS:
        raise RuntimeError(f"FAIL_CLOSED_UNKNOWN_WORKER_TARGET {args.worker_target}")
    registry, _method, _execution = validate_frozen_gate()
    configure_v7_target_runtime()

    args.worker_report.parent.mkdir(parents=True, exist_ok=True)
    args.cache_root.mkdir(parents=True, exist_ok=True)
    args.worker_work.mkdir(parents=True, exist_ok=True)
    expected = base.expected_tile_hashes(registry)
    geom_path = base.find_geometry(args.geometry_root, args.worker_target)

    target = base.target_metrics(
        args.worker_target,
        geom_path,
        registry,
        expected,
        args.cache_root,
        args.worker_work,
    )
    if set(v4.EXACT_DEM_AUDIT) != {args.worker_target}:
        raise RuntimeError(f"FAIL_CLOSED_WORKER_EXACT_DEM_AUDIT {args.worker_target}")
    if set(v7.ROUTING_REPLAY_AUDIT) != {args.worker_target}:
        raise RuntimeError(f"FAIL_CLOSED_WORKER_ROUTING_AUDIT {args.worker_target}")
    if args.worker_target == "cashahuacra":
        if v6.REPLAY_AUDIT:
            raise RuntimeError("FAIL_CLOSED_CASHAHUACRA_PYSHEDS_REPLAY_PRESENT")
        if set(v3.POURPOINT_AUDIT) != {args.worker_target}:
            raise RuntimeError("FAIL_CLOSED_CASHAHUACRA_POURPOINT_AUDIT")
    else:
        if set(v6.REPLAY_AUDIT) != {args.worker_target}:
            raise RuntimeError(f"FAIL_CLOSED_WORKER_PYSHEDS_REPLAY_AUDIT {args.worker_target}")
        if v3.POURPOINT_AUDIT:
            raise RuntimeError(f"FAIL_CLOSED_NONCASHAHUACRA_POURPOINT_AUDIT {args.worker_target}")

    doc = {
        "schema_version": "0.8-worker",
        "target_id": args.worker_target,
        "guards": GUARDS,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "target": target,
        "exact_geometry_dem_audit": v4.EXACT_DEM_AUDIT[args.worker_target],
        "geometry_generation_routing_replay_audit": v7.ROUTING_REPLAY_AUDIT[args.worker_target],
        "pysheds_geometry_replay_audit": v6.REPLAY_AUDIT.get(args.worker_target),
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
        "schema_version": "0.8",
        "batch_id": registry["batch_id"],
        "status": "PENDING",
        "phase": "PHASE_1_PREUNBLIND_DEM_MORPHOMETRY",
        "execution_revision": "0.8_TARGET_PROCESS_ISOLATION_ONLY",
        "guards": GUARDS,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "registry_sha256": sha256_path(base.REGISTRY),
        "morphometry_contract_sha256": sha256_path(base.METHOD),
        "execution_contract_sha256": sha256_path(EXECUTION_V8),
        "implementation_sha256": sha256_path(Path(__file__).resolve()),
        "retained_revision_0_7_implementation_sha256": sha256_path(ROOT / "scripts/compute_chosica_2015_morphometry_phase1_v7.py"),
        "target_count": 0,
        "targets": [],
        "worker_execution_audit": {},
        "exact_geometry_dem_audit": {},
        "geometry_generation_routing_replay_audit": {},
        "pysheds_geometry_replay_audit": {},
        "pourpoint_semantics_audit": {},
        "revision_guards": {
            "a6680_numeric_reference_read": False,
            "outcome_evidence_read": False,
            "post_anchor_predictor_read": False,
            "selection_or_tuning_from_metric_values": False,
            "frozen_polygon_mask_modified": False,
            "frozen_outlet_modified": False,
            "scientific_semantics_changed_from_v0_7": False,
            "one_target_per_fresh_python_process": True,
        },
    }

    try:
        with tempfile.TemporaryDirectory(prefix="irfen_chosica_2015_morphometry_v8_") as raw:
            root = Path(raw)
            cache = root / "tile_cache"
            cache.mkdir()
            reports = root / "worker_reports"
            reports.mkdir()
            work = root / "worker_work"
            work.mkdir()
            completed: list[str] = []

            for key in TARGET_KEYS:
                worker_report = reports / f"{key}.json"
                worker_work = work / key
                cmd = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--geometry-root", str(args.geometry_root),
                    "--worker-target", key,
                    "--worker-report", str(worker_report),
                    "--cache-root", str(cache),
                    "--worker-work", str(worker_work),
                ]
                proc = subprocess.run(cmd, text=True, capture_output=True)
                result["worker_execution_audit"][key] = {
                    "return_code": int(proc.returncode),
                    "fresh_python_process": True,
                    "scientific_functions": "UNCHANGED_REVISION_0_7_TARGET_FUNCTIONS",
                    "worker_report_persisted": worker_report.exists(),
                }
                if proc.returncode != 0:
                    result["status"] = "FAIL_CLOSED_PHASE1_MORPHOMETRY"
                    result["error"] = f"FAIL_CLOSED_WORKER_PROCESS {key} return_code={proc.returncode}"
                    result["failed_worker_target"] = key
                    result["completed_worker_ids_before_failure"] = completed
                    # Native failure diagnostics are retained without parsing any partial metric report.
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

            # Only after all six workers succeed do we observe and aggregate metric values.
            worker_docs = {key: load_json(reports / f"{key}.json") for key in TARGET_KEYS}
            for key in TARGET_KEYS:
                doc = worker_docs[key]
                if doc["target_id"] != key or doc["guards"] != GUARDS:
                    raise RuntimeError(f"FAIL_CLOSED_WORKER_REPORT_IDENTITY {key}")
                if doc["a6680_numeric_reference_read"] is not False:
                    raise RuntimeError(f"FAIL_CLOSED_WORKER_A6680_GUARD {key}")
                if doc["outcome_evidence_read"] is not False or doc["post_anchor_predictor_read"] is not False:
                    raise RuntimeError(f"FAIL_CLOSED_WORKER_BLIND_GUARD {key}")
                result["targets"].append(doc["target"])
                result["exact_geometry_dem_audit"][key] = doc["exact_geometry_dem_audit"]
                result["geometry_generation_routing_replay_audit"][key] = doc["geometry_generation_routing_replay_audit"]
                if doc["pysheds_geometry_replay_audit"] is not None:
                    result["pysheds_geometry_replay_audit"][key] = doc["pysheds_geometry_replay_audit"]
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
        print(json.dumps({
            "status": result["status"],
            "target_count": result["target_count"],
            "execution_revision": result["execution_revision"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        result["status"] = "FAIL_CLOSED_PHASE1_MORPHOMETRY"
        result["error"] = str(exc)
        result["targets"] = []
        result["target_count"] = 0
        result["exact_geometry_dem_audit"] = {}
        result["geometry_generation_routing_replay_audit"] = {}
        result["pysheds_geometry_replay_audit"] = {}
        result["pourpoint_semantics_audit"] = {}
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": result["status"], "error": result["error"]}, sort_keys=True))
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
    if args.worker_target is not None:
        return worker_main(args)
    return coordinator_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
