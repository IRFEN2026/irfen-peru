#!/usr/bin/env python3
"""Evaluate anonymous target-code readiness from the clean-room v0.2 control-set freeze only."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p:Path,d:dict):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--cleanroom-freeze",type=Path,required=True)
    ap.add_argument("--contamination",type=Path,required=True)
    ap.add_argument("--ingest-contract",type=Path,required=True)
    ap.add_argument("--control-set-freeze",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    rep={"schema_version":"0.2","status":"PENDING","guards":GUARDS,"target_unblind_allowed":False,"automatic_unblind_performed":False,"target_outcomes_read":False,"a6680_read":False}
    try:
        co=load(a.contract); fr=load(a.cleanroom_freeze); contam=load(a.contamination); ing=load(a.ingest_contract)
        for obj in (co,fr,contam,ing):
            if obj.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
        if co.get("status")!="FROZEN_TARGET_UNBLIND_READINESS_V0_2_CONTRACT": raise RuntimeError("FAIL_CLOSED_CONTRACT_STATUS")
        if fr.get("status")!="CLEANROOM_RECOVERY_FROZEN_BY_EXACT_HASH": raise RuntimeError("FAIL_CLOSED_CLEANROOM_STATUS")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_TOMBSTONE")
        for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
            if contam.get("disposition",{}).get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_CONTAMINATION_ELIGIBLE {k}")
        if ing.get("status")!="FROZEN_CANDIDATE_ONLY_ADJUDICATION_INGEST_V0_2_CONTRACT": raise RuntimeError("FAIL_CLOSED_INGEST_STATUS")
        pre=co["prerequisites"]
        if ing["prerequisites"]["reviewer_bundle_sha256"]!=pre["reviewer_bundle_sha256"]: raise RuntimeError("FAIL_CLOSED_REVIEWER_BUNDLE_LINK")
        if ing["prerequisites"]["candidate_membership_sha256"]!=pre["candidate_membership_sha256"]: raise RuntimeError("FAIL_CLOSED_MEMBERSHIP_LINK")
        expected=ing["selected_candidate_codes"]
        line_hash=hashlib.sha256(("\n".join(expected)+"\n").encode()).hexdigest()
        if line_hash!=pre["candidate_membership_line_sha256"]: raise RuntimeError("FAIL_CLOSED_LINE_MEMBERSHIP_LINK")
        if not a.control_set_freeze.exists():
            rep.update({"status":"WAITING_FOR_INDEPENDENT_CANDIDATE_ONLY_CONTROL_SET_V0_2","scientific_use_allowed":False,"eligible_target_codes":[],"eligible_target_count":0,"target_unblind_allowed":False,"next_gate":"COMMIT_VALIDATED_V0_2_CONTROL_SET_FREEZE_FROM_ISOLATED_REVIEW"})
            write(a.output,rep); print(json.dumps(rep,sort_keys=True)); return 0
        ctrl=load(a.control_set_freeze)
        if ctrl.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_CONTROL_GUARDS")
        if ctrl.get("status")!="CANDIDATE_ONLY_CONTROL_SET_V0_2_FROZEN_BY_ADJUDICATION_SHA256": raise RuntimeError("FAIL_CLOSED_CONTROL_SET_STATUS")
        if ctrl.get("reviewer_bundle_sha256")!=pre["reviewer_bundle_sha256"]: raise RuntimeError("FAIL_CLOSED_CONTROL_REVIEWER_BUNDLE_SHA")
        if ctrl.get("candidate_membership_sha256")!=pre["candidate_membership_sha256"]: raise RuntimeError("FAIL_CLOSED_CONTROL_MEMBERSHIP_SHA")
        if ctrl.get("candidate_membership_line_sha256")!=pre["candidate_membership_line_sha256"]: raise RuntimeError("FAIL_CLOSED_CONTROL_LINE_MEMBERSHIP_SHA")
        if ctrl.get("candidate_count")!=len(expected) or len(expected)!=7 or len(set(expected))!=7: raise RuntimeError("FAIL_CLOSED_CANDIDATE_COUNT")
        for k in ("candidate_replacement_performed","matching_recalculated_after_review","selection_feedback_used","contaminated_adjudication_reused","target_outcomes_accessed","external_reference_morphometry_accessed"):
            if ctrl.get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_FORBIDDEN_CONTROL_FLAG {k}")
        confirmed=set(ctrl.get("confirmed_control_codes",[])); excluded=set(ctrl.get("excluded_activated_codes",[])); unknown=set(ctrl.get("outcome_unknown_codes",[])); exp=set(expected)
        if confirmed|excluded|unknown != exp: raise RuntimeError("FAIL_CLOSED_CONTROL_PARTITION_MEMBERSHIP")
        if confirmed&excluded or confirmed&unknown or excluded&unknown: raise RuntimeError("FAIL_CLOSED_CONTROL_PARTITION_OVERLAP")
        target_results={}; eligible=[]
        minimum=int(co["eligibility_rule"]["minimum_confirmed_controls_within_frozen_shortlist"])
        for target_code,shortlist in co["frozen_target_shortlists"].items():
            if any(c not in exp for c in shortlist): raise RuntimeError(f"FAIL_CLOSED_SHORTLIST_MEMBER {target_code}")
            hits=[c for c in shortlist if c in confirmed]; ok=len(hits)>=minimum
            target_results[target_code]={"frozen_shortlist":shortlist,"confirmed_controls_in_shortlist":hits,"confirmed_control_count":len(hits),"eligible_for_separate_explicit_unblind_record":ok}
            if ok: eligible.append(target_code)
        rep.update({"status":"PASS_TARGET_UNBLIND_READINESS_V0_2","scientific_use_allowed":True,"control_set_freeze_sha256":sha(a.control_set_freeze),"target_code_count":len(target_results),"eligible_target_codes":eligible,"eligible_target_count":len(eligible),"ineligible_target_count":len(target_results)-len(eligible),"target_results":target_results,"target_unblind_allowed":False,"automatic_unblind_performed":False,"target_outcomes_read":False,"a6680_read":False,"next_gate":"CREATE_SEPARATE_EXPLICIT_UNBLIND_RECORD_FOR_ELIGIBLE_ANONYMOUS_TARGET_CODES_ONLY"})
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_TARGET_UNBLIND_READINESS_V0_2","error":str(e),"scientific_use_allowed":False,"eligible_target_codes":[],"eligible_target_count":0,"target_unblind_allowed":False,"automatic_unblind_performed":False,"target_outcomes_read":False,"a6680_read":False,"next_gate":"STOP_NO_UNBLIND"})
        write(a.output,rep); return 2
    write(a.output,rep); print(json.dumps(rep,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
