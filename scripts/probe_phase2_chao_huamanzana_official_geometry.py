#!/usr/bin/env python3
"""Freeze exact ANA unit 137712 as one Chao discovery child only."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
DID="lalibertad_chao_huamanzaña_chorobal";CID="huamanzaña_basin_context";CODE="137712";ANA_NAME="Cuenca Huamansaña";DISPLAY_NAME="Cuenca Huamanzaña"
CONTRACT=ROOT/f"site/data/validation/phase2_discovery_contracts/{DID}.json";PACKAGE=ROOT/f"site/data/validation/phase2_discovery_packages/{DID}.json"
SOURCE=ROOT/"site/data/phase2/sources/north_coast_discovery_geometry/ana_lalibertad_huamanzana_137712.geojson";GEOM=ROOT/"site/data/phase2/geometries/lalibertad_huamanzana_basin_context.geojson";VAL=ROOT/"site/data/phase2/geometries/lalibertad_huamanzana_basin_context_validation.json"
ENDPOINT="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class E(RuntimeError):pass
def cb(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def h(p):return sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding="utf-8"))
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(cb(v));return h(p)
def guards(o,label):
 for k,v in SAFE.items():
  if o.get(k)!=v:raise E(f"UNSAFE_{label}_{k}")
def validate(c,p):
 guards(c,"CONTRACT");guards(p,"PACKAGE")
 if c.get("discovery_id")!=DID or p.get("discovery_id")!=DID:raise E("DISCOVERY_ID_DRIFT")
 cp=c.get("component_policy") or {};pp=p.get("parent_policy") or {}
 if cp.get("composite_union_forbidden") is not True or cp.get("parent_is_map_polygon") is not False or pp.get("composite_parent_geometry_forbidden") is not True:raise E("PARENT_COMPOSITE_NOT_FORBIDDEN")
 kids={x["child_id"]:x for x in p.get("hydrologic_children",[])};hu=kids.get(CID);ch=kids.get("chorobal_river_component")
 if not hu or hu.get("ana_unit_code")!=CODE or hu.get("name")!=DISPLAY_NAME:raise E("HUAMANZANA_DISPLAY_IDENTITY_DRIFT")
 ci={x["child_id"]:x for x in (c.get("hydrologic_identity") or {}).get("children",[])}.get(CID) or {}
 if ci.get("ana_unit_code")!=CODE or ci.get("ana_unit_name")!=ANA_NAME or ci.get("display_name")!=DISPLAY_NAME:raise E("HUAMANSANA_OFFICIAL_IDENTITY_DRIFT")
 if not ch or "STANDALONE" not in str(ch.get("promotion_rule","")).upper():raise E("CHOROBAL_PROMOTION_GUARD_MISSING")
 q=(c.get("source_queries") or {}).get(CID) or {};pq=(hu.get("geometry") or {}).get("source_query") or {}
 if q!=pq or q.get("endpoint")!=ENDPOINT or q.get("where")!="CODIGO='137712'":raise E("EXACT_QUERY_DRIFT")
 return kids,q
def fetch(q):
 params={"where":q["where"],"outFields":q.get("out_fields","*"),"returnGeometry":"true","outSR":str(q.get("out_sr",4326)),"geometryPrecision":str(q.get("geometry_precision",7)),"f":q.get("format","geojson")};url=q["endpoint"]+"?"+urlencode(params)
 with urlopen(Request(url,headers={"User-Agent":"IRFEN-RESEARCH-ONLY/0.1"}),timeout=90) as r:return json.loads(r.read().decode()),url
def exact(s):
 fs=s.get("features") or []
 if s.get("type")!="FeatureCollection" or len(fs)!=1:raise E(f"ANA_EXACT_QUERY_NOT_UNIQUE_{len(fs)}")
 f=fs[0];pr=f.get("properties") or {};code=str(pr.get("CODIGO") or pr.get("codigo") or "");name=pr.get("NOMBRE") or pr.get("nombre")
 if code!=CODE or name!=ANA_NAME:raise E(f"ANA_IDENTITY_MISMATCH_{code}_{name}")
 g=f.get("geometry") or {}
 if g.get("type") not in {"Polygon","MultiPolygon"} or not g.get("coordinates"):raise E("ANA_POLYGON_MISSING")
 return f
def norm(f,srcsha):
 props={"unit_id":f"{DID}__{CID}","parent_discovery_id":DID,"component_id":CID,"name":DISPLAY_NAME,"official_name":ANA_NAME,"official_unit_code":CODE,"source_id":"ANA-UH-137712-HUAMANZANA","source_snapshot_sha256":srcsha,"representation":"OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT","context_only":True,"counts_as_event_footprint":False,"counts_as_operational_geometry":False,**SAFE,"alerting_enabled":False}
 return {"type":"FeatureCollection","properties":{**SAFE,"context_only":True,"parent_composite":False,"source_id":"ANA-UH-137712-HUAMANZANA","source_snapshot_sha256":srcsha},"features":[{"type":"Feature","properties":props,"geometry":f["geometry"]}]}
def run(refresh):
 c=load(CONTRACT);p=load(PACKAGE);kids,q=validate(c,p)
 if refresh:s,url=fetch(q);srcsha=dump(SOURCE,s)
 else:
  if not SOURCE.is_file():raise E("FROZEN_SOURCE_MISSING")
  s=load(SOURCE);srcsha=h(SOURCE);url=None
 f=exact(s);gsha=dump(GEOM,norm(f,srcsha))
 v={"schema_version":"0.1","discovery_id":DID,"component_id":CID,"status":"PASS_OFFICIAL_ANA_DISCOVERY_CHILD_GEOMETRY",**SAFE,"ana_unit_code":CODE,"ana_unit_name":ANA_NAME,"display_name":DISPLAY_NAME,"source_id":"ANA-UH-137712-HUAMANZANA","source_path":SOURCE.relative_to(ROOT).as_posix(),"source_sha256":srcsha,"geometry_path":GEOM.relative_to(ROOT).as_posix(),"geometry_sha256":gsha,"request_url":url,"fetched_at_utc":datetime.now(timezone.utc).isoformat() if refresh else None,"outcomes_read":False,"event_footprint_created":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"chorobal_geometry_inferred":False,"parent_composite_created":False};vsha=dump(VAL,v)
 comp={"component_id":CID,"name":DISPLAY_NAME,"source_id":"ANA-UH-137712-HUAMANZANA","hydrologic_identity":{"ana_unit_code":CODE,"ana_unit_name":ANA_NAME,"display_name":DISPLAY_NAME},"source_query":q,"geometry":{"status":"PARTIAL_OFFICIAL_BASIN_CONTEXT","path":GEOM.relative_to(ROOT).as_posix(),"representation":"OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT","sha256":gsha,"validation_path":VAL.relative_to(ROOT).as_posix(),"validation_sha256":vsha,"source_path":SOURCE.relative_to(ROOT).as_posix(),"source_sha256":srcsha,"counts_as_operational_geometry":False,"counts_as_event_footprint":False}}
 c["assets"]["geometry_components"]=[comp];c["contract_status"]="DISCOVERY_CHILD_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY";dump(CONTRACT,c)
 hu=kids[CID];hu["ana_unit_name"]=ANA_NAME;hu["name_aliases"]=[DISPLAY_NAME];hu["geometry"].update(comp["geometry"]);p["contract_status"]="DISCOVERY_PARENT_NON_ACTIVABLE_HUAMANZANA_GEOMETRY_REPRODUCIBLE_CHOROBAL_PENDING";p["geometry_contract_path"]=CONTRACT.relative_to(ROOT).as_posix();dump(PACKAGE,p);return v
def main():
 a=argparse.ArgumentParser();a.add_argument("--refresh-source",action="store_true");x=a.parse_args();r=run(x.refresh_source);print(json.dumps({"status":r["status"],"component_id":CID},sort_keys=True))
if __name__=="__main__":main()
