#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

FORBIDDEN_EXACT_KEYS = {"territorial_outcome","event_label","case_control_role","activation","damage","incident","risk","alert","priority"}
FORBIDDEN_SOURCE_TOKENS = ("official_outcome","historical_events","shadow_review","shadow_runs","/calibration/","phase2_event_intake","research_events")
EXPECTED_ORDER = ["A2_AREA_KM2","A2_PERIMETER_KM","A2_ELEVATION_MIN_M","A2_ELEVATION_MAX_M","A2_ELEVATION_MEAN_M","A2_ELEVATION_MEDIAN_M","A2_RELIEF_M","A3_P3H_MAX_MM","A3_P24H_LOCAL_MM","A3_ANTECEDENT_7D_MM","A4_S1_MEDIAN_DELTA_DB","A4_S1_IQR_DELTA_DB","A4_S1_DECREASE_FACTOR2_FRACTION","A4_S1_INCREASE_FACTOR2_FRACTION","A4_S1_LARGEST_FACTOR2_CLUSTER_FRACTION","A4_OPTICAL_CHANGE_PRIMARY","SMAP_SOIL_MOISTURE_PRIMARY"]

def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def canon_sha(x): return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
def scan_keys(x,path="$"):
    bad=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if k in FORBIDDEN_EXACT_KEYS: bad.append(f"{path}.{k}")
            bad += scan_keys(v,f"{path}.{k}")
    elif isinstance(x,list):
        for i,v in enumerate(x): bad += scan_keys(v,f"{path}[{i}]")
    return bad

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--a5",required=True); ap.add_argument("--out",required=True); args=ap.parse_args(); a=load(args.a5); failures=[]
    expected_guards={"deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"territorial_activation_evidence_blinded":True}
    for k,v in expected_guards.items():
        if a.get(k)!=v: failures.append(f"guard:{k}")
    for k in ("territorial_outcome_fields_read","known_event_dates_read","case_control_assignment_performed","activation_inference_allowed","risk_classification_computed","alert_value_computed","modeling_allowed","selected_windows_replaced","pairs_reselected","feature_selection_used_observed_magnitude"):
        if a.get(k) is not False: failures.append(f"must_false:{k}")
    if a.get("status")!="PASS_PRIMARY6_A5_ALL_108_FROZEN_WITH_EXPLICIT_UNKNOWN_NO_UNBLIND_NO_MODELING": failures.append("a5_status")
    if a.get("feature_order")!=EXPECTED_ORDER: failures.append("feature_order")
    rows=a.get("rows",[])
    if len(rows)!=108: failures.append(f"row_count:{len(rows)}")
    keys=[(r.get("unit_id"),r.get("season_id"),r.get("date_local")) for r in rows]
    if len(set(keys))!=108: failures.append("duplicate_window_keys")
    if canon_sha(rows)!=a.get("rows_canonical_sha256"): failures.append("rows_hash")
    badkeys=scan_keys(a)
    if badkeys: failures.append("forbidden_exact_keys:"+",".join(badkeys[:10]))
    for p in a.get("source_paths",[]):
        if any(t in p.lower() for t in FORBIDDEN_SOURCE_TOKENS): failures.append(f"forbidden_source:{p}")
    counts={"s1_numeric":0,"s1_unknown":0,"opt_numeric":0,"opt_unknown":0,"smap_null":0}
    for r in rows:
        e=r.get("feature_entries",[])
        if len(e)!=17 or [x.get("id") for x in e]!=EXPECTED_ORDER: failures.append(f"entry_order:{r.get('window_id')}"); continue
        if canon_sha(e)!=r.get("feature_vector_sha256"): failures.append(f"feature_hash:{r.get('window_id')}")
        for x in e:
            if set(x)!={"id","value","status","unit"}: failures.append(f"entry_schema:{r.get('window_id')}:{x.get('id')}")
            if x.get("value")==0 and x.get("status") and any(q in x["status"] for q in ("MISSING","UNKNOWN","DEFERRED")): failures.append(f"zero_imputation:{r.get('window_id')}:{x.get('id')}")
        s=e[10:15]
        if all(x["value"] is not None for x in s): counts["s1_numeric"]+=1
        elif all(x["value"] is None for x in s): counts["s1_unknown"]+=1
        else: failures.append(f"partial_s1_vector:{r.get('window_id')}")
        if e[15]["value"] is None: counts["opt_unknown"]+=1
        else: counts["opt_numeric"]+=1
        if e[16]["value"] is None and "DEFERRED" in e[16]["status"]: counts["smap_null"]+=1
        else: failures.append(f"smap_not_deferred_null:{r.get('window_id')}")
    if counts!={"s1_numeric":71,"s1_unknown":37,"opt_numeric":106,"opt_unknown":2,"smap_null":108}: failures.append(f"availability_counts:{counts}")
    ac=a.get("availability_counts",{})
    if ac!={"s1_numeric":71,"s1_r3_unknown":33,"s1_structural_missing":4,"optical_numeric":106,"optical_unknown":2,"smap_deferred":108}: failures.append(f"upstream_counts:{ac}")
    status="PASS_ANTI_LEAKAGE_AUDIT_TERRITORIAL_UNBLIND_PERMITTED" if not failures else "FAIL_CLOSED_ANTI_LEAKAGE_AUDIT_UNBLIND_FORBIDDEN"
    report={"schema_version":"irfen-ibvf-primary6-a5-antileakage-audit-v0.1","deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"territorial_activation_evidence_blinded":True,"a5_path":args.a5,"a5_file_sha256":hashlib.sha256(Path(args.a5).read_bytes()).hexdigest(),"window_count":len(rows),"feature_count_per_window":17,"observed_availability_counts":counts,"forbidden_outcome_source_paths_read":False,"territorial_outcome_fields_read":False,"case_control_assignment_performed":False,"activation_inference_allowed":False,"modeling_allowed":False,"failures":failures,"status":status,"next_gate":"FIRST_TERRITORIAL_UNBLIND_AND_PREREGISTERED_HYPOTHESIS_TEST" if not failures else "KEEP_TERRITORIAL_EVIDENCE_SEALED"}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True); Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"failures":failures,"counts":counts},sort_keys=True))
    if failures: raise SystemExit(2)
if __name__=="__main__": main()
