#!/usr/bin/env python3
"""Execute the frozen IBVF meteorological ranking on an approved blind cohort.

The v0.2 gate permits ranking PRIMARY6_CHRONOLOGICAL after six complete frozen
A3 partitions. FULL12_ROBUSTNESS may later be ranked separately with identical
rules. No outcome, event, sensor-availability, risk or alert fields are read.
"""
from __future__ import annotations

import argparse, hashlib, json, math
from datetime import date
from pathlib import Path
from typing import Any, Iterable

FEATURES=("P3H_MAX","P24H_LOCAL","ANTECEDENT_7D")
FORBIDDEN=("outcome","event","activation","damage","incident","case_control","case_role","control_role","label","risk","alert","priority","sensor_availability")

def csha(x:Any)->str: return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def sha_file(p:Path)->str:
    h=hashlib.sha256();
    with p.open("rb") as f:
        for b in iter(lambda:f.read(4*1024*1024),b""): h.update(b)
    return h.hexdigest()
def finite(v:Any)->bool: return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def guards(d:dict[str,Any])->None:
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"
def reject(rows:Iterable[dict[str,Any]])->None:
    for i,r in enumerate(rows):
        for k in r:
            if any(x in str(k).lower() for x in FORBIDDEN): raise ValueError(f"forbidden field row {i}: {k}")
def midrank(vals:dict[str,float])->dict[str,float]:
    items=sorted(vals.items(),key=lambda kv:(kv[1],kv[0])); n=len(items)
    if not n:return {}
    if n==1:return {items[0][0]:0.5}
    out={}; i=0
    while i<n:
        j=i+1
        while j<n and items[j][1]==items[i][1]:j+=1
        avg=((i+1)+j)/2.0; pct=(avg-1.0)/(n-1.0)
        for k in range(i,j):out[items[k][0]]=pct
        i=j
    return out
