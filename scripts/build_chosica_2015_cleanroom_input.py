#!/usr/bin/env python3
"""Build a minimal blinded Chosica-2015 clean-room package from allowlisted frozen inputs only."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
REVEALING=("cashahuacra","quirio","pedregal","san_antonio","san antonio","la_libertad","la libertad","carossio","carosio","rayos_de_sol","rayos de sol","corrales","a6680","ingemmet")

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def code(prefix:str, value:str): return prefix+hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
def finite(x): return isinstance(x,(int,float)) and math.isfinite(float(x))

def require_blind_flags(d, candidate=False):
    if d.get("guards")!=GUARDS: raise RuntimeError("FAIL_CLOSED_GUARDS")
    for k in ("outcome_evidence_read","a6680_numeric_reference_read","post_anchor_predictor_read"):
        if d.get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_SOURCE_FLAG {k}")
    if candidate:
        for k in ("candidate_outcome_evidence_read","control_outcome_adjudication_performed"):
            if d.get(k) is not False: raise RuntimeError(f"FAIL_CLOSED_SOURCE_FLAG {k}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--artifact-root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=load(a.contract)
    if co.get("guards")!=GUARDS: raise SystemExit("FAIL_CLOSED_CONTRACT_GUARDS")
    contamination=load(a.repo_root/co["contamination_registry"])
    if contamination.get("status")!="CONTAMINATED_DO_NOT_USE" or contamination.get("guards")!=GUARDS: raise SystemExit("FAIL_CLOSED_CONTAMINATION_TOMBSTONE")
    if contamination["disposition"].get("eligible_for_matching") is not False: raise SystemExit("FAIL_CLOSED_CONTAMINATION_ELIGIBLE")

    repo_docs={}
    for key,spec in co["trusted_repo_inputs"].items():
        p=a.repo_root/spec["path"]
        if sha(p)!=spec["sha256"]: raise SystemExit(f"FAIL_CLOSED_REPO_HASH {key}")
        repo_docs[key]=load(p)
    reg=repo_docs["outlet_freeze_registry"]; pool=repo_docs["candidate_pool"]
    if reg.get("guards")!=GUARDS or reg["batch_gate"].get("unblind_allowed") is not False: raise SystemExit("FAIL_CLOSED_REGISTRY")
    if reg["anti_leakage"].get("outcome_evidence_read") is not False or reg["anti_leakage"].get("a6680_numeric_reference_read") is not False or reg["anti_leakage"].get("post_anchor_predictor_read") is not False: raise SystemExit("FAIL_CLOSED_REGISTRY_LEAKAGE")
    if pool.get("guards")!=GUARDS or pool.get("candidate_pool_frozen") is not True or pool.get("control_outcome_adjudication_performed") is not False or pool.get("candidate_selection_used_observed_2015_response") is not False: raise SystemExit("FAIL_CLOSED_POOL")

    art={}
    for key,spec in co["trusted_frozen_artifacts"].items():
        p=a.artifact_root/key/spec["file_name"]
        if not p.exists(): raise SystemExit(f"FAIL_CLOSED_MISSING_ARTIFACT {key}")
        if sha(p)!=spec["sha256"]: raise SystemExit(f"FAIL_CLOSED_ARTIFACT_HASH {key}")
        art[key]=load(p)
    require_blind_flags(art["target_morphometry"])
    require_blind_flags(art["target_preanchor_imerg"])
    require_blind_flags(art["candidate_dem_metrics"],candidate=True)
    require_blind_flags(art["candidate_preanchor_imerg"],candidate=True)
    if art["target_morphometry"].get("status")!="PASS_CHOSICA_2015_PHASE1_MORPHOMETRY": raise SystemExit("FAIL_CLOSED_MORPH_STATUS")
    if art["target_preanchor_imerg"].get("status")!="PASS_CHOSICA_2015_PREUNBLIND_IMERG_EXTRACTION": raise SystemExit("FAIL_CLOSED_TARGET_IMERG_STATUS")
    if art["candidate_dem_metrics"].get("status")!="PASS_PREUNBLIND_NEGATIVE_CONTROL_DEM_MATCHING": raise SystemExit("FAIL_CLOSED_CANDIDATE_METRICS_STATUS")
    if art["candidate_preanchor_imerg"].get("status")!="PASS_CHOSICA_2015_NEGATIVE_CONTROL_PREUNBLIND_IMERG": raise SystemExit("FAIL_CLOSED_CANDIDATE_IMERG_STATUS")

    morph={x["target_id"]:x for x in art["target_morphometry"]["targets"]}
    precip={x["target_id"]:x for x in art["target_preanchor_imerg"]["targets"]}
    if set(morph)!=set(precip) or len(morph)!=6: raise SystemExit("FAIL_CLOSED_TARGET_ALIGNMENT")
    reg_targets=reg["targets"]
    if set(morph)!=set(reg_targets): raise SystemExit("FAIL_CLOSED_TARGET_REGISTRY_ALIGNMENT")

    targets=[]
    for tid in sorted(morph):
        m=morph[tid]; p=precip[tid]; r=reg_targets[tid]
        vals={k:m[k] for k in ("area_km2","perimeter_km","elevation_min_m","elevation_max_m","relief_m","main_channel_length_m","mean_basin_slope_deg","median_basin_slope_deg","p90_basin_slope_deg","drainage_density_km_per_km2")}
        if not all(finite(v) for v in vals.values()): raise SystemExit("FAIL_CLOSED_TARGET_NONFINITE")
        if p.get("coverage_fraction")!=1.0 or p.get("valid_slot_count")!=p.get("slot_count"): raise SystemExit("FAIL_CLOSED_TARGET_PRECIP_COVERAGE")
        geom=m["geometry_geojson_sha256"]; outlet=r["accepted_outlet"]
        targets.append({"target_code":code("T_",geom),"geometry_sha256":geom,"outlet_x_m":outlet["x_m"],"outlet_y_m":outlet["y_m"],**vals,
                        "preanchor_windows":p["windows"],"coverage_fraction":p["coverage_fraction"]})

    pool_by_id={x["candidate_id"]:x for x in pool["candidates"]}
    metrics={x["candidate_id"]:x for x in art["candidate_dem_metrics"]["candidate_metrics"]}
    if set(pool_by_id)!=set(metrics) or len(metrics)!=29: raise SystemExit("FAIL_CLOSED_CANDIDATE_ALIGNMENT")
    frozen_precip={x["candidate_id"]:x for x in art["candidate_preanchor_imerg"]["candidates"]}
    if len(frozen_precip)!=7: raise SystemExit("FAIL_CLOSED_FROZEN_CANDIDATE_PRECIP_COUNT")
    candidates=[]
    for cid in sorted(metrics):
        m=metrics[cid]; q=pool_by_id[cid]
        if m.get("eligible_for_matching") is not True: raise SystemExit("FAIL_CLOSED_PREINCIDENT_INELIGIBLE_CANDIDATE")
        vals={k:m[k] for k in ("area_km2","elevation_min_m","elevation_max_m","relief_m","mean_basin_slope_deg","mainstem_confluence_x_m","mainstem_confluence_y_m")}
        if not all(finite(v) for v in vals.values()): raise SystemExit("FAIL_CLOSED_CANDIDATE_NONFINITE")
        fp=q["feeder_cell"]
        out={"candidate_code":code("C_",cid),"feeder_x_m":fp["x_m"],"feeder_y_m":fp["y_m"],**vals}
        if cid in frozen_precip:
            pp=frozen_precip[cid]
            if pp.get("coverage_fraction")!=1.0 or pp.get("valid_slot_count")!=pp.get("slot_count"): raise SystemExit("FAIL_CLOSED_CANDIDATE_PRECIP_COVERAGE")
            out["preanchor_windows_if_frozen"]=pp["windows"]; out["coverage_fraction_if_frozen"]=pp["coverage_fraction"]
        else:
            out["preanchor_windows_if_frozen"]=None; out["coverage_fraction_if_frozen"]=None
        candidates.append(out)

    package={
      "schema_version":"0.1","status":"PASS_CLEANROOM_INPUT_PACKAGE","phase":"CLEANROOM_PREUNBLIND_RECOVERY",
      "guards":GUARDS,"sealed_target_unblind_allowed":False,"control_outcome_adjudication_performed":False,
      "package_contains_target_names":False,"package_contains_outcome_labels":False,"package_contains_post_anchor_predictors":False,
      "anchor_utc":art["target_preanchor_imerg"]["anchor_utc"],
      "source_integrity":{
        "contract_sha256":sha(a.contract),
        "outlet_registry_sha256":co["trusted_repo_inputs"]["outlet_freeze_registry"]["sha256"],
        "candidate_pool_sha256":co["trusted_repo_inputs"]["candidate_pool"]["sha256"],
        "target_morphometry_sha256":co["trusted_frozen_artifacts"]["target_morphometry"]["sha256"],
        "target_preanchor_imerg_sha256":co["trusted_frozen_artifacts"]["target_preanchor_imerg"]["sha256"],
        "candidate_dem_metrics_sha256":co["trusted_frozen_artifacts"]["candidate_dem_metrics"]["sha256"],
        "candidate_preanchor_imerg_sha256":co["trusted_frozen_artifacts"]["candidate_preanchor_imerg"]["sha256"]},
      "matching_spec":co["matching"],"targets":targets,"candidates":candidates
    }
    text=json.dumps(package,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"
    low=text.lower()
    if any(token in low for token in REVEALING): raise SystemExit("FAIL_CLOSED_REVEALING_NAME_IN_PACKAGE")
    for token in ("official_outcome_evidence","damage","severity","post_event","web_search"):
        if token in low: raise SystemExit(f"FAIL_CLOSED_FORBIDDEN_TOKEN_IN_PACKAGE {token}")
    a.output.write_text(text,encoding="utf-8")
    print(json.dumps({"status":"PASS_CLEANROOM_INPUT_PACKAGE","sha256":sha(a.output),"target_count":len(targets),"candidate_count":len(candidates),"frozen_candidate_predictor_count":sum(x["preanchor_windows_if_frozen"] is not None for x in candidates)},sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
