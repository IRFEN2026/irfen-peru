#!/usr/bin/env python3
"""Match controls from one blinded package only; no network, repo, outcomes or named inputs."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
FORMULA="distance_m/10000 + abs(log(area_ratio)) + abs(log(relief_ratio)) + abs(mean_slope_candidate_deg-mean_slope_target_deg)/45"
FORBIDDEN_VALUE_TOKENS=("cashahuacra","quirio","pedregal","san_antonio","san antonio","la_libertad","la libertad","carossio","carosio","rayos_de_sol","rayos de sol","corrales","a6680","ingemmet","official_outcome_evidence","damage","severity","post_event","web_search")
FORBIDDEN_KEY_TOKENS=("target_id","target_name","activation","severity","damage","a6680","post_anchor","official_outcome_evidence","outcome_label","event_dossier","post_event","web_search")
SAFE_FALSE_KEYS={"package_contains_target_names","package_contains_outcome_labels","package_contains_post_anchor_predictors","control_outcome_adjudication_performed","outcomes_used_for_matching","sealed_target_unblind_allowed","sealed_target_unblind_performed","target_names_read","free_web_search_used","precipitation_used_for_matching"}

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def finite(x): return isinstance(x,(int,float)) and math.isfinite(float(x))

def validate_blind_structure(obj,path="$"):
    if isinstance(obj,dict):
        for k,v in obj.items():
            kl=str(k).lower()
            if k in SAFE_FALSE_KEYS:
                if v is not False: raise SystemExit(f"FAIL_CLOSED_SAFETY_ATTESTATION_NOT_FALSE {path}.{k}")
            elif any(tok in kl for tok in FORBIDDEN_KEY_TOKENS):
                raise SystemExit(f"FAIL_CLOSED_FORBIDDEN_DATA_KEY {path}.{k}")
            validate_blind_structure(v,f"{path}.{k}")
    elif isinstance(obj,list):
        for i,v in enumerate(obj): validate_blind_structure(v,f"{path}[{i}]")
    elif isinstance(obj,str):
        low=obj.lower(); bad=[tok for tok in FORBIDDEN_VALUE_TOKENS if tok in low]
        if bad: raise SystemExit(f"FAIL_CLOSED_REVEALING_STRING_VALUE {path} {bad}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    d=json.loads(a.input.read_text(encoding="utf-8")); validate_blind_structure(d)
    if d.get("status")!="PASS_CLEANROOM_INPUT_PACKAGE" or d.get("guards")!=GUARDS: raise SystemExit("FAIL_CLOSED_PACKAGE")
    if d.get("sealed_target_unblind_allowed") is not False or d.get("control_outcome_adjudication_performed") is not False: raise SystemExit("FAIL_CLOSED_UNBLIND_FLAG")
    if d.get("package_contains_target_names") is not False or d.get("package_contains_outcome_labels") is not False or d.get("package_contains_post_anchor_predictors") is not False: raise SystemExit("FAIL_CLOSED_PACKAGE_DISCLOSURE_FLAG")
    spec=d["matching_spec"]
    if set(spec)!={"shortlist_per_target","formula","tie_break","precipitation_used_for_matching","outcomes_used_for_matching"}: raise SystemExit("FAIL_CLOSED_MATCHING_SPEC_FIELDS")
    if spec.get("formula")!=FORMULA or spec.get("shortlist_per_target")!=3 or spec.get("tie_break")!=["score","candidate_code"] or spec.get("precipitation_used_for_matching") is not False or spec.get("outcomes_used_for_matching") is not False: raise SystemExit("FAIL_CLOSED_MATCHING_SPEC")
    targets=d["targets"]; candidates=d["candidates"]
    if len(targets)!=6 or len(candidates)!=29: raise SystemExit("FAIL_CLOSED_DIMENSIONS")
    if len({x["target_code"] for x in targets})!=6 or len({x["candidate_code"] for x in candidates})!=29: raise SystemExit("FAIL_CLOSED_DUPLICATE_CODES")
    shortlists={}; selected=set()
    for t in sorted(targets,key=lambda x:x["target_code"]):
        rows=[]
        for c in candidates:
            values=[t["outlet_x_m"],t["outlet_y_m"],t["area_km2"],t["relief_m"],t["mean_basin_slope_deg"],c["mainstem_confluence_x_m"],c["mainstem_confluence_y_m"],c["area_km2"],c["relief_m"],c["mean_basin_slope_deg"]]
            if not all(finite(x) for x in values): raise SystemExit("FAIL_CLOSED_NONFINITE")
            ar=float(c["area_km2"])/float(t["area_km2"]); rr=float(c["relief_m"])/float(t["relief_m"])
            if ar<=0 or rr<=0: raise SystemExit("FAIL_CLOSED_NONPOSITIVE_RATIO")
            dist=math.hypot(float(c["mainstem_confluence_x_m"])-float(t["outlet_x_m"]),float(c["mainstem_confluence_y_m"])-float(t["outlet_y_m"]))
            slope=abs(float(c["mean_basin_slope_deg"])-float(t["mean_basin_slope_deg"]))
            score=dist/10000.0+abs(math.log(ar))+abs(math.log(rr))+slope/45.0
            rows.append({"candidate_code":c["candidate_code"],"score":round(score,12),"distance_m":round(dist,6),"area_ratio":round(ar,12),"relief_ratio":round(rr,12),"mean_slope_abs_diff_deg":round(slope,12)})
        rows.sort(key=lambda x:(x["score"],x["candidate_code"])); shortlists[t["target_code"]]=rows[:3]; selected.update(x["candidate_code"] for x in rows[:3])
    bycode={x["candidate_code"]:x for x in candidates}; missing=sorted(c for c in selected if bycode[c].get("preanchor_mm_if_frozen") is None)
    status="PASS_CLEANROOM_MATCHING" if not missing else "FAIL_CLOSED_SELECTED_CANDIDATE_WITHOUT_FROZEN_PREANCHOR_PREDICTORS"
    out={"schema_version":"0.1","status":status,"phase":"CLEANROOM_PREUNBLIND_CONTROL_MATCHING","guards":GUARDS,"cleanroom_input_sha256":sha(a.input),"input_count":{"targets":6,"candidates":29},"matching_formula":FORMULA,"shortlist_per_target":3,"precipitation_used_for_matching":False,"outcomes_used_for_matching":False,"target_names_read":False,"free_web_search_used":False,"control_outcome_adjudication_performed":False,"sealed_target_unblind_performed":False,"shortlists":shortlists,"selected_candidate_codes":sorted(selected),"selected_candidate_count":len(selected),"selected_without_frozen_preanchor_predictors":missing,"next_gate":"FREEZE_CLEANROOM_PACKAGE_AND_MATCHING" if not missing else "STOP_NO_UNBLIND"}
    validate_blind_structure(out)
    a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); print(json.dumps({"status":status,"sha256":sha(a.output),"selected_candidate_count":len(selected)},sort_keys=True)); return 0 if not missing else 2
if __name__=="__main__": raise SystemExit(main())
