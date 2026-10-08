#!/usr/bin/env python3
"""Validate the frozen candidate-only territorial review boundary without reading outcomes."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
REVEALING=("cashahuacra","quirio","pedregal","san_antonio","san antonio","la_libertad","la libertad","carossio","carosio","rayos_de_sol","rayos de sol","corrales","official_outcome_evidence")

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--cleanroom-freeze",type=Path,required=True)
    ap.add_argument("--contamination",type=Path,required=True)
    ap.add_argument("--packet",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    rep={"schema_version":"0.1","status":"PENDING","guards":GUARDS,"target_unblind_allowed":False,"control_outcome_adjudication_performed":False}
    try:
        co=load(a.contract); fr=load(a.cleanroom_freeze); contam=load(a.contamination); pkt=load(a.packet)
        if any(x.get("guards")!=GUARDS for x in (co,fr,contam,pkt)): raise RuntimeError("FAIL_CLOSED_GUARDS")
        if fr.get("status")!="CLEANROOM_RECOVERY_FROZEN_BY_EXACT_HASH": raise RuntimeError("FAIL_CLOSED_CLEANROOM_NOT_FROZEN")
        if contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise RuntimeError("FAIL_CLOSED_CONTAMINATION_TOMBSTONE")
        if any(contam["disposition"].get(k) is not False for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate")): raise RuntimeError("FAIL_CLOSED_CONTAMINATED_STAGE_ELIGIBLE")
        if sha(a.packet)!=co["review_packet_sha256"]: raise RuntimeError("FAIL_CLOSED_REVIEW_PACKET_HASH")
        if pkt.get("status")!="FROZEN_CANDIDATE_ONLY_TERRITORIAL_REVIEW_PACKET": raise RuntimeError("FAIL_CLOSED_PACKET_STATUS")
        if pkt.get("cleanroom_matching_sha256")!=fr["frozen_outputs"]["cleanroom_matching"]["sha256"] or pkt.get("cleanroom_matching_sha256")!=co["cleanroom_matching_sha256"]: raise RuntimeError("FAIL_CLOSED_MATCHING_HASH_LINK")
        if pkt.get("sealed_target_outcomes_allowed") is not False or pkt.get("selection_feedback_allowed") is not False or pkt.get("candidate_replacement_allowed") is not False or pkt.get("a6680_allowed") is not False: raise RuntimeError("FAIL_CLOSED_PACKET_POLICY")
        codes=[x.get("candidate_code") for x in pkt.get("candidates",[])]
        if codes!=co["selected_candidate_codes"] or len(codes)!=co["selected_candidate_count"]==7 or len(set(codes))!=7: raise RuntimeError("FAIL_CLOSED_CANDIDATE_MEMBERSHIP")
        if any(x.get("adjudication") is not None for x in pkt["candidates"]): raise RuntimeError("FAIL_CLOSED_PREMATURE_ADJUDICATION")
        text=a.packet.read_text(encoding="utf-8").lower()
        bad=[x for x in REVEALING if x in text]
        if bad: raise RuntimeError(f"FAIL_CLOSED_REVEALING_TARGET_IN_PACKET {bad}")
        if co["adjudication"].get("selection_feedback_allowed") is not False or co["adjudication"].get("matching_recalculation_after_review") is not False or co["adjudication"].get("candidate_replacement_after_review") is not False or co["adjudication"].get("target_unblind_allowed") is not False: raise RuntimeError("FAIL_CLOSED_CONTRACT_FEEDBACK_POLICY")
        rep.update({
          "status":"PASS_CANDIDATE_ONLY_TERRITORIAL_REVIEW_GATE",
          "candidate_review_allowed":True,
          "candidate_count":7,
          "review_packet_sha256":sha(a.packet),
          "cleanroom_matching_sha256":co["cleanroom_matching_sha256"],
          "selection_feedback_allowed":False,
          "candidate_replacement_allowed":False,
          "matching_recalculation_allowed":False,
          "target_unblind_allowed":False,
          "a6680_allowed":False,
          "next_gate":"INDEPENDENT_PROCESS_CANDIDATE_ONLY_TERRITORIAL_ADJUDICATION"
        })
    except Exception as e:
        rep.update({"status":"FAIL_CLOSED_CANDIDATE_ONLY_TERRITORIAL_REVIEW_GATE","candidate_review_allowed":False,"error":str(e),"next_gate":"STOP_NO_UNBLIND"})
        a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); return 2
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); print(json.dumps(rep,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
