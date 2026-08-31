#!/usr/bin/env python3
"""Execute frozen PRIMARY6 Landsat A4 optical CVA for one blind track.

Uses only already-selected 108 Landsat pairs and the preregistered optical A4
contract. No scene/window replacement, territorial evidence, or case/control
role is read. Every selected window is retained; acquisition/grid failures are
explicit UNKNOWN/MISSING and never imputed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ibvf_primary6_landsat_a4_optical_preflight as pf

ALLOWED_UNITS = {"huaycoloro", "san_ildefonso", "shingolay"}
BACKOFF = (0, 3, 8, 20, 45)


def load(p: Path) -> dict[str, Any]: return json.loads(p.read_text(encoding="utf-8"))
def bsha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def csha(x: Any) -> str: return bsha(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
def sha_file(p: Path) -> str: return pf.sha_file(p)


def fetch_json_retry(url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    last: Exception | None = None
    for delay in BACKOFF:
        if delay: time.sleep(delay)
        try:
            req = Request(url, headers={"User-Agent": pf.UA + "/BULK"})
            with urlopen(req, timeout=120) as r:
                raw = r.read(); status = getattr(r, "status", 200)
            if status != 200: raise RuntimeError(f"HTTP_{status}")
            return json.loads(raw.decode("utf-8")), {
                "url_without_query": url.split("?", 1)[0], "http_status": status,
                "raw_bytes": len(raw), "raw_sha256": bsha(raw), "attempts": BACKOFF.index(delay)+1,
            }
        except HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504): break
        except Exception as exc:
            last = exc
            break
    raise RuntimeError(f"RETRY_EXHAUSTED:{type(last).__name__}:{last!r}")


# All helper functions in the preregistered preflight resolve this module global.
pf.fetch_json = fetch_json_retry


def window_feature(w: dict[str, Any], geom: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    pair = w["selected_pair"]
    out: dict[str, Any] = {
        "unit_id": w["unit_id"], "season_id": w["season_id"], "date_local": w["date_local"],
        "selected_target_order": w["selected_target_order"], "case_control_role": "UNASSIGNED",
        "selected_pair_identity_sha256": w["selected_pair_identity_sha256"],
        "pre_item_id": pair["pre_item_id"], "post_item_id": pair["post_item_id"],
        "platform": pair["platform"], "wrs_path": pair["wrs_path"], "wrs_row": pair["wrs_row"],
        "selected_window_replaced": False, "pair_reselected": False,
    }
    scene_results: dict[str, Any] = {}
    try:
        for side in ("pre", "post"):
            iid = str(pair[f"{side}_item_id"]); expected = pf.expected_identity(iid, pair, side)
            es_url = f"{pf.EARTH_SEARCH}/collections/landsat-c2-l2/items/{pf.quote(iid, safe='')}"
            es_item, es_prov = fetch_json_retry(es_url)
            pf.assert_identity(pf.item_identity(es_item), expected, "EARTH_SEARCH")
            urls, mirror_prov = pf.signed_same_item_assets(es_item, expected)
            scene = pf.process_scene(urls, geom, contract)
            scene_results[side] = {"es": es_prov, "mirror": mirror_prov, "processed": scene}
        pre, post = scene_results["pre"]["processed"], scene_results["post"]["processed"]
        out["pre_grid_identity_sha256"] = pre["grid_identity_sha256"]
        out["post_grid_identity_sha256"] = post["grid_identity_sha256"]
        out["pre_native_array_sha256"] = pf.public_scene(pre)["native_array_sha256"]
        out["post_native_array_sha256"] = pf.public_scene(post)["native_array_sha256"]
        out["pre_source_identity_sha256"] = csha({"es": scene_results["pre"]["es"], "mirror": scene_results["pre"]["mirror"]})
        out["post_source_identity_sha256"] = csha({"es": scene_results["post"]["es"], "mirror": scene_results["post"]["mirror"]})
        if pf.grid_id(pre["rasters"]["QA_PIXEL"]) != pf.grid_id(post["rasters"]["QA_PIXEL"]):
            out.update({"status": "UNKNOWN_GRID_MISMATCH_NO_RESAMPLING", "A4_OPTICAL_CHANGE_PRIMARY": None, "common_valid_pixel_count": 0, "common_valid_fraction_of_aoi": None, "common_valid_mask_sha256": None})
            return out
        common = pre["valid"] & post["valid"]
        n = int(common.sum())
        inside_n = int((~pre["rasters"]["QA_PIXEL"]["outside"] & ~post["rasters"]["QA_PIXEL"]["outside"]).sum())
        out["common_valid_pixel_count"] = n
        out["common_valid_fraction_of_aoi"] = (n / inside_n) if inside_n else None
        out["common_valid_mask_sha256"] = bsha(np.ascontiguousarray(common.astype(np.uint8)).tobytes())
        if n == 0:
            out.update({"status": "MISSING_VALID_OPTICAL_SUPPORT_NO_IMPUTATION", "A4_OPTICAL_CHANGE_PRIMARY": None})
            return out
        scale = float(contract["surface_reflectance"]["scale_factor"]); offset = float(contract["surface_reflectance"]["additive_offset"])
        sq = np.zeros(pre["valid"].shape, dtype=np.float64)
        for sem in pf.SEMANTICS:
            a = pre["rasters"][sem]["data"].astype(np.float64) * scale + offset
            b = post["rasters"][sem]["data"].astype(np.float64) * scale + offset
            sq += (b-a)**2
        value = float(np.median(np.sqrt(sq)[common]))
        if not math.isfinite(value): raise RuntimeError("NONFINITE_PRIMARY_FEATURE")
        out.update({"status": "PASS_BLIND_OPTICAL_CVA_PRIMARY_VALUE_FROZEN_NO_OUTCOME", "A4_OPTICAL_CHANGE_PRIMARY": value})
        return out
    except Exception as exc:
        out.update({
            "status": "UNKNOWN_TRANSPORT_OR_SCHEMA_NO_REPLACEMENT", "A4_OPTICAL_CHANGE_PRIMARY": None,
            "common_valid_pixel_count": None, "common_valid_fraction_of_aoi": None, "common_valid_mask_sha256": None,
            "error_class": type(exc).__name__, "error": repr(exc),
        })
        return out


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",type=Path,default=Path(".")); ap.add_argument("--unit",required=True)
    ap.add_argument("--pairs",default="site/data/validation/ibvf_primary6_landsat_pair_selection.json")
    ap.add_argument("--contract",default="site/data/validation/ibvf_primary6_landsat_a4_optical_contract.json")
    ap.add_argument("--a5-amendment",default="site/data/validation/ibvf_a5_optical_slot_amendment_v02.json")
    ap.add_argument("--preflight",default="site/data/validation/ibvf_primary6_landsat_a4_optical_preflight.json")
    ap.add_argument("--map",default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--output",type=Path,required=True); args=ap.parse_args(); root=args.repo_root.resolve()
    if args.unit not in ALLOWED_UNITS: raise SystemExit(f"FAIL_CLOSED_UNIT:{args.unit}")
    pp,cp,apath,pfp,mp=[root/x for x in (args.pairs,args.contract,args.a5_amendment,args.preflight,args.map)]
    pairs,contract,amend,preflight,m=map(load,(pp,cp,apath,pfp,mp))
    for d in (pairs,contract,amend,preflight,m): pf.guards(d)
    assert preflight["primary_feature"]["status"]=="PASS_BLIND_OPTICAL_CVA_PREFLIGHT_PRIMARY_VALUE_COMPUTED_NO_OUTCOME"
    assert preflight["bulk_execution_allowed"] is True
    assert contract["primary_feature"]["feature_id"]=="A4_OPTICAL_CVA_MEDIAN_MAGNITUDE_SR"
    assert amend["slot_resolution"]["slot_id"]=="A4_OPTICAL_CHANGE_PRIMARY"
    wins=sorted([w for w in pairs["windows"] if w["unit_id"]==args.unit],key=lambda w:(w["season_id"],w["date_local"]))
    if len(wins)!=36: raise SystemExit(f"FAIL_CLOSED_SELECTED_WINDOW_COUNT:{args.unit}:{len(wins)}")
    cases={str(c.get('unit_id')):c for c in m.get('cases',[])}
    if args.unit not in cases: raise SystemExit(f"FAIL_CLOSED_MAP_CASE:{args.unit}")
    geom,geom_prov=pf.select_geometry(mp.parents[2],cases[args.unit])
    rows=[]
    for i,w in enumerate(wins,1):
        r=window_feature(w,geom,contract); rows.append(r)
        print(json.dumps({"progress":f"{i}/36","unit":args.unit,"date":w['date_local'],"status":r['status']},ensure_ascii=False),flush=True)
    # Deterministic preflight cross-check where applicable.
    preflight_crosscheck=None
    if args.unit==preflight["preflight_window"]["unit_id"]:
        key=(preflight["preflight_window"]["season_id"],preflight["preflight_window"]["date_local"])
        match=[r for r in rows if (r["season_id"],r["date_local"])==key]
        if len(match)!=1: raise SystemExit("FAIL_CLOSED_PREFLIGHT_CROSSCHECK_ROW")
        r=match[0]; pv=preflight["primary_feature"]["value"]
        ok=(r["status"].startswith("PASS_") and r["A4_OPTICAL_CHANGE_PRIMARY"]==pv and r["common_valid_mask_sha256"]==preflight["common_valid_mask_sha256"])
        if not ok: raise SystemExit("FAIL_CLOSED_PREFLIGHT_CROSSCHECK_MISMATCH")
        preflight_crosscheck={"status":"PASS_EXACT_PRIMARY_VALUE_AND_COMMON_MASK_REPRODUCED","value":pv,"common_valid_mask_sha256":r["common_valid_mask_sha256"]}
    counts={}
    for r in rows: counts[r["status"]]=counts.get(r["status"],0)+1
    report={
      "schema_version":"irfen-ibvf-primary6-landsat-a4-optical-track-v0.1","generated_at":pf.now(),"framework":"IRFEN Independent Basin Validation Framework",
      "deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,
      "uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED","cohort_id":"PRIMARY6_CHRONOLOGICAL",
      "unit_id":args.unit,"source_pair_selection_sha256":sha_file(pp),"source_optical_contract_sha256":sha_file(cp),"source_a5_amendment_sha256":sha_file(apath),"source_preflight_sha256":sha_file(pfp),
      "geometry":geom_prov,"selected_window_count":36,"retained_window_count":len(rows),"status_counts":counts,
      "numeric_primary_feature_count":sum(r["A4_OPTICAL_CHANGE_PRIMARY"] is not None for r in rows),
      "unknown_or_missing_count":sum(r["A4_OPTICAL_CHANGE_PRIMARY"] is None for r in rows),
      "selected_windows_replaced":False,"pairs_reselected":False,"resampling_performed":False,"reprojection_performed":False,"interpolation_performed":False,
      "territorial_outcome_fields_read":False,"known_event_dates_read":False,"case_control_assignment_performed":False,"activation_inference_allowed":False,"modeling_allowed":False,
      "preflight_crosscheck":preflight_crosscheck,"rows":rows,"rows_canonical_sha256":csha(rows),
      "status":"PASS_TRACK_EXECUTION_COMPLETE_ALL_SELECTED_WINDOWS_RETAINED_NO_OUTCOME" if len(rows)==36 else "FAIL_TRACK_ROW_COUNT"
    }
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"unit":args.unit,"status_counts":counts,"rows_sha256":report["rows_canonical_sha256"]},indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
