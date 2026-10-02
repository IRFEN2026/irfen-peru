#!/usr/bin/env python3
"""Validate an independently produced candidate-only territorial adjudication and freeze the control set.

This process MUST NOT discover evidence. It only validates a pre-existing isolated-review artifact
against the frozen candidate membership and scientific guardrails.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
ALLOWED={"CONFIRMED_CONTROL","EXCLUDE_ACTIVATED","OUTCOME_UNKNOWN"}

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def membership_sha(codes:list[str])->str:
    b=("\n".join(codes)+"\n").encode(); return hashlib.sha256(b).hexdigest()
def nonempty(v): return isinstance(v,str) and bool(v.strip())
def string_values(obj):
    if isinstance(obj,str):
        yield obj
    elif isinstance(obj,dict):
        for v in obj.values(): yield from string_values(v)
    elif isinstance(obj,list):
        for v in obj: yield from string_values(v)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--cleanroom-freeze",type=Path,required=True)
    ap.add_argument("--contamination",type=Path,required=True)
    ap.add_argument("--territorial-contract",type=Path,required=True)
    ap.add_argument("--packet",type=Path,required=True)
    ap.add_argument("--adjudication",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.1","status":"PENDING","guards":GUARDS,"target_unblind_allowed":False,"scientific_use_allowed":False}
    try:
        co=load(a.contract); fr=load(a.cleanroom_freeze); contam=load(a.contamination); territorial=load(a.territorial_contract); pkt=load(a.packet); adj=load(a.adjudication)
        for obj in (co,fr,contam,territorial,pkt,adj):
            if obj.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
        if co.get("status")!="FROZEN_CANDIDATE_ONLY_ADJUDICATION_INGEST_CONTRACT": raise RuntimeError("FAIL_CLOSED_INGEST_CONTRACT_STATUS")
        if fr.get("status")!="CLEANROOM_RECOVERY_FROZEN_BY_EXACT_HASH": raise RuntimeError("FAIL_CLOSED_CLEANROOM_NOT_FROZEN")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_TOMBSTONE")
        for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
            if contam.get("disposition",{}).get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_CONTAMINATED_STAGE_ELIGIBLE {k}")
        if sha(a.packet)!=co["prerequisites"]["candidate_review_packet_sha256"]: raise RuntimeError("FAIL_CLOSED_PACKET_SHA")
        if pkt.get("cleanroom_matching_sha256")!=co["prerequisites"]["cleanroom_matching_sha256"]: raise RuntimeError("FAIL_CLOSED_MATCHING_LINK")
        codes=[x.get("candidate_code") for x in pkt.get("candidates",[])]
        expected=co["selected_candidate_codes"]
        if codes!=expected or territorial.get("selected_candidate_codes")!=expected: raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MEMBERSHIP")
        if any(x.get("adjudication") is not None for x in pkt.get("candidates",[])): raise RuntimeError("FAIL_CLOSED_PACKET_ALREADY_ADJUDICATED")
        if adj.get("status")!="INDEPENDENT_CANDIDATE_ONLY_TERRITORIAL_ADJUDICATION_COMPLETE": raise RuntimeError("FAIL_CLOSED_ADJUDICATION_STATUS")
        att=adj.get("review_attestation",{})
        required_att={
          "review_process_isolated_from_target_outcomes":True,
          "candidate_membership_fixed_before_review":True,
          "candidate_replacement_performed":False,
          "matching_recalculated_after_review":False,
          "selection_feedback_used":False,
          "target_outcomes_accessed":False,
          "contaminated_stage_material_accessed":False
        }
        for k,v in required_att.items():
            if att.get(k) is not v: raise RuntimeError(f"FAIL_CLOSED_REVIEW_ATTESTATION {k}")
        # Clean-room reviewer bundle uses a neutral attestation key so the reviewer never receives
        # the name of the prohibited external morphometry source. Legacy key is accepted only if false.
        neutral_ref=att.get("external_reference_morphometry_accessed")
        legacy_ref=att.get("a6680_accessed")
        if neutral_ref is not False and legacy_ref is not False:
            raise RuntimeError("FAIL_CLOSED_REVIEW_ATTESTATION external_reference_morphometry_accessed")
        if neutral_ref is True or legacy_ref is True:
            raise RuntimeError("FAIL_CLOSED_EXTERNAL_REFERENCE_MORPHOMETRY_ACCESSED")
        records=adj.get("candidates")
        if not isinstance(records,list) or len(records)!=len(expected): raise RuntimeError("FAIL_CLOSED_RECORD_COUNT")
        got=[r.get("candidate_code") for r in records]
        if got!=expected or len(set(got))!=len(expected): raise RuntimeError("FAIL_CLOSED_ADJUDICATION_MEMBERSHIP")
        required=set(co["required_record_fields"])
        out=[]
        for r in records:
            missing=required-set(r)
            if missing: raise RuntimeError(f"FAIL_CLOSED_MISSING_FIELDS {r.get('candidate_code')} {sorted(missing)}")
            val=r.get("adjudication")
            if val not in ALLOWED: raise RuntimeError(f"FAIL_CLOSED_BAD_ADJUDICATION {r.get('candidate_code')}")
            if r.get("reviewer_attestation_no_target_outcome_access") is not True: raise RuntimeError(f"FAIL_CLOSED_RECORD_ATTESTATION {r.get('candidate_code')}")
            if not nonempty(r.get("source_locator")) or not nonempty(r.get("retrieved_at_utc")) or not nonempty(r.get("evidence_sha256_or_stable_source_identifier")) or not nonempty(r.get("evidence_basis")):
                raise RuntimeError(f"FAIL_CLOSED_EVIDENCE_METADATA {r.get('candidate_code')}")
            if val=="CONFIRMED_CONTROL":
                basis=r["evidence_basis"].strip().lower()
                weak=("no result","not found","no report","silence","absence from","search failed","no mention")
                if any(w in basis for w in weak): raise RuntimeError(f"FAIL_CLOSED_CONTROL_FROM_SILENCE {r.get('candidate_code')}")
            out.append({k:r.get(k) for k in co["required_record_fields"]})
        value_text="\n".join(string_values(adj)).lower()
        bad=[t for t in co["forbidden_content_tokens_case_insensitive"] if t.lower() in value_text]
        if bad: raise RuntimeError(f"FAIL_CLOSED_FORBIDDEN_CONTENT {bad}")
        if any(x in value_text for x in ("blinding_incident_2026_09_09","official_outcome_evidence")): raise RuntimeError("FAIL_CLOSED_CONTAMINATED_OR_TARGET_PROVENANCE")
        control_codes=[r["candidate_code"] for r in out if r["adjudication"]=="CONFIRMED_CONTROL"]
        excluded_codes=[r["candidate_code"] for r in out if r["adjudication"]=="EXCLUDE_ACTIVATED"]
        unknown_codes=[r["candidate_code"] for r in out if r["adjudication"]=="OUTCOME_UNKNOWN"]
        freeze={
          "schema_version":"0.1","batch_id":co["batch_id"],"status":"CANDIDATE_ONLY_CONTROL_SET_FROZEN_BY_ADJUDICATION_SHA256",
          "guards":GUARDS,"candidate_adjudication_sha256":sha(a.adjudication),"candidate_review_packet_sha256":sha(a.packet),
          "cleanroom_matching_sha256":co["prerequisites"]["cleanroom_matching_sha256"],"candidate_membership_sha256":membership_sha(expected),
          "candidate_count":len(expected),"confirmed_control_codes":control_codes,"excluded_activated_codes":excluded_codes,"outcome_unknown_codes":unknown_codes,
          "candidate_replacement_performed":False,"matching_recalculated_after_review":False,"selection_feedback_used":False,
          "contaminated_adjudication_reused":False,"target_outcomes_accessed":False,"a6680_accessed":False,
          "records":out,"target_unblind_allowed":False,
          "next_gate":"SEPARATE_TARGET_UNBLIND_READINESS_REQUIRES_EXPLICIT_CONTROL_SET_POLICY_AND_NO_SCIENTIFIC_GUARD_RELAXATION"
        }
        a.output.write_text(json.dumps(freeze,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
        rep.update({"status":"PASS_CANDIDATE_ONLY_ADJUDICATION_FREEZE","scientific_use_allowed":True,"confirmed_control_count":len(control_codes),"unknown_count":len(unknown_codes),"excluded_count":len(excluded_codes),"output_sha256":sha(a.output),"target_unblind_allowed":False})
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_CANDIDATE_ONLY_ADJUDICATION_FREEZE","error":str(e),"target_unblind_allowed":False,"scientific_use_allowed":False})
        a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); return 2
    print(json.dumps(rep,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
