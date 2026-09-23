#!/usr/bin/env python3
"""Probe official ANA IDEP hydrologic-unit geometry for code 1377722 (La Leche).

RESEARCH_ONLY / TEST_ONLY. This bounded discovery probe queries only the exact ANA
hydrologic-unit code already supported by official context. A successful polygon can
be interpreted only according to the unit identity returned by ANA. It must not infer
an event footprint, outlet, hydraulic capacity, threshold, negative control, risk,
activation state, alert, Pítipo polygon, or artificial Motupe/La Leche connector.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LAYER="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
EXPECTED_CODE="1377722"
CANDIDATE_ID="lambayeque_motupe_la_leche_pitipo"
GUARDS={
 "deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,
 "production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED",
 "missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,
}

def query_url():
 return LAYER+"?"+urlencode({
  "where":f"CODIGO='{EXPECTED_CODE}'","outFields":"*","returnGeometry":"true",
  "outSR":"4326","geometryPrecision":"7","f":"geojson"})

def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--response",type=Path,required=True); ap.add_argument("--manifest",type=Path,required=True); a=ap.parse_args()
 req=Request(query_url(),headers={"User-Agent":"IRFEN-research-source-lock/1.0"})
 with urlopen(req,timeout=45) as r: raw=r.read()
 data=json.loads(raw.decode("utf-8"))
 if data.get("error"): raise SystemExit(f"FAIL_CLOSED_ARCGIS_ERROR {data['error']}")
 features=data.get("features") or []
 status="PASS_UNIQUE_OFFICIAL_HYDROLOGIC_UNIT" if len(features)==1 else ("NO_EXACT_OFFICIAL_HYDROLOGIC_UNIT" if not features else "AMBIGUOUS_OFFICIAL_HYDROLOGIC_UNIT")
 name=None; area=None; geometry_type=None
 if len(features)==1:
  f=features[0]; p=f.get("properties") or {}; g=f.get("geometry") or {}
  if str(p.get("CODIGO") or "").strip()!=EXPECTED_CODE:
   status="FAIL_CLOSED_CODE_MISMATCH"
  name=p.get("NOMBRE"); area=p.get("AREA_KM2"); geometry_type=g.get("type")
  if geometry_type not in {"Polygon","MultiPolygon"}:
   status="FAIL_CLOSED_NON_POLYGON_GEOMETRY"
  try:
   if float(area or 0)<=0: status="FAIL_CLOSED_INVALID_OFFICIAL_AREA"
  except (TypeError,ValueError): status="FAIL_CLOSED_INVALID_OFFICIAL_AREA"
 manifest={"version":"phase2-la-leche-hydrologic-unit-probe-v1",**GUARDS,
  "candidate_id":CANDIDATE_ID,"query_url":query_url(),"expected_unit_code":EXPECTED_CODE,
  "status":status,"feature_count":len(features),"official_unit_name":name,"official_area_km2":area,
  "geometry_type":geometry_type,"raw_response_sha256":sha(raw),"canonical_response_sha256":sha(canonical(data)),
  "separate_hydrologic_unit_asserted":status=="PASS_UNIQUE_OFFICIAL_HYDROLOGIC_UNIT",
  "separate_basin_wording_asserted":False,"outlet_inferred":False,"event_footprint_asserted":False,
  "hydraulic_capacity_inferred":False,"negative_control_inferred":False,"pitipo_polygon_inferred":False,
  "artificial_connector_used":False,"counts_as_complete_candidate_geometry":False,
  "allowed_interpretation":"If unique, preserve ANA's returned hydrologic-unit name and polygon as a separate PARTIAL research-context component; do not rename its unit class or infer routing beyond the official feature.",
  "forbidden":["rename the returned ANA unit as a basin unless ANA names it so","connect the unit artificially to Cuenca Motupe","infer Pítipo hydrologic polygon","infer local ravine geometry","infer event footprint or inundation extent","derive hydraulic capacity or discharge","derive operational threshold, risk or alert state","infer negative control from documentary silence"]}
 for path,payload in ((a.response,data),(a.manifest,manifest)):
  path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(canonical(payload))
 print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))
 return 0 if status=="PASS_UNIQUE_OFFICIAL_HYDROLOGIC_UNIT" else 2
if __name__=="__main__": raise SystemExit(main())
