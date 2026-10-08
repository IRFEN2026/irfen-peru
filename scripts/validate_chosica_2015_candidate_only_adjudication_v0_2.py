#!/usr/bin/env python3
"""Validate candidate-only territorial adjudication v0.2 and freeze controls without discovering evidence."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def nonempty(v): return isinstance(v,str) and bool(v.strip())
def membership_sha(codes:list[str])->str: return hashlib.sha256(("\n".join(codes)+"\n").encode()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--contamination",type=Path,required=True)
    ap.add_argument("--cleanroom-freeze",type=Path,required=True)
    ap.add_argument("--review-contract",type=Path,required=True)
    ap.add_argument("--bundle",type=Path,required=True)
    ap.add_argument("--input",type=Path,required=True)
    ap.add_argument("--mode",choices=("template","adjudication"),required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.2","status":"PENDING","guards":GUARDS,"target_unblind_allowed":False,"scientific_use_allowed":False}
    try:
        co=load(a.contract); contam=load(a.contamination); fr=load(a.cleanroom_freeze); rv=load(a.review_contract); bu=load(a.bundle); inp=load(a.input)
        for o in (co,contam,fr,rv,bu,inp):
            if o.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
        if co.get("status")!="FROZEN_CANDIDATE_ONLY_ADJUDICATION_INGEST_V0_2_CONTRACT": raise RuntimeError("FAIL_CLOSED_CONTRACT_STATUS")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_STATUS")
        for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
            if contam.get("disposition",{}).get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_CONTAMINATED_STAGE_ELIGIBLE {k}")
        if fr.get("status")!="CLEANROOM_RECOVERY_FROZEN_BY_EXACT_HASH": raise RuntimeError("FAIL_CLOSED_CLEANROOM_FREEZE")
        if rv.get("status")!="FROZEN_CANDIDATE_ONLY_REVIEW_V0_2_CONTRACT": raise RuntimeError("FAIL_CLOSED_REVIEW_CONTRACT")
        if bu.get("status")!="FROZEN_CANDIDATE_ONLY_REVIEWER_BUNDLE_V0_2": raise RuntimeError("FAIL_CLOSED_BUNDLE_STATUS")
        if sha(a.bundle)!=co["prerequisites"]["reviewer_bundle_sha256"] or sha(a.bundle)!=rv["output"]["reviewer_bundle_sha256"]: raise RuntimeError("FAIL_CLOSED_BUNDLE_SHA")
        if bu.get("candidate_membership_sha256")!=co["prerequisites"]["candidate_membership_sha256"]: raise RuntimeError("FAIL_CLOSED_MEMBERSHIP_SHA_LINK")
        expected=co["selected_candidate_codes"]
        bundle_codes=[x.get("candidate_code") for x in bu.get("candidates",[])]
        if bundle_codes!=expected or len(expected)!=7 or len(set(expected))!=7: raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MEMBERSHIP")
        raw=a.input.read_text(encoding="utf-8").lower()
        bad=[t for t in co["forbidden_content_tokens_case_insensitive"] if t.lower() in raw]
        if bad: raise RuntimeError(f"FAIL_CLOSED_FORBIDDEN_CONTENT {bad}")
        records=inp.get("candidates")
        if not isinstance(records,list) or [r.get("candidate_code") for r in records]!=expected: raise RuntimeError("FAIL_CLOSED_INPUT_MEMBERSHIP")
        if len(set(r.get("candidate_code") for r in records))!=7: raise RuntimeError("FAIL_CLOSED_DUPLICATE_CANDIDATE")
        att=inp.get("review_attestation",{})
        for k,v in co["review_attestation_required"].items():
            if att.get(k) is not v: raise RuntimeError(f"FAIL_CLOSED_REVIEW_ATTESTATION {k}")
        if inp.get("target_unblind_allowed") is not False: raise RuntimeError("FAIL_CLOSED_TARGET_UNBLIND_FLAG")
        required=set(co["required_record_fields"])
        if a.mode=="template":
            if inp.get("status")!="TEMPLATE_NOT_ADJUDICATED": raise RuntimeError("FAIL_CLOSED_TEMPLATE_STATUS")
            for r in records:
                if set(r.keys())!=required: raise RuntimeError(f"FAIL_CLOSED_TEMPLATE_FIELDS {r.get('candidate_code')}")
                for k in required-{"candidate_code"}:
                    if r.get(k) is not None: raise RuntimeError(f"FAIL_CLOSED_TEMPLATE_PREPOPULATED {r.get('candidate_code')} {k}")
            rep.update({"status":"PASS_CANDIDATE_ONLY_ADJUDICATION_TEMPLATE_V0_2","template_sha256":sha(a.input),"candidate_count":7,"candidate_review_pending":True,"scientific_use_allowed":False,"target_unblind_allowed":False,"next_gate":"INDEPENDENT_CANDIDATE_ONLY_TERRITORIAL_ADJUDICATION_V0_2"})
        else:
            if inp.get("status")!=co["required_status"]: raise RuntimeError("FAIL_CLOSED_ADJUDICATION_STATUS")
            allowed=set(co["allowed_adjudications"]); resolutions=set(co["allowed_evidence_resolution"]); classes=set(co["allowed_source_classes"])
            weak=("no result","not found","no report","silence","absence from","search failed","no mention","no record")
            out=[]
            for r in records:
                missing=required-set(r)
                if missing: raise RuntimeError(f"FAIL_CLOSED_MISSING_FIELDS {r.get('candidate_code')} {sorted(missing)}")
                val=r.get("adjudication"); res=r.get("evidence_resolution"); cls=r.get("source_class")
                if val not in allowed or res not in resolutions or cls not in classes: raise RuntimeError(f"FAIL_CLOSED_ENUM {r.get('candidate_code')}")
                if r.get("reviewer_attestation_no_target_outcome_access") is not True: raise RuntimeError(f"FAIL_CLOSED_RECORD_ATTESTATION {r.get('candidate_code')}")
                if r.get("source_location_caveat_acknowledged") is not True: raise RuntimeError(f"FAIL_CLOSED_LOCATION_CAVEAT {r.get('candidate_code')}")
                for k in ("source_locator","retrieved_at_utc","evidence_sha256_or_stable_source_identifier","evidence_basis"):
                    if not nonempty(r.get(k)): raise RuntimeError(f"FAIL_CLOSED_EVIDENCE_METADATA {r.get('candidate_code')} {k}")
                if res in ("JURISDICTION_ONLY","AMBIGUOUS_OR_UNRESOLVED") and val!="OUTCOME_UNKNOWN": raise RuntimeError(f"FAIL_CLOSED_NON_SPECIFIC_DECISIVE_LABEL {r.get('candidate_code')}")
                if val in ("CONFIRMED_CONTROL","EXCLUDE_ACTIVATED"):
                    if res!="CANDIDATE_SPECIFIC": raise RuntimeError(f"FAIL_CLOSED_DECISIVE_NOT_CANDIDATE_SPECIFIC {r.get('candidate_code')}")
                    if cls=="JURISDICTION_LEVEL_INCIDENT_RECORD": raise RuntimeError(f"FAIL_CLOSED_JURISDICTION_ONLY_DECISIVE_SOURCE {r.get('candidate_code')}")
                if val=="CONFIRMED_CONTROL" and any(w in r["evidence_basis"].lower() for w in weak): raise RuntimeError(f"FAIL_CLOSED_CONTROL_FROM_SILENCE {r.get('candidate_code')}")
                out.append({k:r.get(k) for k in co["required_record_fields"]})
            controls=[r["candidate_code"] for r in out if r["adjudication"]=="CONFIRMED_CONTROL"]
            excluded=[r["candidate_code"] for r in out if r["adjudication"]=="EXCLUDE_ACTIVATED"]
            unknown=[r["candidate_code"] for r in out if r["adjudication"]=="OUTCOME_UNKNOWN"]
            freeze={
                "schema_version":"0.2","batch_id":co["batch_id"],"status":"CANDIDATE_ONLY_CONTROL_SET_V0_2_FROZEN_BY_ADJUDICATION_SHA256","guards":GUARDS,
                "candidate_adjudication_sha256":sha(a.input),"reviewer_bundle_sha256":sha(a.bundle),"candidate_membership_sha256":co["prerequisites"]["candidate_membership_sha256"],
                "candidate_membership_line_sha256":membership_sha(expected),"candidate_count":7,"confirmed_control_codes":controls,"excluded_activated_codes":excluded,"outcome_unknown_codes":unknown,
                "candidate_replacement_performed":False,"matching_recalculated_after_review":False,"selection_feedback_used":False,"contaminated_adjudication_reused":False,
                "target_outcomes_accessed":False,"external_reference_morphometry_accessed":False,"records":out,"target_unblind_allowed":False,
                "next_gate":"EVALUATE_TARGET_CODE_READINESS_WITH_FROZEN_SHORTLISTS_NO_FEEDBACK"
            }
            a.output.write_text(json.dumps(freeze,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
            rep.update({"status":"PASS_CANDIDATE_ONLY_ADJUDICATION_V0_2_FREEZE","scientific_use_allowed":True,"confirmed_control_count":len(controls),"excluded_count":len(excluded),"unknown_count":len(unknown),"output_sha256":sha(a.output),"target_unblind_allowed":False})
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_CANDIDATE_ONLY_ADJUDICATION_V0_2","error":str(e),"scientific_use_allowed":False,"target_unblind_allowed":False,"next_gate":"STOP_NO_UNBLIND"})
        a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); return 2
    if a.mode=="template": a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps(rep,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
