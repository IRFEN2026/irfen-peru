#!/usr/bin/env python3
"""Merge three blind PRIMARY6 Landsat QA track reports without choosing pairs."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from ibvf_primary6_landsat_qa_preflight import guards, load, now, sha_file, csha

TRACKS=("huaycoloro","san_ildefonso","shingolay")

def expected_from_catalog(catalog:dict[str,Any], unit:str)->tuple[int,set[str]]:
    ws=[w for w in catalog.get("windows",[]) if w.get("unit_id")==unit]
    req:set[str]=set()
    for w in ws:
        for p in (w.get("landsat") or {}).get("compatible_pair_identities") or []:
            req.add(str(p["pre_item_id"])); req.add(str(p["post_item_id"]))
    return len(ws),req

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--input-dir",type=Path,required=True)
    ap.add_argument("--catalog",default="site/data/validation/ibvf_primary6_selected_a1_catalog.json")
    ap.add_argument("--contract",default="site/data/validation/ibvf_primary6_landsat_qa_contract.json")
    ap.add_argument("--preflight",default="site/data/validation/ibvf_primary6_landsat_qa_preflight.json")
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); root=a.repo_root.resolve()
    cp,qp,pp=root/a.catalog,root/a.contract,root/a.preflight
    catalog,contract,preflight=load(cp),load(qp),load(pp)
    for d in (catalog,contract,preflight):guards(d)
    if preflight.get("status")!="PASS_QA_PIXEL_NATIVE_AOI_MECHANICS_PREFLIGHT_IDENTITY_PRESERVED_NO_PAIR_CHOICE":
        raise SystemExit("FAIL_CLOSED_PREFLIGHT_NOT_PASS")
    reports=[]; summaries=[]; total_scenes=total_measured=total_unknown=total_windows=0
    for u in TRACKS:
        p=root/a.input_dir/f"ibvf_primary6_landsat_qa_{u}.json"
        if not p.exists():raise SystemExit(f"FAIL_CLOSED_TRACK_REPORT_MISSING:{u}")
        d=load(p);guards(d)
        if d.get("unit_id")!=u or d.get("cohort_id")!="PRIMARY6_CHRONOLOGICAL":raise SystemExit(f"FAIL_CLOSED_TRACK_ID:{u}")
        if d.get("pair_choice_performed") is not False or d.get("case_control_assignment_performed") is not False:raise SystemExit(f"FAIL_CLOSED_PREMATURE_PAIR_OR_ROLE:{u}")
        if d.get("territorial_outcome_fields_read") is not False or d.get("known_event_dates_read") is not False:raise SystemExit(f"FAIL_CLOSED_LEAKAGE:{u}")
        if d.get("source_a1_catalog_sha256")!=sha_file(cp) or d.get("source_qa_contract_sha256")!=sha_file(qp) or d.get("source_preflight_sha256")!=sha_file(pp):raise SystemExit(f"FAIL_CLOSED_SOURCE_HASH:{u}")
        ew,req=expected_from_catalog(catalog,u)
        ids={str(x.get("item_id")) for x in d.get("scenes",[])}
        if int(d.get("selected_window_count",-1))!=ew or ew!=36:raise SystemExit(f"FAIL_CLOSED_WINDOW_COUNT:{u}")
        if ids!=req or int(d.get("required_unique_scene_count",-1))!=len(req):raise SystemExit(f"FAIL_CLOSED_SCENE_IDENTITY_SET:{u}")
        total_windows+=ew;total_scenes+=len(req);total_measured+=int(d["qa_measured_scene_count"]);total_unknown+=int(d["qa_unknown_scene_count"])
        summaries.append({"unit_id":u,"path":str(a.input_dir/f"ibvf_primary6_landsat_qa_{u}.json"),"file_sha256":sha_file(p),"selected_window_count":ew,"required_unique_scene_count":len(req),"qa_measured_scene_count":d["qa_measured_scene_count"],"qa_unknown_scene_count":d["qa_unknown_scene_count"],"status":d["status"],"scenes_canonical_sha256":d["scenes_canonical_sha256"]})
        reports.append(d)
    if total_windows!=108:raise SystemExit(f"FAIL_CLOSED_GLOBAL_WINDOW_COUNT:{total_windows}")
    # The count is derived only from the frozen A1 catalog; it is not an outcome-dependent target.
    all_complete=total_unknown==0 and total_measured==total_scenes and all(x["status"]=="PASS_TRACK_ALL_REQUIRED_QA_MEASURED_NO_PAIR_CHOICE" for x in summaries)
    outdoc={
      "schema_version":"irfen-ibvf-primary6-landsat-qa-global-v0.1","generated_at":now(),"framework":"IRFEN Independent Basin Validation Framework",
      "deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
      "cohort_id":"PRIMARY6_CHRONOLOGICAL","source_a1_catalog_sha256":sha_file(cp),"source_qa_contract_sha256":sha_file(qp),"source_preflight_sha256":sha_file(pp),
      "track_count":3,"selected_window_count":total_windows,"required_unique_unit_scene_count":total_scenes,"qa_measured_unit_scene_count":total_measured,"qa_unknown_unit_scene_count":total_unknown,
      "track_reports":summaries,"track_reports_canonical_sha256":csha(summaries),
      "global_qa_complete":all_complete,"pair_choice_allowed_by_qa_completeness":all_complete,"pair_choice_performed":False,
      "selected_window_replaced":False,"case_control_assignment_performed":False,"territorial_outcome_fields_read":False,"known_event_dates_read":False,"activation_inference_allowed":False,"modeling_allowed":False,"transport_failure_is_missing_science":False,
      "status":"PASS_ALL_PRIMARY6_REQUIRED_LANDSAT_QA_MEASURED_PAIR_CHOICE_NOT_YET_EXECUTED" if all_complete else "PARTIAL_PRIMARY6_LANDSAT_QA_UNKNOWN_PRESERVED_PAIR_CHOICE_BLOCKED",
      "next_gate":"PREREGISTER_EXACT_PAIR_CHOICE_EXECUTION_SEMANTICS_THEN_APPLY_FROZEN_ORDERING_NO_OUTCOME" if all_complete else "RESOLVE_UNKNOWN_QA_TRANSPORT_WITHOUT_REPLACING_SCENES_OR_WINDOWS"
    }
    guards(outdoc); a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(outdoc,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:outdoc[k] for k in ("status","selected_window_count","required_unique_unit_scene_count","qa_measured_unit_scene_count","qa_unknown_unit_scene_count","global_qa_complete")},indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
