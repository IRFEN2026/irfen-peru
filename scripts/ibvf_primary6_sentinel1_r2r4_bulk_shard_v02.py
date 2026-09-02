#!/usr/bin/env python3
"""Execute one frozen PRIMARY6 track x season Sentinel-1 R2-R4 shard.

RESEARCH_ONLY / TEST_ONLY. Pure orchestration over the preregistered execution
partition. The script does not read territorial activation evidence, known
outcomes, event labels, case/control assignments, or use R4 magnitudes to alter
execution. Missing Sentinel-1 slots remain explicit and are never replaced or
imputed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PASS_R2 = "PASS_R2_V02_PRE_POST_INDEPENDENT_SNAP14_CANONICAL_POEORB_VERIFIED_NO_COMPARISON"
PASS_R3 = "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY"
UNKNOWN_R3 = "UNKNOWN_INSUFFICIENT_COMMON_SUPPORT"
PASS_R4 = "PASS_R4_BLIND_SAR_FEATURE_VECTOR_FROZEN_NO_INFERENCE"
COMPATIBLE = "COMPATIBLE_PAIR_FROZEN_PENDING_R1_R4"
MISSING = "MISSING_COMPATIBLE_PAIR_RETAIN_WINDOW_NO_REPLACEMENT_NO_IMPUTATION"
FEATURES = {
    "MEDIAN_DELTA_DB",
    "IQR_DELTA_DB",
    "DECREASE_FACTOR2_FRACTION",
    "INCREASE_FACTOR2_FRACTION",
    "LARGEST_FACTOR2_CLUSTER_FRACTION",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def blind_guard(d: dict[str, Any], label: str) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY", label
    assert d["test_only"] is True, label
    assert d["production_use"] is False, label
    assert d["production_ready"] is False, label
    assert d["operational_alerting_enabled"] is False, label
    assert d["uses_operational_event_none_labels"] is False, label
    assert d["territorial_activation_evidence_blinded"] is True, label


def run(cmd: list[str], allowed: set[int] | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    rc = subprocess.run(cmd, check=False).returncode
    allowed = {0} if allowed is None else allowed
    if rc not in allowed:
        raise RuntimeError(f"command failed rc={rc}: {' '.join(cmd)}")
    return rc


def find_case(entry: dict[str, Any], unit_id: str, date_local: str) -> dict[str, Any]:
    rows = [
        x for x in entry.get("entries", [])
        if x.get("unit_id") == unit_id and x.get("date_local") == date_local
    ]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one R2 entry for {unit_id} {date_local}, got {len(rows)}")
    return rows[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", type=Path, required=True)
    ap.add_argument("--global-contract", type=Path, required=True)
    ap.add_argument("--pilot-r4", type=Path, required=True)
    ap.add_argument("--orbit-amendment", type=Path, required=True)
    ap.add_argument("--selector-validation", type=Path, required=True)
    ap.add_argument("--anchor-r3", type=Path, required=True)
    ap.add_argument("--anchor-r4", type=Path, required=True)
    ap.add_argument("--unit-id", required=True)
    ap.add_argument("--season-id", required=True)
    ap.add_argument("--r2-entry", type=Path, required=True)
    ap.add_argument("--prerequisites", type=Path, required=True)
    ap.add_argument("--dem-freeze", type=Path, required=True)
    ap.add_argument("--gpt", type=Path, required=True)
    ap.add_argument("--dem", type=Path, required=True)
    ap.add_argument("--dem-report", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    args = ap.parse_args()

    partition = load(args.partition)
    contract = load(args.global_contract)
    pilot_r4 = load(args.pilot_r4)
    orbit = load(args.orbit_amendment)
    selector = load(args.selector_validation)
    r2_entry = load(args.r2_entry)
    prereq = load(args.prerequisites)
    dem_freeze = load(args.dem_freeze)
    dem_report = load(args.dem_report)
    for label, d in [
        ("partition", partition), ("contract", contract), ("pilot_r4", pilot_r4),
        ("orbit", orbit), ("selector", selector), ("r2_entry", r2_entry),
        ("prerequisites", prereq), ("dem_freeze", dem_freeze), ("dem_report", dem_report),
    ]:
        blind_guard(d, label)

    assert partition["partition_rule"] == "EXACT_TRACK_X_PRIMARY6_SEASON"
    assert partition["partition_count"] == 18
    assert partition["selected_window_count"] == 108
    assert partition["compatible_pair_window_count"] == 104
    assert partition["missing_compatible_pair_count"] == 4
    assert partition["partition_assignment_uses_scientific_magnitude"] is False
    assert partition["partition_assignment_uses_sensor_response"] is False
    assert partition["partition_assignment_uses_known_event_dates"] is False
    assert partition["partition_assignment_uses_territorial_outcomes"] is False
    assert partition["partition_assignment_uses_case_control_role"] is False
    assert partition["selected_window_replacement_allowed"] is False
    assert partition["compatible_pair_reselection_allowed"] is False
    assert partition["missing_pair_imputation_allowed"] is False
    assert contract["primary6"]["selected_windows"] == 108
    assert contract["primary6"]["sentinel1_compatible_pairs"] == 104
    assert contract["primary6"]["sentinel1_missing_compatible_pair_slots"] == 4
    assert contract["bulk_gate"]["pilot_implementation_integrity_must_pass_before_bulk"] is True
    assert contract["bulk_gate"]["bulk_rules_locked_to_this_contract"] is True
    assert contract["pilot_selection"]["pilot_result_may_change_bulk_rules"] is False

    assert pilot_r4["case_id"] == contract["pilot_selection"]["selected_case_id"]
    assert pilot_r4["status"] == PASS_R4
    assert pilot_r4["r4_difference_computed"] is True
    assert pilot_r4["territorial_outcomes_read"] is False
    assert pilot_r4["known_event_dates_read"] is False
    assert pilot_r4["case_control_role_assigned"] is False
    assert pilot_r4["activation_inference_allowed"] is False
    assert pilot_r4["modeling_allowed"] is False
    assert set(pilot_r4["primary_r4_feature_vector"].keys()) == FEATURES

    shard_id = f"{args.unit_id}__{args.season_id.replace('-', '_')}"
    shards = [x for x in partition["shards"] if x["shard_id"] == shard_id]
    if len(shards) != 1:
        raise ValueError(f"expected one frozen shard {shard_id}, got {len(shards)}")
    shard = shards[0]
    assert shard["unit_id"] == args.unit_id and shard["season_id"] == args.season_id
    assert shard["selected_window_count"] == 6 == len(shard["windows"])
    assert shard["partition_uses_selected_rank_or_percentile"] is False
    assert shard["partition_uses_rainfall_magnitude"] is False
    assert shard["partition_uses_sar_response"] is False
    assert shard["partition_uses_outcome_or_event_date"] is False
    compatible = [w for w in shard["windows"] if w["sar_execution_status"] == COMPATIBLE]
    missing = [w for w in shard["windows"] if w["sar_execution_status"] == MISSING]
    assert len(compatible) == shard["compatible_pair_window_count"]
    assert len(missing) == shard["missing_compatible_pair_count"]
    assert len(compatible) + len(missing) == 6
    assert all(w["case_control_role"] == "UNASSIGNED" for w in shard["windows"])

    assert r2_entry["season_id"] == args.season_id
    assert r2_entry["territorial_outcomes_read"] is False
    assert prereq["season_id"] == args.season_id
    assert prereq["status"] == "PASS_ALL_SNAP14_CANONICAL_R2_PREREQUISITES_V02_FROZEN_NO_SCIENCE_VALUES"
    assert prereq["territorial_outcomes_read"] is False
    assert dem_freeze["unit_id"] == args.unit_id
    assert dem_freeze["status"] == "PASS_TRACK_DEM_FROZEN_NO_R2_SCIENCE_VALUES"
    assert dem_freeze["territorial_outcomes_read"] is False
    assert dem_report["unit_id"] == args.unit_id
    assert dem_report["status"] == "PASS_TRACK_DEM_REPRODUCED_EXACTLY_R2_EXECUTION_ALLOWED_FOR_UNIT"
    assert dem_report["territorial_outcomes_read"] is False

    geometry_path = Path(contract["unit_geometry_and_projection"][args.unit_id]["geometry_path"])
    if not geometry_path.exists():
        raise FileNotFoundError(geometry_path)
    if not args.gpt.exists() or not args.dem.exists():
        raise FileNotFoundError("frozen SNAP runtime or reproduced DEM missing")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    r2_pass = r3_pass = r3_unknown = r4_pass = 0

    for window in shard["windows"]:
        date_local = window["date_local"]
        if window["sar_execution_status"] == MISSING:
            row = {
                "unit_id": args.unit_id,
                "season_id": args.season_id,
                "date_local": date_local,
                "window_execution_identity_sha256": window["window_execution_identity_sha256"],
                "sar_execution_status": MISSING,
                "r1_r4_accounting_status": "EXPLICIT_STRUCTURAL_MISSING_NO_REPLACEMENT_NO_IMPUTATION",
                "case_control_role": "UNASSIGNED",
                "territorial_outcomes_read": False,
                "activation_inference_allowed": False,
            }
            dump(args.output_dir / f"missing_{date_local}.json", row)
            results.append(row)
            continue

        entry = find_case(r2_entry, args.unit_id, date_local)
        case_id = entry["case_id"]
        assert entry["case_control_role"] == "UNASSIGNED"
        assert entry["r2_entry_status"] == "PASS_R2_ENTRY_IDENTITY_FROZEN_EXECUTION_NOT_RUN"
        case_root = args.work_dir / case_id
        exec_dir = case_root / "execution-v02"
        r3_dir = case_root / "r3"
        r4_dir = case_root / "r4"
        for p in (exec_dir, r3_dir, r4_dir):
            p.mkdir(parents=True, exist_ok=True)

        r2_report = case_root / "r2-v02.json"
        adapter_report = case_root / "r2-r3-interface.json"
        r3_report = r3_dir / "r3-v02.json"
        r4_report = r4_dir / "r4-v02.json"

        run([
            sys.executable, "scripts/ibvf_primary6_sentinel1_r2_execute_v02.py",
            "--contract", str(args.global_contract),
            "--orbit-amendment", str(args.orbit_amendment),
            "--selector-validation", str(args.selector_validation),
            "--r2-entry", str(args.r2_entry),
            "--prerequisites", str(args.prerequisites),
            "--case-id", case_id,
            "--gpt", str(args.gpt),
            "--dem", str(args.dem),
            "--dem-report", str(args.dem_report),
            "--work-dir", str(exec_dir),
            "--output", str(r2_report),
        ])
        r2 = load(r2_report)
        assert r2["status"] == PASS_R2
        assert r2["r2_processing_executed"] is True and r2["poeorb_consumption_verified_both_dates"] is True
        assert r2["territorial_outcomes_read"] is False and r2["known_event_dates_read"] is False
        assert r2["case_control_role_assigned"] is False and r2["activation_inference_allowed"] is False
        r2_pass += 1

        run([
            sys.executable, "scripts/ibvf_primary6_sentinel1_r2v02_r3_adapter.py",
            "--r2-v02", str(r2_report), "--output", str(adapter_report),
        ])

        pre = exec_dir / f"{case_id}_pre_r2_gamma0_tc.tif"
        post = exec_dir / f"{case_id}_post_r2_gamma0_tc.tif"
        r3_rc = run([
            sys.executable, "scripts/ibvf_primary6_sentinel1_r3_tiled_storage_wrapper.py",
            "--global-contract", str(args.global_contract),
            "--anchor-r3-contract", str(args.anchor_r3),
            "--r2-report", str(adapter_report),
            "--case-id", case_id,
            "--pre", str(pre), "--post", str(post),
            "--basin", str(geometry_path),
            "--pre-crop-output", str(r3_dir / f"{case_id}_pre_r2_basin_crop.tif"),
            "--post-crop-output", str(r3_dir / f"{case_id}_post_r2_basin_crop.tif"),
            "--mask-output", str(r3_dir / f"{case_id}_r3_common_support_mask.tif"),
            "--report-output", str(r3_report),
        ], allowed={0, 2})
        r3 = load(r3_report)
        assert r3["territorial_outcomes_read"] is False and r3["case_control_role_assigned"] is False
        assert r3["activation_inference_allowed"] is False and r3["modeling_allowed"] is False

        out_case = args.output_dir / case_id
        out_case.mkdir(parents=True, exist_ok=True)
        shutil.copy2(r2_report, out_case / "r2-v02.json")
        shutil.copy2(adapter_report, out_case / "r2-r3-interface.json")
        shutil.copy2(r3_report, out_case / "r3-v02.json")

        if r3["status"] == PASS_R3:
            if r3_rc != 0:
                raise RuntimeError(f"R3 PASS returned unexpected rc={r3_rc} for {case_id}")
            assert float(r3["common_support_fraction"]) >= float(contract["r3_rule"]["minimum_common_support_fraction"])
            r3_pass += 1
            run([
                sys.executable, "scripts/ibvf_primary6_sentinel1_r4_blind_features.py",
                "--global-contract", str(args.global_contract),
                "--anchor-r4-contract", str(args.anchor_r4),
                "--r3-report", str(r3_report),
                "--case-id", case_id,
                "--pre", str(r3_dir / f"{case_id}_pre_r2_basin_crop.tif"),
                "--post", str(r3_dir / f"{case_id}_post_r2_basin_crop.tif"),
                "--common-mask", str(r3_dir / f"{case_id}_r3_common_support_mask.tif"),
                "--delta-output", str(r4_dir / f"{case_id}_delta_gamma0_db.tif"),
                "--factor2-mask-output", str(r4_dir / f"{case_id}_factor2_mask.tif"),
                "--report-output", str(r4_report),
            ])
            r4 = load(r4_report)
            assert r4["status"] == PASS_R4
            assert set(r4["primary_r4_feature_vector"].keys()) == FEATURES
            assert r4["territorial_outcomes_read"] is False and r4["known_event_dates_read"] is False
            assert r4["case_control_role_assigned"] is False and r4["activation_inference_allowed"] is False
            shutil.copy2(r4_report, out_case / "r4-v02.json")
            r4_pass += 1
            final_status = "PASS_R2_R3_R4_BLIND_ACCOUNTED"
            r4_sha = sha256(r4_report)
        elif r3["status"] == UNKNOWN_R3:
            if r3_rc != 2:
                raise RuntimeError(f"R3 UNKNOWN returned unexpected rc={r3_rc} for {case_id}")
            assert float(r3["common_support_fraction"]) < float(contract["r3_rule"]["minimum_common_support_fraction"])
            assert not r4_report.exists()
            r3_unknown += 1
            final_status = "PASS_R2_R3_ACCOUNTED_R4_EXPLICIT_UNKNOWN_BY_FROZEN_SUPPORT_GATE"
            r4_sha = None
        else:
            raise RuntimeError(f"non-accepted R3 blocker for {case_id}: {r3['status']}")

        row = {
            "case_id": case_id,
            "unit_id": args.unit_id,
            "season_id": args.season_id,
            "date_local": date_local,
            "window_execution_identity_sha256": window["window_execution_identity_sha256"],
            "sar_execution_status": COMPATIBLE,
            "r2_status": r2["status"],
            "r3_status": r3["status"],
            "r4_status": PASS_R4 if r4_sha else "NOT_COMPUTED_EXPLICIT_R3_UNKNOWN",
            "r2_report_sha256": sha256(r2_report),
            "r3_report_sha256": sha256(r3_report),
            "r4_report_sha256": r4_sha,
            "r1_r4_accounting_status": final_status,
            "r4_feature_magnitudes_used_for_execution_decisions": False,
            "territorial_outcomes_read": False,
            "known_event_dates_read": False,
            "case_control_role_assigned": False,
            "activation_inference_allowed": False,
            "modeling_allowed": False,
        }
        dump(out_case / "accounting.json", row)
        results.append(row)
        shutil.rmtree(case_root, ignore_errors=True)

    compatible_accounted = r4_pass + r3_unknown
    assert r2_pass == len(compatible)
    assert r3_pass + r3_unknown == len(compatible)
    assert compatible_accounted == len(compatible)
    assert len(results) == 6

    summary = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-r2r4-bulk-shard-v0.2",
        "shard_id": shard_id,
        "shard_identity_sha256": shard["shard_identity_sha256"],
        "unit_id": args.unit_id,
        "season_id": args.season_id,
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "selected_windows_accounted": 6,
        "compatible_windows_expected": len(compatible),
        "missing_windows_expected": len(missing),
        "r2_pass": r2_pass,
        "r3_pass": r3_pass,
        "r3_explicit_unknown": r3_unknown,
        "r4_pass": r4_pass,
        "compatible_windows_accounted": compatible_accounted,
        "missing_windows_preserved": len(missing),
        "selected_window_replacement_performed": False,
        "compatible_pair_reselection_performed": False,
        "missing_pair_imputation_performed": False,
        "r4_feature_magnitudes_used_for_execution_decisions": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_assignment_performed": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "status": "PASS_SHARD_ALL_SIX_WINDOWS_ACCOUNTED_BLIND_R2_R4",
        "results": results,
    }
    dump(args.summary, summary)
    print(json.dumps({
        "shard": shard_id,
        "status": summary["status"],
        "selected": 6,
        "compatible": len(compatible),
        "missing": len(missing),
        "r4_pass": r4_pass,
        "r3_explicit_unknown": r3_unknown,
        "territorial_outcomes_read": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
