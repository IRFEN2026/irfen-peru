#!/usr/bin/env python3
"""Freeze the blind Cashahuacra A5 remote/global feature vector.

The schema is value-independent and already frozen in
ibvf_a5_feature_vector_contract.json. This builder only projects previously
frozen A2/A3/A4 evidence into that schema and hashes it. It never reads
territorial outcome evidence or assigns an analytic case/control role.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def load(p:Path)->dict[str,Any]: return json.loads(p.read_text(encoding="utf-8"))
def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->bytes: return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
def csha(x:Any)->str: return hashlib.sha256(canon(x)).hexdigest()
def guard(d:dict[str,Any])->None:
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    if "serious_modeling_gate" in d: assert d["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"
def num(x:Any)->float:
    assert isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x))
    return float(x)

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",type=Path,default=Path(".")); ap.add_argument("--contract",type=Path,default=Path("site/data/validation/ibvf_a5_feature_vector_contract.json")); ap.add_argument("--geometry",type=Path,default=Path("site/data/watersheds/cashahuacra_ibvf_two_point_v03.geojson")); ap.add_argument("--imerg",type=Path,default=Path("site/data/validation/cashahuacra_imerg_basin_features.json")); ap.add_argument("--timebasis",type=Path,default=Path("site/data/validation/cashahuacra_imerg_timebasis_audit.json")); ap.add_argument("--r4",type=Path,default=Path("site/data/validation/cashahuacra_sentinel1_r4.json")); ap.add_argument("--landsat",type=Path,default=Path("site/data/validation/cashahuacra_landsat_aoi_qa.json")); ap.add_argument("--manifest",type=Path,default=Path("site/data/validation/independent_basin_validation_map.json")); ap.add_argument("--output",type=Path,required=True); args=ap.parse_args(); root=args.repo_root.resolve()
    paths={k:root/getattr(args,k) for k in ("contract","geometry","imerg","timebasis","r4","landsat","manifest")}; d={k:load(p) for k,p in paths.items()}
    for k in ("contract","imerg","timebasis","r4","landsat","manifest"): guard(d[k])
    contract=d["contract"]; geom=d["geometry"]; imerg=d["imerg"]; tb=d["timebasis"]; r4=d["r4"]; ls=d["landsat"]; manifest=d["manifest"]
    assert contract["same_schema_for_future_roles"] is True and contract["a5_completion_does_not_open_modeling"] is True and contract["a5_completion_does_not_unblind_outcome"] is True
    assert geom["properties"]["production_use"] is False and geom["properties"]["production_ready"] is False and geom["properties"]["operational_alerting_enabled"] is False
    assert imerg["case_id"]==tb["case_id"]==r4["case_id"]==ls["case_id"]=="cashahuacra_2015-03-23"
    assert imerg["raw_identity"]["match"] is True and imerg["slots"]["attempted"]==imerg["slots"]["valid_basin_rates"]==432 and imerg["slots"]["blocked_or_missing"]==0
    assert tb["event_time_used"] is False and tb["source_raw_identity"]["match"] is True
    assert r4["status"]=="PASS_R4_BLIND_SAR_FEATURE_VECTOR_FROZEN_NO_INFERENCE" and r4["r4_difference_computed"] is True and r4["case_control_role_assigned"] is False and r4["territorial_outcome_fields_read"] is False and r4["activation_inference_allowed"] is False
    assert r4["common_support_fraction"]>=0.95
    assert ls["acceptance_status"].startswith("NOT_FROZEN_") and all(s["interpretation"]=="AOI_QA_DIAGNOSTIC_ONLY_NO_ACCEPTANCE_DECISION" for s in ls["scenes"])
    cases=[c for c in manifest["cases"] if c.get("case_id")=="cashahuacra_2015-03-23"]; assert len(cases)==1; case=cases[0]; assert case["blind_status"]=="TERRITORIAL_EVIDENCE_SEALED"; assert case["smap_status"]=="MISSING_FOR_EVENT_WINDOW"
    gp=geom["properties"]; local=tb["peru_local_calendar_features"]; ant=local["antecedent_ending_local_00"]; sar=r4["primary_r4_feature_vector"]
    values={
      "A2_AREA_KM2":num(gp["area_km2"]),"A2_PERIMETER_KM":num(gp["perimeter_km"]),"A2_ELEVATION_MIN_M":num(gp["elevation_min_m"]),"A2_ELEVATION_MAX_M":num(gp["elevation_max_m"]),"A2_ELEVATION_MEAN_M":num(gp["elevation_mean_m"]),"A2_ELEVATION_MEDIAN_M":num(gp["elevation_median_m"]),"A2_RELIEF_M":num(gp["relief_m"]),
      "A3_P3H_MAX_MM":num(local["p3h_max"]["depth_mm"]),"A3_P24H_LOCAL_MM":num(local["p24h_total_mm"]),"A3_ANTECEDENT_7D_MM":num(ant["p7d_mm"]),
      "A4_S1_MEDIAN_DELTA_DB":num(sar["MEDIAN_DELTA_DB"]),"A4_S1_IQR_DELTA_DB":num(sar["IQR_DELTA_DB"]),"A4_S1_DECREASE_FACTOR2_FRACTION":num(sar["DECREASE_FACTOR2_FRACTION"]),"A4_S1_INCREASE_FACTOR2_FRACTION":num(sar["INCREASE_FACTOR2_FRACTION"]),"A4_S1_LARGEST_FACTOR2_CLUSTER_FRACTION":num(sar["LARGEST_FACTOR2_CLUSTER_FRACTION"]),
      "A4_OPTICAL_CHANGE_PRIMARY":None,"SMAP_SOIL_MOISTURE_PRIMARY":None
    }
    order=contract["feature_order"]; assert set(order)==set(values) and len(order)==len(set(order))
    entries=[]
    for fid in order:
        spec=contract["feature_contract"][fid]; v=values[fid]
        if fid=="A4_OPTICAL_CHANGE_PRIMARY": status="UNKNOWN_OPTICAL_PRIMARY_NOT_FROZEN"
        elif fid=="SMAP_SOIL_MOISTURE_PRIMARY": status="MISSING_FOR_EVENT_WINDOW_NO_IMPUTATION"
        else: status="PASS_FROZEN"
        entries.append({"id":fid,"value":v,"status":status,"unit":spec.get("unit")})
    assert all(e["value"] is not None for e in entries[:15]) and all(e["value"] is None for e in entries[15:])
    forbidden=tuple(x.lower() for x in contract["forbidden_fields"])
    assert not any(any(x in e["id"].lower() for x in forbidden) for e in entries)
    out={
      "schema_version":"irfen-ibvf-cashahuacra-a5-frozen-feature-vector-v0.1","framework":"IRFEN Independent Basin Validation Framework","case_id":"cashahuacra_2015-03-23","window_date":"2015-03-23","deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
      "contract_path":str(args.contract),"contract_sha256":fsha(paths["contract"]),"source_sha256":{k:fsha(paths[k]) for k in ("geometry","imerg","timebasis","r4","landsat","manifest")},
      "feature_entries":entries,"feature_vector_sha256":csha(entries),"numeric_feature_count":15,"explicit_missing_or_unknown_feature_count":2,
      "quality_metadata":{
        "geometry_status":gp["geometry_status"],"morphometry_scope":gp["morphometry_scope"],"geometry_conditioning_dependency":"FLAGGED_RESEARCH_CANDIDATE_NOT_OPERATIONAL",
        "imerg_native_intersecting_cell_count":len(imerg["spatial_contract"]["grid"]["cells"]),"imerg_valid_slot_fraction":imerg["slots"]["valid_basin_rates"]/imerg["slots"]["attempted"],"imerg_time_basis":"America/Lima local calendar UTC-05:00",
        "sentinel1_common_support_fraction":r4["common_support_fraction"],"sentinel1_r4_status":r4["status"],
        "landsat_scene_ids":[s["item_id"] for s in ls["scenes"]],"landsat_aoi_qa_diagnostics":[{"item_id":s["item_id"],"strict_clear_pct_of_data":s["strict_clear_pct_of_data"],"aerosol_valid_retrieval_pct_of_data":s["aerosol_valid_retrieval_pct_of_data"],"interpretation":s["interpretation"]} for s in ls["scenes"]],"landsat_primary_optical_feature_status":"UNKNOWN_NOT_FROZEN_NO_IMPUTATION","smap_status":"MISSING_FOR_EVENT_WINDOW_NO_IMPUTATION"
      },
      "feature_selection_used_observed_magnitude":False,"territorial_outcome_fields_read":False,"known_event_outcome_read":False,"case_control_role_assigned":False,"activation_inference_allowed":False,"risk_classification_computed":False,"alert_value_computed":False,"modeling_allowed":False,
      "a5_status":"PASS_A5_BLIND_FEATURE_VECTOR_HASHED_WITH_EXPLICIT_MISSING_NO_UNBLIND_NO_MODELING","next_gate":"REUSE_IDENTICAL_A5_SCHEMA_FOR_FROZEN_MULTIPISTA_WINDOWS; KEEP ANCHOR OUTCOME SEALED UNTIL BLIND-SAMPLING CONTRACT ALLOWS UNBLINDING; SERIOUS MODELING REMAINS CLOSED"
    }
    guard(out); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"a5_status":out["a5_status"],"feature_vector_sha256":out["feature_vector_sha256"],"numeric_feature_count":out["numeric_feature_count"],"explicit_missing_or_unknown_feature_count":out["explicit_missing_or_unknown_feature_count"],"case_control_role_assigned":out["case_control_role_assigned"],"modeling_allowed":out["modeling_allowed"]},indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
