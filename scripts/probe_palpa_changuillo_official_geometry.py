#!/usr/bin/env python3
"""Freeze/replay official ANA Cuenca Grande geometry as Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. Only the ANA hydrologic unit Cuenca Grande (1372)
is materialized. Palpa/Changuillo local rivers, ravines, outlets, event footprints,
hydraulic capacity, operational thresholds and negative controls remain unresolved.
"""
from __future__ import annotations

import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE_ID="ica_palpa_changuillo"
QUERY_NAME="Cuenca Grande"
EXPECTED_CODE="1372"
EXPECTED_AREA_KM2=10991.2703
EXPECTED_CANONICAL_SOURCE_SHA256="3ac91009d90eaf5f245fb0d481b7fb0777f1d8265b081bc23601f83bf6b3de70"
BOOTSTRAP_RAW_RESPONSE_SHA256="2e4a5721af240e25ddd724a87446c860d2b14a75d3dbee959d58a516d992a1ad"
SOURCE_ID="ANA-IDEP-UH-GRANDE-1372-20260923"
BASE="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SOURCE_DIR=ROOT/"site/data/phase2/sources/palpa_changuillo_hydrologic_context"
SOURCE=SOURCE_DIR/"ana_cuenca_grande_1372.geojson"
SOURCE_INVENTORY=SOURCE_DIR/"source_inventory.json"
GEOMETRY=ROOT/"site/data/phase2/geometries/ica_palpa_changuillo_grande_basin_context.geojson"
VALIDATION=ROOT/"site/data/phase2/geometries/ica_palpa_changuillo_geometry_validation.json"
CONTRACT=ROOT/"site/data/validation/phase2_zone_contracts/ica_palpa_changuillo.json"
INVENTORIES=[ROOT/"config/phase2_candidate_inventory_v0_1.json",ROOT/"config/phase2_candidate_inventory_v0_2.json"]

GUARDS={
 "deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,
 "production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED",
 "missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,
}

def query_url():
 return BASE+"?"+urlencode({"where":f"NOMBRE='{QUERY_NAME}'","outFields":"*","returnGeometry":"true","outSR":"4326","geometryPrecision":"7","f":"geojson"})
def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(canonical(v))

def validate_source(data):
 if data.get("type")!="FeatureCollection" or len(data.get("features") or [])!=1: raise ValueError("expected exactly one official Cuenca Grande feature")
 f=data["features"][0]; p=f.get("properties") or {}
 if str(p.get("CODIGO"))!=EXPECTED_CODE or p.get("NOMBRE")!=QUERY_NAME: raise ValueError(f"unexpected ANA identity: {p}")
 if abs(float(p.get("AREA_KM2") or 0)-EXPECTED_AREA_KM2)>0.0001: raise ValueError("official Cuenca Grande area changed from frozen bootstrap evidence")
 if (f.get("geometry") or {}).get("type") not in {"Polygon","MultiPolygon"}: raise ValueError("official Cuenca Grande geometry is not polygonal")
 if sha_bytes(canonical(data))!=EXPECTED_CANONICAL_SOURCE_SHA256: raise ValueError("official Cuenca Grande canonical source hash changed")
 return f

def fetch_source():
 req=Request(query_url(),headers={"User-Agent":"IRFEN-research-source-lock/1.0"})
 with urlopen(req,timeout=45) as response: raw=response.read()
 data=json.loads(raw.decode("utf-8")); validate_source(data)
 return data,sha_bytes(raw)

def expected_inventory_document(doc):
 out=json.loads(json.dumps(doc)); rows=[r for r in out.get("candidates") or [] if r.get("candidate_id")==CANDIDATE_ID]
 if len(rows)!=1: raise ValueError("Palpa-Changuillo candidate missing from inventory")
 row=rows[0]; sources=list(row.get("official_sources") or [])
 if SOURCE_ID not in sources: sources.append(SOURCE_ID)
 row["official_sources"]=sources
 out.setdefault("official_source_catalog",{})[SOURCE_ID]=query_url()
 return out

