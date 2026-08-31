#!/usr/bin/env python3
"""Recover only transport-blocked HTTP 429 Landsat QA_PIXEL scenes for PRIMARY6.

This stage consumes one frozen baseline track report from workflow run
33337857203. Successful baseline measurements are reused byte-for-byte. Only
scenes whose baseline QA state is UNKNOWN because the exact-item Planetary
Computer fallback returned HTTP 429 are retried. No window, scene, compatible
pair, meteorological ranking, or case/control role may change.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from ibvf_primary6_landsat_qa_preflight import (
    analyze_qa_pixel,
    csha,
    guards,
    load,
    now,
    planetary_same_item_fallback,
    select_geometry,
    sha_file,
)

TRACKS = ("huaycoloro", "san_ildefonso", "shingolay")


def catalog_scene_map(catalog: dict[str, Any], unit: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    windows = [w for w in catalog.get("windows", []) if w.get("unit_id") == unit]
    if len(windows) != 36:
        raise SystemExit(f"FAIL_CLOSED_SELECTED_WINDOW_COUNT:{unit}:{len(windows)}")
    for w in windows:
        land = w.get("landsat") or {}
        for scene in (land.get("pre_candidates") or []) + (land.get("post_candidates") or []):
            iid = str(scene.get("id") or "")
            if iid:
                out.setdefault(iid, scene)
    return out


def is_baseline_429(scene: dict[str, Any]) -> bool:
    if not str(scene.get("qa_status", "")).startswith("UNKNOWN_"):
        return False
    acq = scene.get("acquisition") or {}
    fb = acq.get("fallback_attempt") or {}
    return fb.get("transport_status") == "TRANSPORT_BLOCKED" and "429" in str(fb.get("error", ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--unit-id", choices=TRACKS, required=True)
    ap.add_argument("--baseline-report", type=Path, required=True)
    ap.add_argument("--recovery-contract", default="site/data/validation/ibvf_primary6_landsat_qa_recovery_contract.json")
    ap.add_argument("--catalog", default="site/data/validation/ibvf_primary6_selected_a1_catalog.json")
    ap.add_argument("--qa-contract", default="site/data/validation/ibvf_primary6_landsat_qa_contract.json")
    ap.add_argument("--preflight", default="site/data/validation/ibvf_primary6_landsat_qa_preflight.json")
    ap.add_argument("--map", default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--download-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()

    root = a.repo_root.resolve(); unit = a.unit_id
    bp = (root / a.baseline_report).resolve() if not a.baseline_report.is_absolute() else a.baseline_report
    rp, cp = root / a.recovery_contract, root / a.catalog
    qp, pp, mp = root / a.qa_contract, root / a.preflight, root / a.map
    baseline, recovery, catalog, qa_contract, preflight, m = (load(x) for x in (bp, rp, cp, qp, pp, mp))
    for d in (baseline, recovery, catalog, qa_contract, preflight, m):
        guards(d)

    if recovery.get("cohort_id") != "PRIMARY6_CHRONOLOGICAL" or baseline.get("cohort_id") != "PRIMARY6_CHRONOLOGICAL":
        raise SystemExit("FAIL_CLOSED_COHORT")
    if baseline.get("unit_id") != unit or baseline.get("selected_window_count") != 36:
        raise SystemExit(f"FAIL_CLOSED_BASELINE_TRACK:{unit}")
    bmeta = (recovery.get("baseline_artifacts") or {}).get(unit) or {}
    if int(baseline.get("required_unique_scene_count", -1)) != int(bmeta.get("required_scenes", -2)):
        raise SystemExit(f"FAIL_CLOSED_BASELINE_SCENE_COUNT:{unit}")
    if int(baseline.get("qa_measured_scene_count", -1)) != int(bmeta.get("measured", -2)) or int(baseline.get("qa_unknown_scene_count", -1)) != int(bmeta.get("unknown", -2)):
        raise SystemExit(f"FAIL_CLOSED_BASELINE_COUNTS:{unit}")
    if baseline.get("source_a1_catalog_sha256") != sha_file(cp) or baseline.get("source_qa_contract_sha256") != sha_file(qp) or baseline.get("source_preflight_sha256") != sha_file(pp):
        raise SystemExit(f"FAIL_CLOSED_BASELINE_SOURCE_HASH:{unit}")
    if baseline.get("pair_choice_performed") is not False or baseline.get("selected_window_replaced") is not False:
        raise SystemExit(f"FAIL_CLOSED_BASELINE_PAIR_OR_WINDOW:{unit}")
    if baseline.get("case_control_assignment_performed") is not False or baseline.get("territorial_outcome_fields_read") is not False or baseline.get("known_event_dates_read") is not False:
        raise SystemExit(f"FAIL_CLOSED_BASELINE_LEAKAGE:{unit}")

    waits = [int(x) for x in recovery["retry_policy"]["deterministic_wait_seconds_before_attempts"]]
    if len(waits) != int(recovery["retry_policy"]["maximum_attempts_per_unknown_scene"]):
        raise SystemExit("FAIL_CLOSED_RETRY_POLICY")
    scene_map = catalog_scene_map(catalog, unit)
    cases = {str(c.get("unit_id")): c for c in m.get("cases", [])}
    if unit not in cases:
        raise SystemExit(f"FAIL_CLOSED_MAP_CASE_MISSING:{unit}")
    site_root = mp.parents[2]
    geom, geom_prov = select_geometry(site_root, cases[unit])
    dldir = root / a.download_dir; dldir.mkdir(parents=True, exist_ok=True)

    recovered = 0; retained_unknown = 0; baseline_success_reused = 0
    out_scenes: list[dict[str, Any]] = []
    for original in baseline.get("scenes", []):
        iid = str(original.get("item_id") or "")
        if not iid or iid not in scene_map:
            raise SystemExit(f"FAIL_CLOSED_SCENE_NOT_IN_FROZEN_CATALOG:{unit}:{iid}")
        if str(original.get("qa_status", "")).startswith("PASS_"):
            out_scenes.append(original)
            baseline_success_reused += 1
            continue
        if not is_baseline_429(original):
            out_scenes.append(original)
            retained_unknown += 1
            continue

        scene = scene_map[iid]
        dst = dldir / f"{iid}_qa_pixel.tif"
        attempts: list[dict[str, Any]] = []
        metrics = None; successful_acq = None
        for attempt_no, wait_s in enumerate(waits, start=1):
            if wait_s:
                time.sleep(wait_s)
            acq = planetary_same_item_fallback(scene, dst)
            attempts.append({"attempt": attempt_no, "wait_seconds_before_attempt": wait_s, "result": acq})
            if acq.get("transport_status") == "SUCCESS":
                try:
                    metrics = analyze_qa_pixel(dst, geom)
                    successful_acq = acq
                finally:
                    if dst.exists(): dst.unlink()
                break
            if "429" not in str(acq.get("error", "")):
                break
        if dst.exists():
            dst.unlink()
        if metrics is not None and successful_acq is not None:
            x = dict(original)
            x["qa_status"] = "PASS_QA_PIXEL_AOI_MEASURED_IDENTITY_PRESERVED"
            x["acquisition"] = {
                "transport_status": "SUCCESS",
                "route_used": "PLANETARY_COMPUTER_SIGNED_MIRROR_SAME_EARTH_SEARCH_ITEM_ID_ONLY",
                "primary_attempt": (original.get("acquisition") or {}).get("primary_attempt"),
                "fallback_attempt": successful_acq,
                "bytes": successful_acq.get("bytes"),
                "sha256": successful_acq.get("sha256"),
                "recovery_from_baseline_http_429": True,
                "recovery_attempts": attempts,
            }
            x["metrics"] = metrics
            out_scenes.append(x); recovered += 1
        else:
            x = dict(original)
            x["recovery"] = {"attempted": True, "attempts": attempts, "resolved": False}
            out_scenes.append(x); retained_unknown += 1
        time.sleep(int(recovery["retry_policy"]["inter_scene_pause_seconds"]))

    out_scenes.sort(key=lambda x: x["item_id"])
    pass_n = sum(str(x.get("qa_status", "")).startswith("PASS_") for x in out_scenes)
    unknown_n = len(out_scenes) - pass_n
    if len(out_scenes) != int(baseline["required_unique_scene_count"]):
        raise SystemExit(f"FAIL_CLOSED_OUTPUT_SCENE_COUNT:{unit}")
    if baseline_success_reused != int(baseline["qa_measured_scene_count"]):
        raise SystemExit(f"FAIL_CLOSED_BASELINE_SUCCESS_REUSE_COUNT:{unit}")

    result = dict(baseline)
    result.update({
        "schema_version": "irfen-ibvf-primary6-landsat-qa-track-v0.2-recovery",
        "generated_at": now(),
        "geometry": geom_prov,
        "qa_measured_scene_count": pass_n,
        "qa_unknown_scene_count": unknown_n,
        "bounded_parallelism_max_workers": 1,
        "scenes": out_scenes,
        "scenes_canonical_sha256": csha(out_scenes),
        "status": "PASS_TRACK_ALL_REQUIRED_QA_MEASURED_NO_PAIR_CHOICE" if unknown_n == 0 else "PARTIAL_TRACK_QA_UNKNOWN_PRESERVED_NO_PAIR_CHOICE",
        "next_gate": "GLOBAL_THREE_TRACK_QA_COMPLETENESS_GATE_THEN_FROZEN_PAIR_ORDERING",
        "recovery": {
            "source_contract": str(a.recovery_contract),
            "source_contract_sha256": sha_file(rp),
            "baseline_report_sha256": sha_file(bp),
            "baseline_workflow_run_id": recovery["baseline_workflow_run_id"],
            "baseline_unknown_count": int(baseline["qa_unknown_scene_count"]),
            "baseline_success_reused_without_remeasurement": baseline_success_reused,
            "http_429_scenes_recovered": recovered,
            "unknown_after_recovery": unknown_n,
            "scene_identity_changed": False,
            "selected_window_changed": False,
            "pair_choice_performed": False,
            "territorial_outcome_fields_read": False,
        },
    })
    guards(result)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"unit_id": unit, "baseline_unknown": baseline["qa_unknown_scene_count"], "recovered": recovered, "unknown_after": unknown_n, "status": result["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
