#!/usr/bin/env python3
"""Fail-closed replay verification for frozen ANA Jicamarca parent context."""
from __future__ import annotations
import json
from hashlib import sha256
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_jicamarca_parent_geometry_v0_1.json"
DISC=ROOT/"config/phase2_jicamarca_discovery_v0_1.json"
ZONE=ROOT/"site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class VerifyError(RuntimeError): pass

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def digest(p): return sha256(p.read_bytes()).hexdigest()
def guards(o,label):
 for k,e in SAFE.items():
  if o.get(k)!=e: raise VerifyError(f"UNSAFE_{label}_{k}")

def main():
 cfg=load(CFG); disc=load(DISC); zone=load(ZONE); guards(cfg,"CONFIG"); guards(disc,"DISCOVERY")
 out=cfg["output"]; sp=ROOT/out["source_snapshot"]; gp=ROOT/out["normalized_geometry"]; vp=ROOT/out["validation"]
 for p in (sp,gp,vp):
  if not p.is_file(): raise VerifyError(f"MISSING_FROZEN_ARTIFACT {p}")
 val=load(vp); guards(val,"VALIDATION")
 if val.get("status")!="PASS_EXACT_ANA_JICAMARCA_PARENT_CONTEXT": raise VerifyError("VALIDATION_STATUS")
 if val.get("official_unit_code")!="1375542": raise VerifyError("UNIT_CODE")
 if val.get("source_sha256")!=digest(sp) or val.get("geometry_sha256")!=digest(gp): raise VerifyError("HASH_DRIFT")
 if val.get("parent_context_only") is not True or val.get("local_activation_geometry") is not False: raise VerifyError("PARENT_ROLE_DRIFT")
 for k in ("child_geometry_inferred","confluence_inferred","routing_inferred","outcomes_read","rainfall_read","hydraulic_capacity_read","thresholds_used","negative_controls_read","approximate_geometry_used","event_footprint_created"):
  if val.get(k) is not False: raise VerifyError(f"UNSAFE_VALIDATION_{k}")
 src=load(sp); fs=src.get("features") or []
 if len(fs)!=1: raise VerifyError("SOURCE_NOT_UNIQUE")
 props=fs[0].get("properties") or {}; exp=cfg.get("expected_response") or {}
 if str(props.get(exp.get("code_field","NIVEL7")) or "")!="1375542": raise VerifyError("SOURCE_LEVEL7_CODE_DRIFT")
 names=[str(props.get(k) or "") for k in exp.get("name_fields",["NOMB_UH_N7","NOMBRE"])]
 if not any("jicamarca" in n.lower() for n in names): raise VerifyError("SOURCE_NAME_DRIFT")
 try: area=float(props.get(exp.get("area_field","AREA_KM2")))
 except (TypeError,ValueError): raise VerifyError("SOURCE_AREA_MISSING")
 if abs(area-float(exp.get("area_km2",492.31)))>float(exp.get("area_tolerance_km2",1.0)): raise VerifyError("SOURCE_AREA_DRIFT")
 geo=load(gp); guards(geo.get("properties") or {},"GEOJSON")
 feats=geo.get("features") or []
 if len(feats)!=1: raise VerifyError("GEOMETRY_FEATURE_COUNT")
 fp=feats[0].get("properties") or {}; guards(fp,"GEOMETRY_FEATURE")
 if fp.get("official_unit_code")!="1375542" or fp.get("context_only") is not True or fp.get("local_activation_geometry") is not False: raise VerifyError("GEOMETRY_ROLE")
 if fp.get("source_snapshot_sha256")!=digest(sp): raise VerifyError("GEOMETRY_SOURCE_HASH")
 ref=disc.get("parent_context_geometry") or {}
 if ref.get("path")!=out["normalized_geometry"] or ref.get("sha256")!=digest(gp): raise VerifyError("DISCOVERY_GEOMETRY_BINDING")
 if ref.get("local_activation_geometry") is not False or ref.get("counts_as_event_footprint") is not False or ref.get("counts_as_operational_geometry") is not False: raise VerifyError("DISCOVERY_ROLE")
 if (disc.get("hierarchy_binding") or {}).get("candidate_inventory_registration") is not False: raise VerifyError("DISCOVERY_REGISTRATION_DRIFT")
 lid=out["map_layer_id"]; layers=((zone.get("assets") or {}).get("geometry") or {}).get("component_layers") or []; hits=[x for x in layers if x.get("layer_id")==lid]
 if len(hits)!=1: raise VerifyError("ZONE_COMPONENT_BINDING")
 layer=hits[0]
 if layer.get("path")!=out["normalized_geometry"] or layer.get("counts_as_complete_candidate_geometry") is not False or layer.get("candidate_wide_sampling_ready") is not False: raise VerifyError("ZONE_COMPONENT_ROLE")
 print(json.dumps({"status":"PASS_REPLAY_JICAMARCA_PARENT_CONTEXT","geometry_sha256":digest(gp)},sort_keys=True))

if __name__=="__main__": main()
