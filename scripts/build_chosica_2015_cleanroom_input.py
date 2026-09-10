#!/usr/bin/env python3
"""Build a minimal blinded clean-room package from allowlisted preincident frozen artifacts."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def pseudonym(prefix:str,value:str): return prefix+hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
def finite(x): return isinstance(x,(int,float)) and math.isfinite(float(x))

def blind_flags(d,candidate=False):
    if d.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
    for k in ("outcome_evidence_read","a6680_numeric_reference_read","post_anchor_predictor_read"):
        if d.get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_SOURCE_FLAG_{k}")
    if candidate:
        for k in ("candidate_outcome_evidence_read","control_outcome_adjudication_performed"):
            if d.get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_SOURCE_FLAG_{k}")

def outlet_center(m):
    tr=m["semantic_dem_metadata"]["transform"]; row=m["outlet_grid_cell"]["row"]; col=m["outlet_grid_cell"]["col"]
    if len(tr)!=6: raise RuntimeError("FAIL_CLOSED_BAD_AFFINE")
    x=float(tr[2])+float(tr[0])*(float(col)+0.5)+float(tr[1])*(float(row)+0.5)
    y=float(tr[5])+float(tr[3])*(float(col)+0.5)+float(tr[4])*(float(row)+0.5)
    if not finite(x) or not finite(y): raise RuntimeError("FAIL_CLOSED_BAD_OUTLET_CENTER")
    return round(x,6),round(y,6)

def window_vector(rec):
    if rec.get("coverage_fraction")!=1.0 or rec.get("valid_slot_count")!=rec.get("slot_count"): raise RuntimeError("FAIL_CLOSED_PRECIP_COVERAGE")
    w=rec["windows"]; required={"trigger_0_5h","trigger_1h","trigger_3h","trigger_6h","trigger_24h","antecedent_72h","antecedent_168h","antecedent_360h"}
    if set(w)!=required: raise RuntimeError("FAIL_CLOSED_WINDOW_SET")
    out={}
    for k in sorted(required):
        x=w[k]
        if x.get("complete") is not True or not finite(x.get("accum_mm")): raise RuntimeError("FAIL_CLOSED_WINDOW_INCOMPLETE")
        out[k]=float(x["accum_mm"])
    return out

def validate_blind_structure(obj, rules, path="$"):
    value_tokens=tuple(str(x).lower() for x in rules["forbidden_string_value_tokens"])
    key_tokens=tuple(str(x).lower() for x in rules["forbidden_data_key_tokens"])
    safe_false=set(rules["safe_false_attestation_keys"])
    if isinstance(obj,dict):
        for k,v in obj.items():
            kl=str(k).lower()
            if k in safe_false:
                if v is not False: raise RuntimeError(f"FAIL_CLOSED_SAFETY_ATTESTATION_NOT_FALSE {path}.{k}")
            elif any(tok in kl for tok in key_tokens):
                raise RuntimeError(f"FAIL_CLOSED_FORBIDDEN_DATA_KEY {path}.{k}")
            validate_blind_structure(v,rules,f"{path}.{k}")
    elif isinstance(obj,list):
        for i,v in enumerate(obj): validate_blind_structure(v,rules,f"{path}[{i}]")
    elif isinstance(obj,str):
        low=obj.lower(); bad=[tok for tok in value_tokens if tok in low]
        if bad: raise RuntimeError(f"FAIL_CLOSED_REVEALING_STRING_VALUE {path} {bad}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--contract",type=Path,required=True); ap.add_argument("--contamination",type=Path,required=True); ap.add_argument("--artifact-root",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=load(a.contract); contam=load(a.contamination)
    if co.get("guards")!=GUARDS or contam.get("guards")!=GUARDS or contam.get("status")!="CONTAMINATED_DO_NOT_USE": raise SystemExit("FAIL_CLOSED_RECOVERY_POLICY")
    rev=co.get("guard_revision") or {}
    if rev.get("scientific_inputs_changed") is not False or rev.get("matching_semantics_changed") is not False or any(rev.get(k) is not False for k in ("outcome_information_used","a6680_information_used","post_anchor_information_used")): raise SystemExit("FAIL_CLOSED_UNSAFE_GUARD_REVISION")
    for k in ("eligible_for_matching","eligible_for_calibration","eligible_for_validation","eligible_for_control_label","eligible_for_unblind_gate"):
        if contam["disposition"].get(k) is not False: raise SystemExit("FAIL_CLOSED_CONTAMINATION_ELIGIBLE")
    art={}
    for key,spec in co["trusted_frozen_artifacts"].items():
        p=a.artifact_root/key/spec["file_name"]
        if not p.exists() or sha(p)!=spec["sha256"]: raise SystemExit(f"FAIL_CLOSED_ARTIFACT_INTEGRITY_{key}")
        art[key]=load(p)
    blind_flags(art["target_morphometry"]); blind_flags(art["target_preanchor_imerg"]); blind_flags(art["candidate_dem_metrics"],True); blind_flags(art["candidate_preanchor_imerg"],True)
    if art["target_morphometry"].get("status")!="PASS_CHOSICA_2015_PHASE1_MORPHOMETRY": raise SystemExit("FAIL_CLOSED_MORPH_STATUS")
    if art["target_preanchor_imerg"].get("status")!="PASS_CHOSICA_2015_PREUNBLIND_IMERG_EXTRACTION": raise SystemExit("FAIL_CLOSED_TARGET_IMERG_STATUS")
    if art["candidate_dem_metrics"].get("status")!="PASS_PREUNBLIND_NEGATIVE_CONTROL_DEM_MATCHING": raise SystemExit("FAIL_CLOSED_CANDIDATE_METRIC_STATUS")
    if art["candidate_preanchor_imerg"].get("status")!="PASS_CHOSICA_2015_NEGATIVE_CONTROL_PREUNBLIND_IMERG": raise SystemExit("FAIL_CLOSED_CANDIDATE_IMERG_STATUS")
    morph={x["target_id"]:x for x in art["target_morphometry"]["targets"]}; precip={x["target_id"]:x for x in art["target_preanchor_imerg"]["targets"]}
    if set(morph)!=set(precip) or len(morph)!=6: raise SystemExit("FAIL_CLOSED_TARGET_ALIGNMENT")
    targets=[]
    for tid in sorted(morph):
        m=morph[tid]; p=precip[tid]; geom=m["geometry_geojson_sha256"]; ox,oy=outlet_center(m)
        vals={k:float(m[k]) for k in ("area_km2","perimeter_km","elevation_min_m","elevation_max_m","relief_m","main_channel_length_m","mean_basin_slope_deg","median_basin_slope_deg","p90_basin_slope_deg","drainage_density_km_per_km2")}
        if not all(finite(v) for v in vals.values()): raise SystemExit("FAIL_CLOSED_TARGET_NONFINITE")
        targets.append({"target_code":pseudonym("T_",geom),"geometry_sha256":geom,"outlet_x_m":ox,"outlet_y_m":oy,**vals,"preanchor_mm":window_vector(p)})
    metrics={x["candidate_id"]:x for x in art["candidate_dem_metrics"]["candidate_metrics"]}; cprecip={x["candidate_id"]:x for x in art["candidate_preanchor_imerg"]["candidates"]}
    if len(metrics)!=29 or len(cprecip)!=7 or not set(cprecip).issubset(metrics): raise SystemExit("FAIL_CLOSED_CANDIDATE_ALIGNMENT")
    candidates=[]
    for cid in sorted(metrics):
        m=metrics[cid]
        if m.get("eligible_for_matching") is not True or m.get("contains_frozen_target_outlet_ids") not in ([],None): raise SystemExit("FAIL_CLOSED_CANDIDATE_ELIGIBILITY")
        vals={k:float(m[k]) for k in ("area_km2","elevation_min_m","elevation_max_m","relief_m","mean_basin_slope_deg","mainstem_confluence_x_m","mainstem_confluence_y_m")}
        if not all(finite(v) for v in vals.values()): raise SystemExit("FAIL_CLOSED_CANDIDATE_NONFINITE")
        candidates.append({"candidate_code":pseudonym("C_",cid),**vals,"preanchor_mm_if_frozen":window_vector(cprecip[cid]) if cid in cprecip else None})
    ms=co["matching"]
    matching_spec={"shortlist_per_target":ms["shortlist_per_target"],"formula":ms["formula"],"tie_break":ms["tie_break"],"precipitation_used_for_matching":ms["precipitation_used_for_matching"],"outcomes_used_for_matching":ms["outcomes_used_for_matching"]}
    package={"schema_version":"0.1","status":"PASS_CLEANROOM_INPUT_PACKAGE","phase":"CLEANROOM_PREUNBLIND_RECOVERY","guards":GUARDS,"sealed_target_unblind_allowed":False,"control_outcome_adjudication_performed":False,"package_contains_target_names":False,"package_contains_outcome_labels":False,"package_contains_post_anchor_predictors":False,"anchor_utc":art["target_preanchor_imerg"]["anchor_utc"],"source_integrity":{"contract_sha256":sha(a.contract),"target_morphometry_sha256":co["trusted_frozen_artifacts"]["target_morphometry"]["sha256"],"target_preanchor_imerg_sha256":co["trusted_frozen_artifacts"]["target_preanchor_imerg"]["sha256"],"candidate_dem_metrics_sha256":co["trusted_frozen_artifacts"]["candidate_dem_metrics"]["sha256"],"candidate_preanchor_imerg_sha256":co["trusted_frozen_artifacts"]["candidate_preanchor_imerg"]["sha256"]},"matching_spec":matching_spec,"targets":targets,"candidates":candidates}
    try: validate_blind_structure(package,co["hard_fail_closed"])
    except RuntimeError as e: raise SystemExit(str(e))
    a.output.write_text(json.dumps(package,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS_CLEANROOM_INPUT_PACKAGE","sha256":sha(a.output),"target_count":6,"candidate_count":29,"candidate_predictor_count":7},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
