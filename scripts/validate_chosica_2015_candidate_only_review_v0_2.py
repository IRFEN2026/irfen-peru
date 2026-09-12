#!/usr/bin/env python3
"""Validate hardened candidate-only territorial-review handoff without reading outcomes."""
from __future__ import annotations
import argparse, hashlib, json, math, re
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
HEX64=re.compile(r"^[0-9a-f]{64}$")

def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(p:Path):
    return json.loads(p.read_text(encoding="utf-8"))

def fail(msg:str):
    raise RuntimeError(msg)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--fingerprints",type=Path,required=True)
    ap.add_argument("--bundle",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.2","status":"PENDING","guards":GUARDS,"target_unblind_allowed":False}
    try:
        co=load(a.contract); fp=load(a.fingerprints); bu=load(a.bundle)
        if co.get("guards")!=GUARDS or fp.get("guards")!=GUARDS or bu.get("guards")!=GUARDS: fail("FAIL_CLOSED_GUARDS")
        if co.get("status")!="FROZEN_CANDIDATE_ONLY_REVIEW_V0_2_CONTRACT": fail("FAIL_CLOSED_CONTRACT_STATUS")
        if fp.get("status")!="CANDIDATE_ONLY_GEOMETRY_FINGERPRINTS_FROZEN_FROM_PREINCIDENT_ARTIFACT": fail("FAIL_CLOSED_FINGERPRINT_STATUS")
        if bu.get("status")!="FROZEN_CANDIDATE_ONLY_REVIEWER_BUNDLE_V0_2": fail("FAIL_CLOSED_BUNDLE_STATUS")
        if sha(a.fingerprints)!=co["inputs"]["geometry_fingerprint_freeze_sha256"]: fail("FAIL_CLOSED_FINGERPRINT_HASH")
        if sha(a.bundle)!=co["output"]["reviewer_bundle_sha256"]: fail("FAIL_CLOSED_BUNDLE_HASH")
        if bu.get("geometry_fingerprint_freeze_sha256")!=sha(a.fingerprints): fail("FAIL_CLOSED_FINGERPRINT_LINK")
        if bu.get("source_bundle_v0_1_sha256")!=co["inputs"]["reviewer_bundle_v0_1_sha256"]: fail("FAIL_CLOSED_SOURCE_BUNDLE_LINK")
        if bu.get("candidate_membership_sha256")!=co["output"]["candidate_membership_sha256"]: fail("FAIL_CLOSED_MEMBERSHIP_HASH")
        fpcs=[x.get("candidate_code") for x in fp.get("candidates",[])]
        bucs=[x.get("candidate_code") for x in bu.get("candidates",[])]
        if len(fpcs)!=7 or len(bucs)!=7 or fpcs!=bucs or len(set(bucs))!=7: fail("FAIL_CLOSED_CANDIDATE_SET")
        if fp.get("candidate_count")!=7 or bu.get("candidate_count")!=7: fail("FAIL_CLOSED_CANDIDATE_COUNT")
        fpby={x["candidate_code"]:x for x in fp["candidates"]}
        for c in bu["candidates"]:
            f=fpby[c["candidate_code"]]
            if c.get("geometry_sha256")!=f.get("geometry_sha256") or c.get("bbox_wgs84")!=f.get("bbox_wgs84") or c.get("geometry_vertex_count")!=f.get("vertex_count"): fail("FAIL_CLOSED_GEOMETRY_FINGERPRINT_MISMATCH")
            if not HEX64.match(str(c.get("geometry_sha256",""))): fail("FAIL_CLOSED_GEOMETRY_HASH_FORMAT")
            b=c.get("bbox_wgs84")
            if not isinstance(b,list) or len(b)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(float(v)) for v in b): fail("FAIL_CLOSED_BBOX_FORMAT")
            if not (-180<=b[0]<b[2]<=180 and -90<=b[1]<b[3]<=90): fail("FAIL_CLOSED_BBOX_RANGE")
        text=a.bundle.read_text(encoding="utf-8").lower()
        bad=[tok for tok in co.get("forbidden_tokens_case_insensitive",[]) if tok.lower() in text]
        if bad: fail(f"FAIL_CLOSED_FORBIDDEN_TOKEN {bad}")
        if bu.get("selection_feedback_allowed") is not False or bu.get("candidate_replacement_allowed") is not False or bu.get("target_unblind_allowed") is not False: fail("FAIL_CLOSED_FEEDBACK_OR_UNBLIND")
        att=bu.get("reviewer_attestation_requirements",{})
        required_true=("review_process_isolated_from_target_outcomes","candidate_membership_fixed_before_review")
        required_false=("candidate_replacement_performed","matching_recalculated_after_review","selection_feedback_used","target_outcomes_accessed","external_reference_morphometry_accessed","contaminated_stage_material_accessed","free_text_queries_include_target_identifiers")
        if any(att.get(k) is not True for k in required_true) or any(att.get(k) is not False for k in required_false): fail("FAIL_CLOSED_REVIEW_ATTESTATION_POLICY")
        dg=bu.get("review_return_schema",{}).get("decisive_label_gate",{})
        if dg.get("allowed_evidence_resolution")!="CANDIDATE_SPECIFIC" or dg.get("jurisdiction_level_incident_record_alone_allowed") is not False or dg.get("documentary_silence_allowed") is not False: fail("FAIL_CLOSED_DECISIVE_EVIDENCE_GATE")
        if bu.get("evidence_rules",{}).get("documentary_silence")!="OUTCOME_UNKNOWN" or bu.get("evidence_rules",{}).get("jurisdiction_only_source_alone")!="OUTCOME_UNKNOWN": fail("FAIL_CLOSED_UNKNOWN_POLICY")
        rep.update({
            "status":"PASS_CANDIDATE_ONLY_REVIEW_V0_2_HANDOFF",
            "fingerprint_sha256":sha(a.fingerprints),
            "bundle_sha256":sha(a.bundle),
            "candidate_count":7,
            "candidate_membership_sha256":bu["candidate_membership_sha256"],
            "candidate_review_allowed":True,
            "candidate_replacement_allowed":False,
            "matching_recalculation_allowed":False,
            "selection_feedback_allowed":False,
            "target_unblind_allowed":False,
            "next_gate":"INDEPENDENT_CANDIDATE_ONLY_TERRITORIAL_ADJUDICATION_V0_2"
        })
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_CANDIDATE_ONLY_REVIEW_V0_2_HANDOFF","candidate_review_allowed":False,"error":str(e),"next_gate":"STOP_NO_UNBLIND"})
        a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
        return 2
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps(rep,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
