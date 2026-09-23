#!/usr/bin/env python3
"""Freeze exact official ANA Cuenca Jequetepeque geometry for discovery/context only."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DISCOVERY_ID="lalibertad_jequetepeque"
CONTRACT=ROOT/"site/data/validation/phase2_discovery_contracts/lalibertad_jequetepeque.json"
PACKAGE=ROOT/"site/data/validation/phase2_discovery_packages/lalibertad_jequetepeque.json"
SOURCE=ROOT/"site/data/phase2/sources/north_coast_discovery_geometry/ana_lalibertad_jequetepeque_13774.geojson"
GEOMETRY=ROOT/"site/data/phase2/geometries/lalibertad_jequetepeque_basin_context.geojson"
VALIDATION=ROOT/"site/data/phase2/geometries/lalibertad_jequetepeque_geometry_validation.json"
APPROVED_ENDPOINT="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class ProbeError(RuntimeError): pass

def canonical_bytes(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def digest_bytes(v): return sha256(v).hexdigest()
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def dump(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); raw=canonical_bytes(v); p.write_bytes(raw); return digest_bytes(raw)
def validate_guards(o,label):
 for k,e in SAFE.items():
  if o.get(k)!=e: raise ProbeError(f"UNSAFE_{label}_{k}")
def validate_inputs(c,p):
 validate_guards(c,"CONTRACT"); validate_guards(p,"PACKAGE")
 if c.get("discovery_id")!=DISCOVERY_ID or p.get("discovery_id")!=DISCOVERY_ID: raise ProbeError("DISCOVERY_ID_MISMATCH")
 ci=c.get("hydrologic_identity") or {}; pi=p.get("hydrologic_identity") or {}; code=str(ci.get("ana_unit_code") or ""); name=ci.get("ana_unit_name")
 if code!="13774" or name!="Cuenca Jequetepeque": raise ProbeError("UNEXPECTED_JEQUETEPEQUE_IDENTITY")
 if str(pi.get("ana_unit_code") or "")!=code or pi.get("ana_unit_name")!=name: raise ProbeError("PACKAGE_CONTRACT_IDENTITY_DRIFT")
 if ci.get("territorial_reference_is_basin") is not False or pi.get("territorial_reference_is_basin") is not False: raise ProbeError("TERRITORIAL_REFERENCE_MUST_NOT_BE_BASIN")
 if pi.get("chepen_is_hydrologic_unit") is not False: raise ProbeError("CHEPEN_MUST_REMAIN_TERRITORIAL")
 q=c.get("source_query") or {}; pq=((p.get("assets") or {}).get("geometry") or {}).get("source_query") or {}
 if q!=pq: raise ProbeError("PACKAGE_CONTRACT_QUERY_DRIFT")
 if q.get("endpoint")!=APPROVED_ENDPOINT or q.get("where")!="CODIGO='13774'": raise ProbeError("QUERY_NOT_LOCKED_TO_EXACT_ANA_UNIT")
 for label,g in (("CONTRACT",c["assets"]["geometry"]),("PACKAGE",p["assets"]["geometry"])):
  if g.get("path")!=GEOMETRY.relative_to(ROOT).as_posix(): raise ProbeError(f"UNEXPECTED_{label}_GEOMETRY_PATH")
  if g.get("counts_as_operational_geometry") is not False or g.get("counts_as_event_footprint") is not False: raise ProbeError(f"UNSAFE_{label}_GEOMETRY_ROLE")
 return code,name,q
def fetch_source(q):
 params={"where":q["where"],"outFields":q.get("out_fields","*"),"returnGeometry":"true","outSR":str(q.get("out_sr",4326)),"geometryPrecision":str(q.get("geometry_precision",7)),"f":q.get("format","geojson")}; url=q["endpoint"]+"?"+urlencode(params)
 with urlopen(Request(url,headers={"User-Agent":"IRFEN-RESEARCH-ONLY/0.1"}),timeout=90) as r: return json.loads(r.read().decode()),url
def validate_source(s,code,name):
 if s.get("type")!="FeatureCollection": raise ProbeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
 fs=s.get("features") or []
 if len(fs)!=1: raise ProbeError(f"ANA_EXACT_CODE_NOT_UNIQUE count={len(fs)}")
 f=fs[0]; props=f.get("properties") or {}; got_code=str(props.get("CODIGO") or props.get("codigo") or ""); got_name=props.get("NOMBRE") or props.get("nombre")
 if got_code!=code: raise ProbeError(f"ANA_CODE_MISMATCH expected={code} got={got_code}")
 if got_name!=name: raise ProbeError(f"ANA_NAME_MISMATCH expected={name!r} got={got_name!r}")
 g=f.get("geometry") or {}
 if g.get("type") not in {"Polygon","MultiPolygon"} or not g.get("coordinates"): raise ProbeError("ANA_GEOMETRY_MISSING_OR_NOT_POLYGON")
 return f
def normalized(f,code,name,source_hash):
 props={"unit_id":DISCOVERY_ID,"name":name,"official_unit_code":code,"source_id":"ANA-UH-13774-JEQUETEPEQUE","source_snapshot_sha256":source_hash,"representation":"OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT","context_only":True,"counts_as_event_footprint":False,"counts_as_operational_geometry":False,**SAFE,"alerting_enabled":False}
 return {"type":"FeatureCollection","properties":{**SAFE,"context_only":True,"source_id":"ANA-UH-13774-JEQUETEPEQUE","source_snapshot_sha256":source_hash},"features":[{"type":"Feature","properties":props,"geometry":f["geometry"]}]}
def run(refresh_source):
 c=load(CONTRACT); p=load(PACKAGE); code,name,q=validate_inputs(c,p)
 if refresh_source:
  source,url=fetch_source(q); source_sha=dump(SOURCE,source)
 else:
  if not SOURCE.is_file(): raise ProbeError("FROZEN_SOURCE_MISSING_USE_REFRESH_SOURCE_ONCE")
  source=load(SOURCE); source_sha=sha256(SOURCE.read_bytes()).hexdigest(); url=None
 f=validate_source(source,code,name); geometry=normalized(f,code,name,source_sha); geometry_sha=dump(GEOMETRY,geometry)
 v={"schema_version":"0.1","discovery_id":DISCOVERY_ID,"status":"PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY",**SAFE,"source_id":"ANA-UH-13774-JEQUETEPEQUE","ana_unit_code":code,"ana_unit_name":name,"source_path":SOURCE.relative_to(ROOT).as_posix(),"source_sha256":source_sha,"geometry_path":GEOMETRY.relative_to(ROOT).as_posix(),"geometry_sha256":geometry_sha,"request_url":url,"fetched_at_utc":datetime.now(timezone.utc).isoformat() if refresh_source else None,"outcomes_read":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"event_footprint_created":False}
 validation_sha=dump(VALIDATION,v)
 for o in (c,p):
  a=o["assets"]["geometry"]; a.update({"status":"PARTIAL_OFFICIAL_BASIN_CONTEXT","representation":"OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT","sha256":geometry_sha,"validation_path":VALIDATION.relative_to(ROOT).as_posix(),"validation_sha256":validation_sha,"source_path":SOURCE.relative_to(ROOT).as_posix(),"source_sha256":source_sha})
 c["contract_status"]="DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"; p["contract_status"]="DISCOVERY_HYDROLOGIC_IDENTITY_AND_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"; p["geometry_contract_path"]=CONTRACT.relative_to(ROOT).as_posix(); dump(CONTRACT,c); dump(PACKAGE,p); return v
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--refresh-source",action="store_true"); a=ap.parse_args(); r=run(a.refresh_source); print(json.dumps({"status":r["status"],"discovery_id":DISCOVERY_ID},sort_keys=True))
if __name__=="__main__": main()
