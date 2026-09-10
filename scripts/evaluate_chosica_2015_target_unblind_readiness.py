#!/usr/bin/env python3
"""Evaluate neutral target-code readiness after the independent candidate-only control freeze.

This script never reads target outcomes, names, A6680, post-event evidence, or contaminated adjudication.
It only evaluates whether each frozen anonymous target shortlist contains affirmative controls.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--cleanroom-freeze",type=Path,required=True)
    ap.add_argument("--contamination",type=Path,required=True)
    ap.add_argument("--control-set-freeze",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.1","status":"PENDING","guards":GUARDS,"target_outcomes_read":False,"a6680_read":False,"automatic_unblind_performed":False}
    try:
        co=load(a.contract); fr=load(a.cleanroom_freeze); contam=load(a.contamination); ctrl=load(a.control_set_freeze)
        for obj in (co,fr,contam,ctrl):
            if obj.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
        if co.get("status")!="FROZEN_TARGET_UNBLIND_READINESS_CONTRACT": raise RuntimeError("FAIL_CLOSED_CONTRACT_STATUS")
        if fr.get("status")!="CLEANROOM_RECOVERY_FROZEN_BY_EXACT_HASH": raise RuntimeError("FAIL_CLOSED_CLEANROOM_STATUS")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_TOMBSTONE")
        for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
            if contam.get("disposition",{}).get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_CONTAMINATION_ELIGIBLE {k}")
        if ctrl.get("status")!="CANDIDATE_ONLY_CONTROL_SET_FROZEN_BY_ADJUDICATION_SHA256": raise RuntimeError("FAIL_CLOSED_CONTROL_SET_STATUS")
        if ctrl.get("cleanroom_matching_sha256")!=co["prerequisites"]["cleanroom_matching_sha256"]: raise RuntimeError("FAIL_CLOSED_MATCHING_HASH")
        if ctrl.get("candidate_membership_sha256")!=co["prerequisites"]["candidate_membership_sha256"]: raise RuntimeError("FAIL_CLOSED_MEMBERSHIP_HASH")
        if ctrl.get("candidate_replacement_performed") is not False or ctrl.get("matching_recalculated_after_review") is not False or ctrl.get("selection_feedback_used") is not False:
            raise RuntimeError("FAIL_CLOSED_SELECTION_FEEDBACK")
        if ctrl.get("contaminated_adjudication_reused") is not False or ctrl.get("target_outcomes_accessed") is not False or ctrl.get("a6680_accessed") is not False:
            raise RuntimeError("FAIL_CLOSED_FORBIDDEN_SOURCE_USE")
        confirmed=set(ctrl.get("confirmed_control_codes",[])); excluded=set(ctrl.get("excluded_activated_codes",[])); unknown=set(ctrl.get("outcome_unknown_codes",[]))
        all_codes=confirmed|excluded|unknown
        if len(all_codes)!=ctrl.get("candidate_count") or (confirmed&excluded) or (confirmed&unknown) or (excluded&unknown): raise RuntimeError("FAIL_CLOSED_CONTROL_PARTITION")
        target_results={}
        eligible=[]
        min_controls=int(co["eligibility_rule"]["minimum_confirmed_controls_within_frozen_shortlist"])
        for target_code, shortlist in co["frozen_target_shortlists"].items():
            hits=[c for c in shortlist if c in confirmed]
            ok=len(hits)>=min_controls
            target_results[target_code]={"frozen_shortlist":shortlist,"confirmed_controls_in_shortlist":hits,"confirmed_control_count":len(hits),"eligible_for_separate_explicit_unblind_record":ok}
            if ok: eligible.append(target_code)
        rep.update({
          "status":"PASS_TARGET_UNBLIND_READINESS_EVALUATION",
          "control_set_freeze_sha256":sha(a.control_set_freeze),
          "target_code_count":len(target_results),
          "eligible_target_codes":eligible,
          "eligible_target_count":len(eligible),
          "ineligible_target_count":len(target_results)-len(eligible),
          "target_results":target_results,
          "automatic_unblind_performed":False,
          "target_outcomes_read":False,
          "a6680_read":False,
          "next_gate":"CREATE_SEPARATE_EXPLICIT_UNBLIND_RECORD_FOR_ELIGIBLE_TARGET_CODES_ONLY_WITH_NO_MATCHING_FEEDBACK"
        })
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_TARGET_UNBLIND_READINESS","error":str(e),"eligible_target_codes":[],"eligible_target_count":0,"automatic_unblind_performed":False,"target_outcomes_read":False,"a6680_read":False})
        a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); return 2
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps(rep,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
