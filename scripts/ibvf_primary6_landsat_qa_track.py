#!/usr/bin/env python3
"""Measure frozen Landsat QA_PIXEL candidates for one PRIMARY6 track.

This stage measures every unique Landsat scene required by at least one frozen
compatible-pair identity for the requested selected track. It deliberately does
NOT choose any pre/post pair. Pair ordering is deferred to the global merge only
after all required QA measurements across all three tracks are complete.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
from pathlib import Path
from typing import Any

from ibvf_primary6_landsat_qa_preflight import (
    acquire_qa_pixel,
    analyze_qa_pixel,
    guards,
    load,
    now,
    select_geometry,
    sha_file,
    csha,
)

TRACKS = ("huaycoloro", "san_ildefonso", "shingolay")


def required_scenes(catalog: dict[str, Any], unit: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    windows = [w for w in catalog.get("windows", []) if w.get("unit_id") == unit]
    if len(windows) != 36:
        raise SystemExit(f"FAIL_CLOSED_SELECTED_WINDOW_COUNT:{unit}:{len(windows)}")
    scenes: dict[str, dict[str, Any]] = {}
    identities = []
    for w in windows:
        land = w.get("landsat") or {}
        if land.get("status") != "COMPATIBLE_CANDIDATES_FROZEN_PAIR_CHOICE_PENDING_AOI_QA":
            raise SystemExit(f"FAIL_CLOSED_LANDSAT_WINDOW_NOT_QA_ELIGIBLE:{unit}:{w.get('date_local')}:{land.get('status')}")
        cand = {str(x.get("id")): x for x in (land.get("pre_candidates") or []) + (land.get("post_candidates") or []) if x.get("id")}
        pairs = land.get("compatible_pair_identities") or []
        if not pairs:
            raise SystemExit(f"FAIL_CLOSED_NO_COMPATIBLE_PAIR_IDENTITIES:{unit}:{w.get('date_local')}")
        req: set[str] = set()
        for p in pairs:
            req.add(str(p["pre_item_id"])); req.add(str(p["post_item_id"]))
        for iid in req:
            if iid not in cand:
                raise SystemExit(f"FAIL_CLOSED_REQUIRED_SCENE_NOT_FROZEN:{unit}:{iid}")
            scenes.setdefault(iid, cand[iid])
        identities.append({
            "unit_id": unit, "season_id": w["season_id"], "date_local": w["date_local"],
            "selected_target_order": w["selected_target_order"],
            "required_scene_ids": sorted(req),
            "compatible_pair_identities": pairs,
        })
    return [scenes[k] for k in sorted(scenes)], identities


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--unit-id", choices=TRACKS, required=True)
    ap.add_argument("--catalog", default="site/data/validation/ibvf_primary6_selected_a1_catalog.json")
    ap.add_argument("--contract", default="site/data/validation/ibvf_primary6_landsat_qa_contract.json")
    ap.add_argument("--preflight", default="site/data/validation/ibvf_primary6_landsat_qa_preflight.json")
    ap.add_argument("--map", default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--download-dir", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(); root = args.repo_root.resolve(); unit = args.unit_id
    if not 1 <= args.workers <= 8: raise SystemExit("FAIL_CLOSED_WORKERS_OUT_OF_RANGE")
    catalog_path, contract_path = root/args.catalog, root/args.contract
    preflight_path, map_path = root/args.preflight, root/args.map
    catalog, contract, preflight, m = load(catalog_path), load(contract_path), load(preflight_path), load(map_path)
    for d in (catalog, contract, preflight, m): guards(d)
    if preflight.get("status") != "PASS_QA_PIXEL_NATIVE_AOI_MECHANICS_PREFLIGHT_IDENTITY_PRESERVED_NO_PAIR_CHOICE":
        raise SystemExit(f"FAIL_CLOSED_QA_PREFLIGHT_NOT_PASS:{preflight.get('status')}")
    if catalog.get("status") != contract["catalog_gate"]["required_selected_a1_status"]:
        raise SystemExit("FAIL_CLOSED_A1_CATALOG_NOT_COMPLETE")
    assert contract["pair_choice_after_qa"]["pair_choice_before_all_required_candidate_qa_complete"] is False
    cases = {str(c.get("unit_id")): c for c in m.get("cases", [])}
    if unit not in cases: raise SystemExit(f"FAIL_CLOSED_MAP_CASE_MISSING:{unit}")
    site_root = map_path.parents[2]
    geom, geom_prov = select_geometry(site_root, cases[unit])
    scenes, windows = required_scenes(catalog, unit)
    dldir = (root/args.download_dir); dldir.mkdir(parents=True, exist_ok=True)

    def measure(scene: dict[str, Any]) -> dict[str, Any]:
        iid = str(scene["id"]); href = scene.get("qa_pixel_href")
        base = {"unit_id": unit, "item_id": iid, "datetime": scene.get("datetime"), "platform": scene.get("platform"), "wrs_path": scene.get("wrs_path"), "wrs_row": scene.get("wrs_row")}
        if not href:
            return {**base, "qa_status": "UNKNOWN_QA_PIXEL_REFERENCE_MISSING_NOT_SCIENTIFIC_MISSING", "acquisition": None, "metrics": None}
        dst = dldir/f"{iid}_qa_pixel.tif"
        acq = acquire_qa_pixel(scene, str(href), dst, contract)
        try:
            metrics = analyze_qa_pixel(dst, geom) if acq["transport_status"] == "SUCCESS" else None
        finally:
            if dst.exists(): dst.unlink()
        return {**base, "qa_status": "PASS_QA_PIXEL_AOI_MEASURED_IDENTITY_PRESERVED" if metrics is not None else "UNKNOWN_QA_PIXEL_TRANSPORT_BLOCKED_NOT_MISSING", "acquisition": acq, "metrics": metrics}

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        measured = list(ex.map(measure, scenes))
    measured.sort(key=lambda x: x["item_id"])
    pass_n = sum(x["qa_status"].startswith("PASS_") for x in measured)
    unknown_n = len(measured)-pass_n
    result = {
      "schema_version":"irfen-ibvf-primary6-landsat-qa-track-v0.1",
      "generated_at":now(), "framework":"IRFEN Independent Basin Validation Framework",
      "deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,
      "operational_alerting_enabled":False,"uses_operational_event_none_labels":False,
      "territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
      "cohort_id":"PRIMARY6_CHRONOLOGICAL", "unit_id":unit,
      "source_a1_catalog_sha256":sha_file(catalog_path), "source_qa_contract_sha256":sha_file(contract_path), "source_preflight_sha256":sha_file(preflight_path),
      "geometry":geom_prov, "selected_window_count":len(windows), "required_unique_scene_count":len(scenes),
      "required_scene_identity_sha256":csha([(unit,str(x['id'])) for x in scenes]),
      "qa_measured_scene_count":pass_n, "qa_unknown_scene_count":unknown_n,
      "bounded_parallelism_max_workers":args.workers,
      "pair_choice_performed":False,"selected_window_replaced":False,"case_control_assignment_performed":False,
      "territorial_outcome_fields_read":False,"known_event_dates_read":False,"activation_inference_allowed":False,"modeling_allowed":False,
      "transport_failure_is_missing_science":False,
      "windows":windows,"scenes":measured,"scenes_canonical_sha256":csha(measured),
      "status":"PASS_TRACK_ALL_REQUIRED_QA_MEASURED_NO_PAIR_CHOICE" if unknown_n==0 else "PARTIAL_TRACK_QA_UNKNOWN_PRESERVED_NO_PAIR_CHOICE",
      "next_gate":"GLOBAL_THREE_TRACK_QA_COMPLETENESS_GATE_THEN_FROZEN_PAIR_ORDERING"
    }
    guards(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"unit_id":unit,"required_scenes":len(scenes),"measured":pass_n,"unknown":unknown_n,"status":result['status']},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