def select_group(rows:list[dict[str,Any]],contract:dict[str,Any])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    by={r["date_local"]:r for r in rows}; known=[d for d,r in by.items() if all(finite(r.get(f)) for f in FEATURES)]
    pct={f:midrank({d:float(by[d][f]) for d in known}) for f in FEATURES}
    comp={d:sum(pct[f][d] for f in FEATURES)/3.0 for d in known}; cpct=midrank(comp)
    enriched=[]
    for d in sorted(by):
        r=by[d]; enriched.append({"unit_id":r["unit_id"],"season_id":r["season_id"],"date_local":d,
          **{f:r.get(f) for f in FEATURES},"PCT_P3H_MAX":pct["P3H_MAX"].get(d),"PCT_P24H_LOCAL":pct["P24H_LOCAL"].get(d),
          "PCT_ANTECEDENT_7D":pct["ANTECEDENT_7D"].get(d),"MET_COMPOSITE_SCORE":comp.get(d),"MET_COMPOSITE_PERCENTILE":cpct.get(d),
          "rank_status":"KNOWN" if d in comp else "UNKNOWN_MISSING_FEATURE_NO_IMPUTATION","selected":False,
          "selected_target_percentile":None,"selected_target_order":None,"case_control_role":"UNASSIGNED"})
    eby={e["date_local"]:e for e in enriched}; selected=[]; anchors=[]; sep=int(contract["primary_selection"]["minimum_anchor_separation_days"])
    for order,target in enumerate([float(x) for x in contract["primary_selection"]["target_order"]],1):
        cand=[]
        for d,p in cpct.items():
            dd=date.fromisoformat(d)
            if any(abs((dd-a).days)<sep for a in anchors):continue
            cand.append((abs(float(p)-target),d))
        if not cand:
            selected.append({"target_percentile":target,"target_order":order,"status":"STRATUM_UNAVAILABLE_NO_REPLACEMENT_FROM_OTHER_SEASON","date_local":None}); continue
        _,chosen=min(cand,key=lambda x:(x[0],x[1])); anchors.append(date.fromisoformat(chosen)); e=eby[chosen]
        e["selected"]=True;e["selected_target_percentile"]=target;e["selected_target_order"]=order
        selected.append({"target_percentile":target,"target_order":order,"status":"SELECTED_BLIND_METEOROLOGICAL_STRATUM","date_local":chosen,
          "composite_score":e["MET_COMPOSITE_SCORE"],"composite_percentile":e["MET_COMPOSITE_PERCENTILE"],
          "absolute_target_distance":abs(float(e["MET_COMPOSITE_PERCENTILE"])-target),"case_control_role":"UNASSIGNED"})
    return enriched,selected

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--a0-pool",type=Path,required=True);ap.add_argument("--ranking-contract",type=Path,required=True)
    ap.add_argument("--gate-amendment",type=Path,required=True);ap.add_argument("--a3-cohort",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);args=ap.parse_args()
    pool=json.loads(args.a0_pool.read_text()); contract=json.loads(args.ranking_contract.read_text()); amendment=json.loads(args.gate_amendment.read_text()); a3=json.loads(args.a3_cohort.read_text())
    for d in (pool,contract,amendment,a3):guards(d)
    assert amendment["decision_timing"]["made_before_primary_meteorological_ranking"] is True
    assert amendment["ranking_contract"]["feature_set_unchanged"]==list(FEATURES)
    assert contract["execution_status"]=="PREREGISTERED_NOT_YET_EXECUTED"
    assert contract["inputs_allowed"]["territorial_outcomes"] is False and contract["inputs_allowed"]["known_event_dates"] is False
    assert contract["normalization"]["scope"]=="WITHIN_TRACK_WITHIN_SEASON" and contract["normalization"]["method"]=="EMPIRICAL_MIDRANK_PERCENTILE"
    assert contract["composite_score"]["formula"]=="MEAN(PCT_P3H_MAX,PCT_P24H_LOCAL,PCT_ANTECEDENT_7D)"
    assert contract["primary_selection"]["minimum_anchor_separation_days"]==9
    if a3["cohort_id"]!="PRIMARY6_CHRONOLOGICAL": raise ValueError("primary ranking requires PRIMARY6_CHRONOLOGICAL")
    if a3["ranking_input_gate"]!="PASS_PRIMARY6_5816_ROWS_RANKING_ALLOWED_NO_UNBLIND_NO_MODELING": raise ValueError("primary6 A3 gate not passed")
    if a3["primary_minimum_complete"] is not True or a3["full_robustness_complete"] is not False: raise ValueError("unexpected cohort completion semantics")
    cohort=amendment["primary_minimum_dataset"]; seasons=list(cohort["season_ids"]); tracks=list(pool["tracks"])
    rows=a3.get("rows");
    if not isinstance(rows,list) or len(rows)!=int(cohort["canonical_track_day_rows"]): raise ValueError("primary6 row count mismatch")
    reject(rows); allowed={"unit_id","season_id","date_local",*FEATURES}
    for i,r in enumerate(rows):
        if set(r)!=allowed: raise ValueError(f"non-preregistered row schema {i}")
    keys=[(r["unit_id"],r["season_id"],r["date_local"]) for r in rows]
    if len(keys)!=len(set(keys)): raise ValueError("duplicate track-season-date")
    if {r["unit_id"] for r in rows}!=set(tracks) or {r["season_id"] for r in rows}!=set(seasons): raise ValueError("cohort track/season set mismatch")
    all_enriched=[]; groups=[]
    for track in tracks:
        for sid in seasons:
            group=[r for r in rows if r["unit_id"]==track and r["season_id"]==sid]
            enriched,selected=select_group(group,contract);all_enriched.extend(enriched);groups.append({"unit_id":track,"season_id":sid,"strata":selected})
    selected_count=sum(1 for r in all_enriched if r["selected"]); unknown_count=sum(1 for r in all_enriched if r["rank_status"]!="KNOWN")
    result={"schema_version":"irfen-ibvf-meteorological-ranking-execution-v0.2","deployment_status":"RESEARCH_ONLY","test_only":True,
      "production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,
      "territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
      "cohort_id":"PRIMARY6_CHRONOLOGICAL","source_a0_pool_sha256":sha_file(args.a0_pool),"source_ranking_contract_sha256":sha_file(args.ranking_contract),
      "source_gate_amendment_sha256":sha_file(args.gate_amendment),"source_a3_cohort_sha256":sha_file(args.a3_cohort),"input_track_day_count":len(rows),
      "selected_primary_window_count":selected_count,"maximum_primary_windows":int(cohort["maximum_primary_ranked_windows"]),"rank_unknown_window_count":unknown_count,
      "sensor_fields_read":False,"territorial_outcome_fields_read":False,"case_control_assignment_performed":False,"all_selected_roles":"UNASSIGNED_BLIND_METEOROLOGICAL_STRATUM",
      "groups":groups,"rows":all_enriched,"rows_canonical_sha256":csha(all_enriched),"selection_canonical_sha256":csha(groups),
      "status":"PRIMARY6_BLIND_METEOROLOGICAL_RANKING_EXECUTED_NO_OUTCOME_NO_CASE_CONTROL_NO_MODELING",
      "next_gate":"FREEZE_A1_A5_REMOTE_FEATURES_FOR_SELECTED_PRIMARY6_WINDOWS_WITHOUT_REPLACING_MISSING_SENSOR_WINDOWS",
      "modeling_allowed":False,"activation_inference_allowed":False}
    guards(result);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"status":result["status"],"rows":len(rows),"selected":selected_count,"unknown":unknown_count,"selection_sha256":result["selection_canonical_sha256"]},indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