def expected_contract_document(doc):
 out=json.loads(json.dumps(doc))
 if out.get("candidate_id")!=CANDIDATE_ID: raise ValueError("Palpa-Changuillo contract identity mismatch")
 if out.get("deployment_status")!="RESEARCH_ONLY" or out.get("production_use") is not False: raise ValueError("unsafe Palpa-Changuillo contract")
 if out.get("missing_data_rule")!="UNKNOWN_NOT_LOW_RISK" or out.get("decision_thresholds") is not None or out.get("hydraulic_factors") is not None: raise ValueError("Palpa-Changuillo scientific guards changed")
 if (out.get("validation") or {}).get("activation_gate")!="BLOCKED": raise ValueError("Palpa-Changuillo activation gate changed")
 out["test_mode"]="TEST_ONLY"; out["production_ready"]=False; out["operational_alerting_enabled"]=False
 source_ids=list(out.get("official_source_ids") or [])
 if SOURCE_ID not in source_ids: source_ids.append(SOURCE_ID)
 out["official_source_ids"]=source_ids
 geom=out.setdefault("assets",{}).setdefault("geometry",{}); gs=list(geom.get("source_ids") or [])
 if SOURCE_ID not in gs: gs.append(SOURCE_ID)
 geom.update({"status":"PARTIAL","path":GEOMETRY.relative_to(ROOT).as_posix(),"source_ids":gs})
 note="Official ANA Cuenca Grande geometry is normalized only as PARTIAL research context; Palpa/Changuillo local river reaches, ravines, event footprints and cross-component routing remain unresolved."
 notes=list(out.get("notes") or [])
 if note not in notes: notes.append(note)
 out["notes"]=notes
 return out

def source_inventory_doc(raw_sha):
 return {"version":"phase2-palpa-changuillo-source-inventory-v1",**GUARDS,"sources":[{
  "candidate_id":CANDIDATE_ID,"source_id":SOURCE_ID,"institution":"Autoridad Nacional del Agua / IDEP",
  "url":query_url(),"role":"official_hydrologic_unit_geometry_research_context","local_path":SOURCE.relative_to(ROOT).as_posix(),
  "canonical_sha256":EXPECTED_CANONICAL_SOURCE_SHA256,"bootstrap_raw_response_sha256":BOOTSTRAP_RAW_RESPONSE_SHA256,
  "refresh_raw_response_sha256":raw_sha,"bootstrap_workflow_run_id":35802048634,"bootstrap_artifact_id":10726296171,
  "bootstrap_artifact_digest":"sha256:d6e1692a1a88daca4325a60d0c476538d6189b45707cacbe942deba7e1c87a4a",
  "official_unit_code":EXPECTED_CODE,"official_unit_name":QUERY_NAME,"official_area_km2":EXPECTED_AREA_KM2,
  "frozen_at_utc":"2026-09-23T00:26:56Z"}],"forbidden":[
   "treat basin polygon as an event or inundation footprint","invent Palpa/Changuillo river, ravine, outlet or connector geometry",
   "infer hydraulic capacity or historical discharge from basin geometry","infer operational thresholds or activation",
   "infer negative controls from documentary silence"]}

