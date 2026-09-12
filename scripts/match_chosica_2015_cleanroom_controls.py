#!/usr/bin/env python3
"""Deterministic clean-room control matching. Reads exactly one blinded JSON package."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
REVEALING_VALUES=("cashahuacra","quirio","pedregal","san_antonio","san antonio","la_libertad","la libertad","carossio","carosio","rayos_de_sol","rayos de sol","corrales","a6680","ingemmet","official_outcome_evidence","damage","severity","post_event","web_search")
FORBIDDEN_KEY_TOKENS=("target_id","target_name","activation","severity","damage","a6680","post_anchor","official_outcome_evidence","web_search")
SAFE_ATTESTATION_KEYS={
    "package_contains_target_names","package_contains_outcome_labels","control_outcome_adjudication_performed",
    "outcomes_used_for_matching","sealed_target_unblind_allowed","package_contains_post_anchor_predictors"
}

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def finite(x): return isinstance(x,(int,float)) and math.isfinite(float(x))

def validate_blind_structure(obj, path="$"):
    """Reject revealing values/keys while allowing explicit false-valued safety attestations."""
    if isinstance(obj,dict):
        for k,v in obj.items():
            kl=str(k).lower()
            if k in SAFE_ATTESTATION_KEYS:
                if v is not False:
                    raise SystemExit(f"FAIL_CLOSED_SAFETY_ATTESTATION_NOT_FALSE {path}.{k}")
            elif any(tok in kl for tok in FORBIDDEN_KEY_TOKENS):
                raise SystemExit(f"FAIL_CLOSED_FORBIDDEN_KEY_IN_CLEANROOM_INPUT {path}.{k}")
            validate_blind_structure(v,f"{path}.{k}")
    elif isinstance(obj,list):
        for i,v in enumerate(obj): validate_blind_structure(v,f"{path}[{i}]")
    elif isinstance(obj,str):
        low=obj.lower()
        bad=[tok for tok in REVEALING_VALUES if tok in low]
        if bad: raise SystemExit(f"FAIL_CLOSED_REVEALING_VALUE_IN_CLEANROOM_INPUT {path} {bad}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    d=json.loads(a.input.read_text(encoding="utf-8")); validate_blind_structure(d)
    if d.get("status")!="PASS_CLEANROOM_INPUT_PACKAGE" or d.get("guards")!=GUARDS: raise SystemExit("FAIL_CLOSED_CLEANROOM_PACKAGE")
    if d.get("sealed_target_unblind_allowed") is not False or d.get("control_outcome_adjudication_performed") is not False: raise SystemExit("FAIL_CLOSED_UNBLIND_OR_ADJUDICATION_FLAG")
    if d.get("package_contains_target_names") is not False or d.get("package_contains_outcome_labels") is not False or d.get("package_contains_post_anchor_predictors") is not False: raise SystemExit("FAIL_CLOSED_PACKAGE_DISCLOSURE_FLAG")
    spec=d["matching_spec"]
    expected_formula="distance_m/10000 + abs(log(area_ratio)) + abs(log(relief_ratio)) + abs(mean_slope_candidate_deg-mean_slope_target_deg)/45"
    if spec.get("formula")!=expected_formula or spec.get("shortlist_per_target")!=3: raise SystemExit("FAIL_CLOSED_MATCHING_SPEC")
    if spec.get("precipitation_used_for_matching") is not False or spec.get("outcomes_used_for_matching") is not False: raise SystemExit("FAIL_CLOSED_MATCHING_FORBIDDEN_VARIABLE")
    targets=d["targets"]; candidates=d["candidates"]
    if len(targets)!=6 or len(candidates)!=29: raise SystemExit("FAIL_CLOSED_DIMENSIONS")
    if len({x["target_code"] for x in targets})!=6 or len({x["candidate_code"] for x in candidates})!=29: raise SystemExit("FAIL_CLOSED_DUPLICATE_CODES")
    required_t=("outlet_x_m","outlet_y_m","area_km2","relief_m","mean_basin_slope_deg")
    required_c=("mainstem_confluence_x_m","mainstem_confluence_y_m","area_km2","relief_m","mean_basin_slope_deg")
    if any(not all(finite(t[k]) for k in required_t) for t in targets): raise SystemExit("FAIL_CLOSED_TARGET_METRICS")
    if any(not all(finite(c[k]) for k in required_c) for c in candidates): raise SystemExit("FAIL_CLOSED_CANDIDATE_METRICS")
    rankings={}; shortlists={}; selected=set()
    for t in sorted(targets,key=lambda x:x["target_code"]):
        rows=[]
        for c in candidates:
            ar=float(c["area_km2"])/float(t["area_km2"]); rr=float(c["relief_m"])/float(t["relief_m"])
            if ar<=0 or rr<=0: raise SystemExit("FAIL_CLOSED_NONPOSITIVE_RATIO")
            dist=math.hypot(float(c["mainstem_confluence_x_m"])-float(t["outlet_x_m"]),float(c["mainstem_confluence_y_m"])-float(t["outlet_y_m"]))
            slope_diff=abs(float(c["mean_basin_slope_deg"])-float(t["mean_basin_slope_deg"]))
            score=dist/10000.0+abs(math.log(ar))+abs(math.log(rr))+slope_diff/45.0
            rows.append({"candidate_code":c["candidate_code"],"score":round(score,12),"distance_m":round(dist,6),"area_ratio":round(ar,12),"relief_ratio":round(rr,12),"mean_slope_abs_diff_deg":round(slope_diff,12)})
        rows.sort(key=lambda x:(x["score"],x["candidate_code"]))
        rankings[t["target_code"]]=rows
        short=rows[:3]; shortlists[t["target_code"]]=short; selected.update(x["candidate_code"] for x in short)
    bycode={x["candidate_code"]:x for x in candidates}
    missing_predictors=sorted(c for c in selected if bycode[c].get("preanchor_windows_if_frozen") is None or bycode[c].get("coverage_fraction_if_frozen")!=1.0)
    out={"schema_version":"0.1","status":"PASS_CLEANROOM_MATCHING" if not missing_predictors else "FAIL_CLOSED_SELECTED_CANDIDATE_WITHOUT_FROZEN_PREANCHOR_PREDICTORS",
         "phase":"CLEANROOM_PREUNBLIND_CONTROL_MATCHING","guards":GUARDS,"cleanroom_input_sha256":sha(a.input),
         "input_count":{"targets":6,"candidates":29},"matching_formula":expected_formula,"shortlist_per_target":3,
         "precipitation_used_for_matching":False,"outcomes_used_for_matching":False,"target_names_read":False,"free_web_search_used":False,
         "control_outcome_adjudication_performed":False,"sealed_target_unblind_performed":False,
         "rankings":rankings,"shortlists":shortlists,"selected_candidate_codes":sorted(selected),
         "selected_candidate_count":len(selected),"selected_without_frozen_preanchor_predictors":missing_predictors,
         "next_gate":"FREEZE_CLEANROOM_PACKAGE_AND_MATCHING" if not missing_predictors else "FAIL_CLOSED_RECONSTRUCT_MISSING_PREANCHOR_PREDICTORS_WITHOUT_OUTCOME_ACCESS"}
    a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"sha256":sha(a.output),"selected_candidate_count":len(selected)},sort_keys=True))
    return 0 if not missing_predictors else 2

if __name__=="__main__": raise SystemExit(main())
