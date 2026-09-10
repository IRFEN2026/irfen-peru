#!/usr/bin/env python3
"""Fail-closed validation for the blinded clean-room package and package-only matcher."""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
REVEALING=("cashahuacra","quirio","pedregal","san_antonio","san antonio","la_libertad","la libertad","carossio","carosio","rayos_de_sol","rayos de sol","corrales","a6680","ingemmet","official_outcome_evidence","outcome_label","damage","severity","post_event","web_search")
FORBIDDEN_IMPORTS={"requests","urllib","http","socket","subprocess","selenium","playwright"}

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def scan_text(p):
    low=p.read_text(encoding="utf-8").lower()
    bad=[x for x in REVEALING if x in low]
    if bad: raise RuntimeError(f"FAIL_CLOSED_REVEALING_TEXT {p.name} {bad}")
def matcher_imports(path):
    tree=ast.parse(path.read_text(encoding="utf-8")); roots=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Import): roots.update(a.name.split('.')[0] for a in n.names)
        elif isinstance(n,ast.ImportFrom) and n.module: roots.add(n.module.split('.')[0])
    return roots

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--contract",type=Path,required=True); ap.add_argument("--contamination",type=Path,required=True); ap.add_argument("--package",type=Path,required=True); ap.add_argument("--matching",type=Path,required=True); ap.add_argument("--matcher",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.1","status":"PENDING","guards":GUARDS,"sealed_target_unblind_allowed":False,"control_outcome_adjudication_performed":False,"checks":{}}
    try:
        co=load(a.contract); contam=load(a.contamination); pkg=load(a.package); match=load(a.matching)
        if co.get("guards")!=GUARDS or contam.get("guards")!=GUARDS or pkg.get("guards")!=GUARDS or match.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_STATUS")
        for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
            if contam["disposition"].get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_CONTAMINATION_DISPOSITION {k}")
        scan_text(a.package); scan_text(a.matching)
        imports=matcher_imports(a.matcher); bad=sorted(imports & FORBIDDEN_IMPORTS)
        if bad: raise RuntimeError(f"FAIL_CLOSED_MATCHER_NETWORK_OR_PROCESS_IMPORT {bad}")
        if pkg.get("status")!="PASS_CLEANROOM_INPUT_PACKAGE" or len(pkg.get("targets",[]))!=6 or len(pkg.get("candidates",[]))!=29: raise RuntimeError("FAIL_CLOSED_PACKAGE_DIMENSIONS")
        if pkg.get("package_contains_target_names") is not False or pkg.get("package_contains_outcome_labels") is not False or pkg.get("package_contains_post_anchor_predictors") is not False: raise RuntimeError("FAIL_CLOSED_PACKAGE_DISCLOSURE")
        if pkg.get("sealed_target_unblind_allowed") is not False or pkg.get("control_outcome_adjudication_performed") is not False: raise RuntimeError("FAIL_CLOSED_PACKAGE_UNBLIND")
        if match.get("status")!="PASS_CLEANROOM_MATCHING": raise RuntimeError("FAIL_CLOSED_MATCH_STATUS")
        if match.get("cleanroom_input_sha256")!=sha(a.package): raise RuntimeError("FAIL_CLOSED_MATCH_INPUT_HASH")
        if match.get("precipitation_used_for_matching") is not False or match.get("outcomes_used_for_matching") is not False or match.get("target_names_read") is not False or match.get("free_web_search_used") is not False: raise RuntimeError("FAIL_CLOSED_MATCH_FORBIDDEN_INPUT")
        if match.get("control_outcome_adjudication_performed") is not False or match.get("sealed_target_unblind_performed") is not False: raise RuntimeError("FAIL_CLOSED_MATCH_UNBLIND")
        if match.get("selected_without_frozen_preanchor_predictors")!=[]: raise RuntimeError("FAIL_CLOSED_SELECTED_PREDICTOR_GAP")
        if len(match.get("shortlists",{}))!=6 or any(len(x)!=3 for x in match["shortlists"].values()): raise RuntimeError("FAIL_CLOSED_SHORTLIST_DIMENSIONS")
        candidate_codes={x["candidate_code"] for x in pkg["candidates"]}; target_codes={x["target_code"] for x in pkg["targets"]}
        if set(match["shortlists"])!=target_codes: raise RuntimeError("FAIL_CLOSED_TARGET_CODE_ALIGNMENT")
        if not set(match["selected_candidate_codes"]).issubset(candidate_codes): raise RuntimeError("FAIL_CLOSED_CANDIDATE_CODE_ALIGNMENT")
        if not 1 <= match.get("selected_candidate_count",0) <= 18: raise RuntimeError("FAIL_CLOSED_SELECTED_COUNT")
        rep["checks"]={"contaminated_adjudication_excluded":True,"package_target_count":6,"package_candidate_count":29,"package_has_no_revealing_names":True,"matcher_forbidden_imports":bad,"matching_is_package_hash_bound":True,"shortlist_per_target":3,"selected_candidate_count":match["selected_candidate_count"],"all_selected_have_frozen_preanchor_predictors":True,"package_sha256":sha(a.package),"matching_sha256":sha(a.matching),"matcher_sha256":sha(a.matcher),"contract_sha256":sha(a.contract)}
        rep["status"]="PASS_CLEANROOM_RECOVERY_PRE_FREEZE"
        rep["next_gate"]="COMMIT_AND_FREEZE_CLEANROOM_PACKAGE_AND_MATCHING_BEFORE_TERRITORIAL_UNBLIND"
    except Exception as e:
        rep["status"]="FAIL_CLOSED_CLEANROOM_RECOVERY"; rep["error"]=str(e); rep["next_gate"]="STOP_NO_UNBLIND"
        a.output.write_text(json.dumps(rep,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); print(json.dumps(rep)); return 2
    a.output.write_text(json.dumps(rep,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); print(json.dumps(rep)); return 0

if __name__=="__main__": raise SystemExit(main())
