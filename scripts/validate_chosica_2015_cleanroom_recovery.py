#!/usr/bin/env python3
"""Validate clean-room isolation, deterministic matching and fail-closed guards."""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
FORBIDDEN=("cashahuacra","quirio","pedregal","san_antonio","san antonio","la_libertad","la libertad","carossio","carosio","rayos_de_sol","rayos de sol","corrales","a6680","ingemmet","official_outcome_evidence","outcome_label","damage","severity","post_event","web_search")
FORBIDDEN_IMPORTS={"requests","urllib","http","socket","subprocess","selenium","playwright"}

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def scan(p):
    low=p.read_text(encoding="utf-8").lower(); bad=[x for x in FORBIDDEN if x in low]
    if bad: raise RuntimeError(f"FAIL_CLOSED_REVEALING_TEXT_{p.name}_{bad}")
def imports(path):
    tree=ast.parse(path.read_text(encoding="utf-8")); out=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Import): out.update(a.name.split('.')[0] for a in n.names)
        elif isinstance(n,ast.ImportFrom) and n.module: out.add(n.module.split('.')[0])
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--contract",type=Path,required=True); ap.add_argument("--contamination",type=Path,required=True); ap.add_argument("--package",type=Path,required=True); ap.add_argument("--matching",type=Path,required=True); ap.add_argument("--matcher",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.1","status":"PENDING","guards":GUARDS,"sealed_target_unblind_allowed":False,"control_outcome_adjudication_performed":False}
    try:
        co=load(a.contract); contam=load(a.contamination); pkg=load(a.package); match=load(a.matching)
        if any(d.get("guards")!=GUARDS for d in (co,contam,pkg,match)): raise RuntimeError("FAIL_CLOSED_GUARDS")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_TOMBSTONE")
        for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
            if contam["disposition"].get(k) is not False: raise RuntimeError("FAIL_CLOSED_CONTAMINATION_DISPOSITION")
        scan(a.package); scan(a.matching)
        bad_imports=sorted(imports(a.matcher)&FORBIDDEN_IMPORTS)
        if bad_imports: raise RuntimeError(f"FAIL_CLOSED_FORBIDDEN_MATCHER_IMPORTS_{bad_imports}")
        if pkg.get("status")!="PASS_CLEANROOM_INPUT_PACKAGE" or len(pkg.get("targets",[]))!=6 or len(pkg.get("candidates",[]))!=29: raise RuntimeError("FAIL_CLOSED_PACKAGE")
        if pkg.get("sealed_target_unblind_allowed") is not False or pkg.get("control_outcome_adjudication_performed") is not False: raise RuntimeError("FAIL_CLOSED_PACKAGE_UNBLIND")
        if pkg.get("package_contains_target_names") is not False or pkg.get("package_contains_outcome_labels") is not False or pkg.get("package_contains_post_anchor_predictors") is not False: raise RuntimeError("FAIL_CLOSED_PACKAGE_DISCLOSURE")
        if match.get("status")!="PASS_CLEANROOM_MATCHING" or match.get("cleanroom_input_sha256")!=sha(a.package): raise RuntimeError("FAIL_CLOSED_MATCHING")
        for k in ("precipitation_used_for_matching","outcomes_used_for_matching","target_names_read","free_web_search_used","control_outcome_adjudication_performed","sealed_target_unblind_performed"):
            if match.get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_MATCH_FLAG_{k}")
        if match.get("selected_without_frozen_preanchor_predictors")!=[]: raise RuntimeError("FAIL_CLOSED_SELECTED_PREDICTOR_GAP")
        if len(match.get("shortlists",{}))!=6 or any(len(v)!=3 for v in match["shortlists"].values()): raise RuntimeError("FAIL_CLOSED_SHORTLIST_DIMENSIONS")
        tc={x["target_code"] for x in pkg["targets"]}; cc={x["candidate_code"] for x in pkg["candidates"]}
        if set(match["shortlists"])!=tc or not set(match["selected_candidate_codes"]).issubset(cc): raise RuntimeError("FAIL_CLOSED_CODE_ALIGNMENT")
        if match.get("selected_candidate_count")!=len(set(match["selected_candidate_codes"])): raise RuntimeError("FAIL_CLOSED_SELECTED_COUNT")
        rep.update({"status":"PASS_CLEANROOM_RECOVERY_PRE_FREEZE","checks":{"contaminated_adjudication_excluded":True,"sparse_package_no_revealing_text":True,"matcher_forbidden_imports":bad_imports,"matcher_input_hash_bound":True,"target_count":6,"candidate_count":29,"shortlist_per_target":3,"selected_candidate_count":match["selected_candidate_count"],"all_selected_have_frozen_preanchor_predictors":True,"package_sha256":sha(a.package),"matching_sha256":sha(a.matching),"matcher_sha256":sha(a.matcher),"contract_sha256":sha(a.contract)},"next_gate":"COMMIT_AND_FREEZE_PACKAGE_AND_MATCHING_BEFORE_TERRITORIAL_UNBLIND"})
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_CLEANROOM_RECOVERY","error":str(e),"next_gate":"STOP_NO_UNBLIND"}); a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); print(json.dumps(rep)); return 2
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); print(json.dumps(rep)); return 0
if __name__=="__main__": raise SystemExit(main())
