#!/usr/bin/env python3
"""Freeze exact ANA Pfafstetter 1375542 as Jicamarca parent context only.

This never derives child catchments, outlets, confluences, routing or activation states.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_jicamarca_parent_geometry_v0_1.json"
DISC=ROOT/"config/phase2_jicamarca_discovery_v0_1.json"
ZONE=ROOT/"site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class ProbeError(RuntimeError): pass

def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def digest_bytes(v): return sha256(v).hexdigest()
def digest_path(p): return sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def dump(p,v): p.parent.mkdir(parents=True,exist_ok=True); raw=canonical(v); p.write_bytes(raw); return digest_bytes(raw)
def guards(o,label):
 for k,e in SAFE.items():
  if o.get(k)!=e: raise ProbeError(f"UNSAFE_{label}_{k}")
def paths(cfg):
 out=cfg["output"]
 return ROOT/out["source_snapshot"],ROOT/out["normalized_geometry"],ROOT/out["validation"]

def validate_contracts(cfg,disc,zone):
 guards(cfg,"GEOMETRY_CONTRACT"); guards(disc,"DISCOVERY")
 if zone.get("deployment_status")!="RESEARCH_ONLY" or zone.get("test_mode")!="TEST_ONLY": raise ProbeError("UNSAFE_ZONE")
 for k in ("production_use","production_ready","operational_alerting_enabled"):
  if zone.get(k) is not False: raise ProbeError(f"UNSAFE_ZONE_{k}")
 if zone.get("activation_gate")!="BLOCKED" or zone.get("missing_data_rule")!="UNKNOWN_NOT_LOW_RISK": raise ProbeError("UNSAFE_ZONE_GATE")
 if zone.get("decision_thresholds") is not None or zone.get("hydraulic_factors") is not None: raise ProbeError("UNSAFE_ZONE_NUMERIC_GUARDS")
 ident=cfg["official_identity"]; q=cfg["source_query"]; role=cfg["scientific_role"]
 if ident.get("unit_code")!="1375542" or ident.get("pfafstetter_level")!=7: raise ProbeError("IDENTITY_NOT_LOCKED")
 if q.get("endpoint")!="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/7/query" or q.get("where")!="CODIGO='1375542'": raise ProbeError("QUERY_NOT_EXACT")
 required={"parent_context_only":True,"local_activation_geometry":False,"counts_as_complete_candidate_geometry":False,"candidate_wide_sampling_ready":False,"counts_as_event_footprint":False,"counts_as_operational_geometry":False,"child_geometry_inferred":False,"confluence_inferred":False,"routing_inferred":False}
 for k,e in required.items():
  if role.get(k)!=e: raise ProbeError(f"UNSAFE_ROLE_{k}")
 if (disc.get("hierarchy_binding") or {}).get("candidate_inventory_registration") is not False: raise ProbeError("DISCOVERY_MUST_REMAIN_UNREGISTERED")
 if (disc.get("territorial_identity") or {}).get("jicamarca_is_single_hydrologic_unit") is not False: raise ProbeError("SYNTHETIC_JICAMARCA_FORBIDDEN")
 return ident,q

def fetch(q):
 params={"where":q["where"],"outFields":q.get("out_fields","*"),"returnGeometry":"true","outSR":str(q.get("out_sr",4326)),"geometryPrecision":str(q.get("geometry_precision",7)),"f":q.get("format","geojson")}
 url=q["endpoint"]+"?"+urlencode(params)
 with urlopen(Request(url,headers={"User-Agent":"IRFEN-RESEARCH-ONLY/0.1"}),timeout=90) as r: return json.loads(r.read().decode()),url

def validate_source(src,cfg):
 if src.get("type")!="FeatureCollection": raise ProbeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
 fs=src.get("features") or []; exp=cfg["expected_response"]
 if len(fs)!=exp["feature_count"]: raise ProbeError(f"ANA_EXACT_CODE_NOT_UNIQUE count={len(fs)}")
 f=fs[0]; p=f.get("properties") or {}; code=str(p.get("CODIGO") or p.get("codigo") or ""); name=str(p.get("NOMBRE") or p.get("nombre") or "")
 if code!=exp["code"]: raise ProbeError(f"ANA_CODE_MISMATCH {code}")
 if exp["name_must_contain"].lower() not in name.lower(): raise ProbeError(f"ANA_NAME_MISMATCH {name!r}")
 g=f.get("geometry") or {}
 if g.get("type") not in set(exp["geometry_types"]) or not g.get("coordinates"): raise ProbeError("ANA_GEOMETRY_MISSING_OR_NOT_POLYGON")
 return f,name,p.get("AREA_KM2") or p.get("area_km2")

def normalized(f,name,source_sha):
 props={"unit_id":"jicamarca_parent_subbasin_context","name":name,"official_unit_code":"1375542","parent_candidate_id":"lima_este_santa_eulalia_rimac","source_id":"ANA-UH-1375542-JICAMARCA","source_snapshot_sha256":source_sha,"representation":"OFFICIAL_ANA_PFAFSTETTER_PARENT_CONTEXT","context_only":True,"local_activation_geometry":False,"counts_as_event_footprint":False,"counts_as_operational_geometry":False,"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
 return {"type":"FeatureCollection","properties":{"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,"context_only":True,"local_activation_geometry":False,"source_id":"ANA-UH-1375542-JICAMARCA","source_snapshot_sha256":source_sha},"features":[{"type":"Feature","properties":props,"geometry":f["geometry"]}]}

def bind(cfg,disc,zone,geom_sha,val_rel,val_sha,source_rel,source_sha,name):
 ref={"status":"REPRODUCIBLE_OFFICIAL_PARENT_CONTEXT","path":cfg["output"]["normalized_geometry"],"sha256":geom_sha,"validation_path":val_rel,"validation_sha256":val_sha,"source_path":source_rel,"source_sha256":source_sha,"source_ids":["ANA-UH-1375542-JICAMARCA"],"representation":"OFFICIAL_ANA_PFAFSTETTER_PARENT_CONTEXT","context_only":True,"local_activation_geometry":False,"counts_as_event_footprint":False,"counts_as_operational_geometry":False}
 disc["parent_context_geometry"]=ref
 disc["territorial_identity"]["official_parent_subbasin_code"]="1375542"
 disc["territorial_identity"]["official_parent_subbasin_name"]=name
 geom=zone["assets"]["geometry"]; layers=geom.setdefault("component_layers",[]); lid=cfg["output"]["map_layer_id"]
 layer={"layer_id":lid,"title":"Jicamarca · subcuenca ANA padre (contexto)","deployment_status":"RESEARCH_ONLY","path":cfg["output"]["normalized_geometry"],"source_ids":["ANA-UH-1375542-JICAMARCA"],"validation_path":val_rel,"representation":"OFFICIAL_ANA_PFAFSTETTER_PARENT_CONTEXT","confidence":"OFFICIAL_EXACT_CODE_PARENT_CONTEXT_ONLY","default_visibility":False,"counts_as_complete_candidate_geometry":False,"candidate_wide_sampling_ready":False,"map_disclaimer":"Subcuenca ANA 1375542 en gris/contexto RESEARCH_ONLY. No es una unidad local activada, riesgo, alerta, footprint de evento, geometría de hijos ni capacidad hidráulica."}
 existing=[x for x in layers if x.get("layer_id")==lid]
 if existing and existing[0]!=layer: raise ProbeError("EXISTING_MAP_LAYER_DRIFT")
 if not existing: layers.append(layer)

def run(refresh):
 cfg=load(CFG); disc=load(DISC); zone=load(ZONE); ident,q=validate_contracts(cfg,disc,zone); source_p,geom_p,val_p=paths(cfg)
 if refresh:
  src,url=fetch(q); source_sha=dump(source_p,src)
 else:
  if not source_p.is_file(): raise ProbeError("FROZEN_SOURCE_MISSING_USE_REFRESH_SOURCE_ONCE")
  src=load(source_p); source_sha=digest_path(source_p); url=None
 f,name,provider_area=validate_source(src,cfg); geo=normalized(f,name,source_sha); geom_sha=dump(geom_p,geo)
 val={"schema_version":"0.1","status":"PASS_EXACT_ANA_JICAMARCA_PARENT_CONTEXT","deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,"official_unit_code":"1375542","official_unit_name":name,"provider_area_km2":provider_area,"documentary_area_km2":ident["documentary_area_km2"],"source_path":source_p.relative_to(ROOT).as_posix(),"source_sha256":source_sha,"geometry_path":geom_p.relative_to(ROOT).as_posix(),"geometry_sha256":geom_sha,"request_url":url,"fetched_at_utc":datetime.now(timezone.utc).isoformat() if refresh else None,"parent_context_only":True,"local_activation_geometry":False,"child_geometry_inferred":False,"confluence_inferred":False,"routing_inferred":False,"outcomes_read":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"event_footprint_created":False}
 val_sha=dump(val_p,val); bind(cfg,disc,zone,geom_sha,val_p.relative_to(ROOT).as_posix(),val_sha,source_p.relative_to(ROOT).as_posix(),source_sha,name); dump(DISC,disc); dump(ZONE,zone)
 print(json.dumps({"status":val["status"],"official_unit_code":"1375542","name":name},ensure_ascii=False,sort_keys=True))

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--refresh-source",action="store_true"); a=ap.parse_args(); run(a.refresh_source)
if __name__=="__main__": main()