def build_documents(source):
 f=validate_source(source); p=f["properties"]
 normalized={"type":"FeatureCollection","properties":{**GUARDS,"candidate_id":CANDIDATE_ID,
  "geometry_status":"PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT","source_id":SOURCE_ID,"source_snapshot_sha256":EXPECTED_CANONICAL_SOURCE_SHA256,
  "coverage":"Official ANA Cuenca Grande unit 1372 only; Palpa/Changuillo local rivers and ravines remain unresolved separate components.",
  "map_disclaimer":"Official basin context RESEARCH_ONLY; not an event footprint, inundation extent, hydraulic-capacity model, risk level or alert layer."},
  "features":[{"type":"Feature","id":"ica_palpa_changuillo_grande_basin_context_1372","properties":{
   "candidate_id":CANDIDATE_ID,"unit_id":"ica_palpa_changuillo_grande_basin_context_1372","name":"Cuenca Grande · contexto hidrológico ANA",
   "feature_role":"OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT","hydrologic_role":"OFFICIAL_BASIN_BOUNDARY_NOT_EVENT_FOOTPRINT",
   "deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","review_status":"REVIEW_ONLY","activation_gate":"BLOCKED",
   "production_use":False,"production_ready":False,"alerting_enabled":False,"operational_alerting_enabled":False,
   "loaded_into_operational_calculation":False,"carries_alert_values":False,"carries_risk_classification":False,
   "missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,
   "official_hydrologic_unit_code":str(p["CODIGO"]),"official_hydrologic_unit_name":p["NOMBRE"],"official_area_km2":float(p["AREA_KM2"]),
   "source_id":SOURCE_ID,"source_crs":"EPSG:4326 requested from ANA IDEP ArcGIS service","geometry_method":"OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM",
   "district_boundary_used":False,"dem_used":False,"outlet_used":False,"outlet":None,
   "local_river_reaches_geometry_resolved":False,"local_ravines_geometry_resolved":False,"event_footprint_asserted":False,
   "counts_as_complete_candidate_geometry":False,"confidence":"HIGH_OFFICIAL_BASIN_GEOMETRY",
   "warning":"Basin context only; do not infer local routing, event extent, hydraulic capacity, thresholds, risk, activation or alert state."},"geometry":f["geometry"]}]}
 validation={"version":"phase2-palpa-changuillo-geometry-validation-v1",**GUARDS,"status":"PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
  "candidate_id":CANDIDATE_ID,"source_snapshot_path":SOURCE.relative_to(ROOT).as_posix(),"source_snapshot_sha256":EXPECTED_CANONICAL_SOURCE_SHA256,
  "normalized_geometry_path":GEOMETRY.relative_to(ROOT).as_posix(),"normalized_geometry_sha256":sha_bytes(canonical(normalized)),
  "official_unit":{"code":EXPECTED_CODE,"name":QUERY_NAME,"area_km2":EXPECTED_AREA_KM2},"component_resolution":{
   "cuenca_grande_polygon":"REPRODUCIBLE_OFFICIAL_GEOMETRY","palpa_changuillo_local_river_reaches":"UNRESOLVED_NO_GEOMETRY_DRAWN",
   "local_ravines":"UNRESOLVED_NO_GEOMETRY_DRAWN","event_footprint":"NOT_ASSERTED","hydraulic_capacity":"UNKNOWN"},
  "counts_as_complete_candidate_geometry":False,"artificial_connector_used":False}
 return normalized,validation

def materialize():
 source,raw_sha=fetch_source(); normalized,validation=build_documents(source)
 write(SOURCE,source); write(SOURCE_INVENTORY,source_inventory_doc(raw_sha)); write(GEOMETRY,normalized); write(VALIDATION,validation)
 write(CONTRACT,expected_contract_document(load(CONTRACT)))
 for p in INVENTORIES: write(p,expected_inventory_document(load(p)))

def check():
 source=load(SOURCE); validate_source(source); inv=load(SOURCE_INVENTORY)
 for k,v in GUARDS.items():
  if inv.get(k)!=v: raise ValueError(f"unsafe source inventory guard {k}")
 rows=inv.get("sources") or []
 if len(rows)!=1 or rows[0].get("canonical_sha256")!=EXPECTED_CANONICAL_SOURCE_SHA256: raise ValueError("frozen source inventory mismatch")
 normalized,validation=build_documents(source)
 if GEOMETRY.read_bytes()!=canonical(normalized): raise ValueError("normalized geometry is not deterministic")
 if load(VALIDATION)!=validation: raise ValueError("geometry validation is stale")
 if load(CONTRACT)!=expected_contract_document(load(CONTRACT)): raise ValueError("contract is not in deterministic guarded state")
 for p in INVENTORIES:
  if load(p)!=expected_inventory_document(load(p)): raise ValueError(f"inventory source registration missing: {p.name}")

def main():
 ap=argparse.ArgumentParser(); g=ap.add_mutually_exclusive_group(required=True); g.add_argument("--materialize",action="store_true"); g.add_argument("--check-only",action="store_true"); a=ap.parse_args()
 if a.materialize: materialize()
 else: check()
 print(json.dumps({"status":"PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY","candidate_id":CANDIDATE_ID,"official_unit_code":EXPECTED_CODE,"counts_as_complete_candidate_geometry":False,"activation_gate":"BLOCKED"},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
