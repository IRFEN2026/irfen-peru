#!/usr/bin/env python3
"""Bootstrap official ANA Cuenca Grande geometry for Palpa-Changuillo research context.

RESEARCH_ONLY / TEST_ONLY. This probe may only identify an official hydrologic-unit
polygon. It must not infer local ravines, river reaches, outlets, event footprints,
negative controls, hydraulic capacity, thresholds, risk, activation or alerts.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
QUERY_NAME="Cuenca Grande"
CANDIDATE_ID="ica_palpa_changuillo"
GUARDS={
 "deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,
 "production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED",
 "missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,
}

def query_url():
 return BASE+"?"+urlencode({"where":f"NOMBRE='{QUERY_NAME}'","outFields":"*","returnGeometry":"true","outSR":"4326","geometryPrecision":"7","f":"geojson"})
def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def validate(data):
 if data.get("type")!="FeatureCollection" or len(data.get("features") or [])!=1: raise ValueError("expected exactly one official Cuenca Grande feature")
 f=data["features"][0]; p=f.get("properties") or {}
 if p.get("NOMBRE")!=QUERY_NAME: raise ValueError(f"unexpected ANA unit name: {p.get('NOMBRE')!r}")
 code=str(p.get("CODIGO") or "")
 if not code.isdigit(): raise ValueError("official unit code missing or non-numeric")
 area=float(p.get("AREA_KM2") or 0)
 if area<=0: raise ValueError("official unit area missing")
 if (f.get("geometry") or {}).get("type") not in {"Polygon","MultiPolygon"}: raise ValueError("official geometry not polygonal")
 return f

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--source",type=Path,required=True); ap.add_argument("--manifest",type=Path,required=True); a=ap.parse_args()
 req=Request(query_url(),headers={"User-Agent":"IRFEN-research-source-lock/1.0"})
 with urlopen(req,timeout=45) as r: raw=r.read()
 data=json.loads(raw.decode()); f=validate(data); p=f["properties"]; c=canonical(data)
 manifest={"version":"phase2-palpa-changuillo-official-basin-bootstrap-v1",**GUARDS,
  "candidate_id":CANDIDATE_ID,"query_url":query_url(),"official_unit_code":str(p["CODIGO"]),
  "official_unit_name":p["NOMBRE"],"official_area_km2":float(p["AREA_KM2"]),
  "geometry_type":f["geometry"]["type"],"raw_response_sha256":sha(raw),"canonical_source_sha256":sha(c),
  "counts_as_complete_candidate_geometry":False,"artificial_connector_used":False,
  "event_footprint_asserted":False,"hydraulic_capacity_inferred":False,"negative_control_inferred":False,
  "component_scope":"whole official Cuenca Grande only; Palpa/Changuillo local reaches and ravines remain unresolved"}
 for path,payload in ((a.source,data),(a.manifest,manifest)):
  path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(canonical(payload))
 print(json.dumps(manifest,ensure_ascii=False,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
