#!/usr/bin/env python3
"""Probe official ANA/GEOSNIRH geometry for Rio La Leche.

RESEARCH_ONLY / TEST_ONLY. This discovery probe may only identify a literal official
watercourse geometry already supported by the frozen identity code 1377722. It must
not infer a separate basin, outlet, event footprint, hydraulic capacity, threshold,
negative control, risk class, activation state or alert.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERVICE="https://geosnirh.ana.gob.pe/server/rest/services/Mapas_ALA/Capas_ALA_Motupe_Olmos_LaLeche/MapServer"
SEARCH_TEXT="Rio La Leche"
EXPECTED_CODE="1377722"
EXPECTED_NAME="Rio La Leche"
CANDIDATE_ID="lambayeque_motupe_la_leche_pitipo"
GUARDS={
 "deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,
 "production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED",
 "missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,
}

def find_url():
 return SERVICE+"/find?"+urlencode({
  "searchText":SEARCH_TEXT,"contains":"false","sr":"4326","returnGeometry":"true",
  "geometryPrecision":"7","returnZ":"false","returnM":"false","f":"json"})

def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def normalize_text(v): return " ".join(str(v or "").split()).casefold()

def result_matches(row):
 attrs=row.get("attributes") or {}
 values={normalize_text(v) for v in attrs.values() if v is not None}
 name_ok=normalize_text(row.get("foundFieldName")) in {"nombre","name","nombrerio","nom_rio"} and normalize_text(row.get("value"))==normalize_text(EXPECTED_NAME)
 literal_name=normalize_text(EXPECTED_NAME) in values or normalize_text(row.get("value"))==normalize_text(EXPECTED_NAME)
 code_ok=EXPECTED_CODE in {str(v).strip() for v in attrs.values() if v is not None}
 return literal_name and code_ok, name_ok, attrs

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--response",type=Path,required=True); ap.add_argument("--manifest",type=Path,required=True); a=ap.parse_args()
 req=Request(find_url(),headers={"User-Agent":"IRFEN-research-source-lock/1.0"})
 with urlopen(req,timeout=45) as r: raw=r.read()
 data=json.loads(raw.decode("utf-8"))
 if data.get("error"): raise SystemExit(f"FAIL_CLOSED_ARCGIS_ERROR {data['error']}")
 rows=data.get("results") or []
 matches=[]
 for row in rows:
  exact,_,_=result_matches(row)
  if exact: matches.append(row)
 status="PASS_UNIQUE_OFFICIAL_WATERCOURSE" if len(matches)==1 else ("NO_EXACT_OFFICIAL_WATERCOURSE" if not matches else "AMBIGUOUS_OFFICIAL_WATERCOURSE")
 geometry_type=None; layer_id=None; layer_name=None
 if len(matches)==1:
  m=matches[0]; geometry_type=(m.get("geometryType") or "").replace("esriGeometry","") or None
  layer_id=m.get("layerId"); layer_name=m.get("layerName")
  geom=m.get("geometry") or {}
  if not isinstance(geom,dict) or not geom.get("paths"):
   status="FAIL_CLOSED_NON_POLYLINE_GEOMETRY"
 manifest={"version":"phase2-la-leche-watercourse-probe-v1",**GUARDS,
  "candidate_id":CANDIDATE_ID,"service":SERVICE,"find_url":find_url(),
  "expected_watercourse_code":EXPECTED_CODE,"expected_watercourse_name":EXPECTED_NAME,
  "status":status,"result_count":len(rows),"exact_match_count":len(matches),
  "matched_layer_id":layer_id,"matched_layer_name":layer_name,"geometry_type":geometry_type,
  "raw_response_sha256":sha(raw),"canonical_response_sha256":sha(canonical(data)),
  "separate_basin_asserted":False,"outlet_inferred":False,"event_footprint_asserted":False,
  "hydraulic_capacity_inferred":False,"negative_control_inferred":False,
  "counts_as_complete_candidate_geometry":False,
  "allowed_interpretation":"Official watercourse line only if exact code/name identity is unique; Motupe basin and Rio La Leche remain separate mapped component roles.",
  "forbidden":["infer a separate La Leche basin from a river line","connect Rio La Leche artificially to Rio Motupe","infer Pítipo hydrologic polygon","infer event footprint or inundation extent","derive hydraulic capacity or discharge","derive operational threshold or risk state","infer negative control from documentary silence"]}
 for path,payload in ((a.response,data),(a.manifest,manifest)):
  path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(canonical(payload))
 print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))
 return 0 if status=="PASS_UNIQUE_OFFICIAL_WATERCOURSE" else 2
if __name__=="__main__": raise SystemExit(main())
