#!/usr/bin/env python3
"""Audit UTC versus Peru-local calendar features from frozen IMERG slots.

RESEARCH_ONLY / TEST_ONLY. Uses only the already-frozen basin-weighted slot
series. No territorial outcome, activation time, or missing-value imputation is
used. Peru local time is fixed at UTC-05:00 for the 2015 study window.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

PERU=timezone(timedelta(hours=-5),name="UTC-05:00")

def parse(s): return datetime.fromisoformat(str(s).replace("Z","+00:00"))
def roll(vals,n):
    a=np.asarray(vals,float); sums=np.convolve(a,np.ones(n),mode="valid"); k=int(np.argmax(sums))
    return {"depth_mm":float(sums[k]),"start_slot_index":k,"end_slot_index":k+n-1}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--source",required=True,type=Path); ap.add_argument("--local-date",required=True); ap.add_argument("--output",required=True,type=Path); a=ap.parse_args()
    d=json.loads(a.source.read_text(encoding="utf-8"))
    assert d["deployment_status"]=="RESEARCH_ONLY" and d["test_only"] is True
    assert d["production_use"] is False and d["production_ready"] is False and d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False and d["territorial_activation_evidence_blinded"] is True
    assert d["feature_status"]=="FROZEN_BLIND_OBSERVATIONAL_FEATURES" and d["raw_identity"]["match"] is True
    rows=d["slots_detail"]
    for r in rows:
        assert r["status"]=="SUCCESS" and r["depth_30m_mm"] is not None
        r["_utc"]=parse(r["time_start"]); r["_local"]=r["_utc"].astimezone(PERU)
    local=[r for r in rows if r["_local"].date().isoformat()==a.local_date]
    if len(local)!=48: raise SystemExit(f"expected 48 local-date slots, got {len(local)}")
    local.sort(key=lambda r:r["_utc"]); vals=[float(r["depth_30m_mm"]) for r in local]
    first=local[0]; idx=next(i for i,r in enumerate(rows) if r["producer_granule_id"]==first["producer_granule_id"])
    preceding=rows[:idx]
    if len(preceding)<336: raise SystemExit("insufficient 7-day local antecedent coverage")
    pv=[float(r["depth_30m_mm"]) for r in preceding]
    local_features={
      "date":a.local_date,"timezone":"America/Lima fixed UTC-05:00","slots":48,
      "utc_window_start":local[0]["time_start"],"utc_window_end_slot_start":local[-1]["time_start"],
      "p30m_max_mm":max(vals),"p1h_max":roll(vals,2),"p3h_max":roll(vals,6),"p6h_max":roll(vals,12),"p12h_max":roll(vals,24),"p24h_total_mm":float(sum(vals)),
      "antecedent_ending_local_00":{"p24h_mm":float(sum(pv[-48:])),"p72h_mm":float(sum(pv[-144:])),"p7d_mm":float(sum(pv[-336:]))}
    }
    utc=d["features"]["event_day_utc"]
    out={
      "schema_version":"irfen-ibvf-imerg-timebasis-audit-v0.1","case_id":d["case_id"],"deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,
      "source_path":str(a.source),"source_raw_identity":d["raw_identity"],"event_time_used":False,"utc_calendar_features":utc,"peru_local_calendar_features":local_features,
      "comparison":{"p24h_local_minus_utc_mm":local_features["p24h_total_mm"]-float(utc["p24h_total_mm"]),"p30m_local_minus_utc_mm":local_features["p30m_max_mm"]-float(utc["p30m_max_mm"])},
      "scientific_interpretation":"TIME_BASIS_SENSITIVITY_ONLY_NO_ACTIVATION_INFERENCE","serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED"
    }
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"utc_p24h":utc["p24h_total_mm"],"local_p24h":local_features["p24h_total_mm"],"local_p3h":local_features["p3h_max"]["depth_mm"],"local_antecedent":local_features["antecedent_ending_local_00"]},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
