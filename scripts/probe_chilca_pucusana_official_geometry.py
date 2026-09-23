#!/usr/bin/env python3
"""Freeze official ANA Cuenca Chilca geometry as Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. The emitted polygon is only official ANA hydrologic
unit 1375532. It does not resolve Pucusana hydrologic identity, local ravines,
event footprints, exposure, hydraulic capacity, controls, thresholds or activation.
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE_ID="lima_sur_chilca_pucusana"
QUERY_NAME="Cuenca Chilca"
EXPECTED_CODE="1375532"
SOURCE_ID="ANA-IDEP-UH-CHILCA-1375532-20260923"
BASE="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SOURCE_DIR=ROOT/"site/data/phase2/sources/chilca_pucusana_hydrologic_context"
SOURCE=SOURCE_DIR/"ana_cuenca_chilca_1375532.geojson"
SOURCE_INVENTORY=SOURCE_DIR/"source_inventory.json"
GEOMETRY=ROOT/"site/data/phase2/geometries/lima_sur_chilca_pucusana_chilca_basin_context.geojson"
VALIDATION=ROOT/"site/data/phase2/geometries/lima_sur_chilca_pucusana_geometry_validation.json"
CONTRACT=ROOT/"site/data/validation/phase2_zone_contracts/lima_sur_chilca_pucusana.json"
INVENTORIES=[ROOT/"config/phase2_candidate_inventory_v0_1.json",ROOT/"config/phase2_candidate_inventory_v0_2.json"]
GUARDS={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}

def query_url():
 return BASE+"?"+urlencode({"where":f"NOMBRE='{QUERY_NAME}'","outFields":"*","returnGeometry":"true","outSR":"4326","geometryPrecision":"7","f":"geojson"})
def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(canonical(v))
def validate_source(data):
 fs=data.get("features") or []
 if data.get("type")!="FeatureCollection" or len(fs)!=1: raise ValueError("expected exactly one official Chilca feature")
 f=fs[0];p=f.get("properties") or {}
 if str(p.get("CODIGO"))!=EXPECTED_CODE: raise ValueError(f"unexpected ANA code: {p.get('CODIGO')}")
 if p.get("NOMBRE")!=QUERY_NAME: raise ValueError(f"unexpected ANA name: {p.get('NOMBRE')}")
 if (f.get("geometry") or {}).get("type") not in {"Polygon","MultiPolygon"}: raise ValueError("official Chilca geometry is not polygonal")
 if float(p.get("AREA_KM2") or 0)<=0: raise ValueError("official area missing")
 return f
def fetch_source():
 req=Request(query_url(),headers={"User-Agent":"IRFEN-research-source-lock/1.0"})
 with urlopen(req,timeout=45) as r: raw=r.read()
 data=json.loads(raw.decode());validate_source(data);return data,sha_bytes(raw)
def source_record_from_inventory():
 inv=load(SOURCE_INVENTORY)
 for k,v in GUARDS.items():
  if inv.get(k)!=v: raise ValueError(f"unsafe source inventory guard: {k}")
 s=inv.get("sources") or []
 if len(s)!=1 or s[0].get("source_id")!=SOURCE_ID: raise ValueError("unexpected Chilca source inventory")
 return s[0]
def expected_inventory_document(doc):
 u=json.loads(json.dumps(doc));rows=[r for r in u.get("candidates") or [] if r.get("candidate_id")==CANDIDATE_ID]
 if len(rows)!=1: raise ValueError("Chilca-Pucusana candidate missing")
 src=list(rows[0].get("official_sources") or [])
 if SOURCE_ID not in src: src.append(SOURCE_ID)
 rows[0]["official_sources"]=src;u.setdefault("official_source_catalog",{})[SOURCE_ID]=query_url();return u
def expected_contract_document(doc,geometry_rel):
 u=json.loads(json.dumps(doc))
 if u.get("candidate_id")!=CANDIDATE_ID: raise ValueError("contract identity mismatch")
 if u.get("deployment_status")!="RESEARCH_ONLY" or u.get("production_use") is not False: raise ValueError("unsafe contract")
 if u.get("decision_thresholds") is not None or u.get("hydraulic_factors") is not None: raise ValueError("decision fields populated")
 if u.get("missing_data_rule")!="UNKNOWN_NOT_LOW_RISK" or (u.get("validation") or {}).get("activation_gate")!="BLOCKED": raise ValueError("fail-closed guards changed")
 u["test_mode"]="TEST_ONLY";u["production_ready"]=False;u["operational_alerting_enabled"]=False
 ids=list(u.get("official_source_ids") or []);
 if SOURCE_ID not in ids: ids.append(SOURCE_ID)
 u["official_source_ids"]=ids;g=u.setdefault("assets",{}).setdefault("geometry",{});gs=list(g.get("source_ids") or [])
 if SOURCE_ID not in gs: gs.append(SOURCE_ID)
 g.update({"status":"PARTIAL","path":geometry_rel,"source_ids":gs})
 note="Official ANA Cuenca Chilca unit 1375532 is normalized only as PARTIAL basin context; Pucusana identity and named local ravines remain unresolved and must not be inferred from this polygon."
 notes=list(u.get("notes") or []);u["notes"]=notes if note in notes else notes+[note];return u
def build_documents(source,rec):
 f=validate_source(source);p=f["properties"]
 norm={"type":"FeatureCollection","properties":{**GUARDS,"candidate_id":CANDIDATE_ID,"geometry_status":"PARTIAL_OFFICIAL_CHILCA_BASIN_CONTEXT","source_id":SOURCE_ID,"source_snapshot_sha256":rec["canonical_sha256"],"coverage":"Official ANA Cuenca Chilca polygon only; Pucusana and local ravines remain unresolved.","map_disclaimer":"RESEARCH_ONLY basin context; not an event footprint, hazard extent, hydraulic model, risk level or alert layer."},"features":[{"type":"Feature","id":"lima_sur_chilca_pucusana_chilca_basin_context_1375532","properties":{"candidate_id":CANDIDATE_ID,"unit_id":"lima_sur_chilca_pucusana_chilca_basin_context_1375532","name":"Cuenca Chilca · contexto hidrológico ANA","feature_role":"OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT","hydrologic_role":"OFFICIAL_CHILCA_BASIN_BOUNDARY_NOT_COMPOSITE_CHILCA_PUCUSANA","deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","review_status":"REVIEW_ONLY","activation_gate":"BLOCKED","production_use":False,"production_ready":False,"alerting_enabled":False,"operational_alerting_enabled":False,"loaded_into_operational_calculation":False,"carries_alert_values":False,"carries_risk_classification":False,"missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,"official_hydrologic_unit_code":str(p["CODIGO"]),"official_hydrologic_unit_name":p["NOMBRE"],"official_area_km2":float(p["AREA_KM2"]),"source_id":SOURCE_ID,"source_crs":"EPSG:4326 requested from ANA IDEP ArcGIS service","geometry_method":"OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM","district_boundary_used":False,"dem_used":False,"outlet_used":False,"outlet":None,"pucusana_identity_resolved":False,"local_ravines_geometry_resolved":False,"event_footprint_resolved":False,"counts_as_complete_candidate_geometry":False,"confidence":"HIGH_OFFICIAL_CHILCA_BASIN_GEOMETRY","warning":"Do not extend Cuenca Chilca geometry to Pucusana or infer local ravines, event extent, capacity, thresholds, risk or alert state."},"geometry":f["geometry"]}]}
 val={"version":"phase2-chilca-pucusana-geometry-validation-v1",**GUARDS,"status":"PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY","candidate_id":CANDIDATE_ID,"source_snapshot_path":rec["local_path"],"source_snapshot_sha256":rec["canonical_sha256"],"normalized_geometry_path":GEOMETRY.relative_to(ROOT).as_posix(),"normalized_geometry_sha256":sha_bytes(canonical(norm)),"official_unit":{"code":str(p["CODIGO"]),"name":p["NOMBRE"],"area_km2":float(p["AREA_KM2"])},"component_resolution":{"chilca_basin_polygon":"REPRODUCIBLE_OFFICIAL_GEOMETRY","pucusana_hydrologic_identity":"UNRESOLVED_NO_GEOMETRY_DRAWN","local_ravines":"UNRESOLVED_NO_GEOMETRY_DRAWN","event_footprint":"NOT_ASSERTED","hydraulic_capacity":"UNKNOWN","negative_controls":"NOT_ASSERTED"},"counts_as_complete_candidate_geometry":False,"artificial_connector_used":False,"activation_gate":"BLOCKED"}
 return norm,val
def sync(check_only):
 rec=source_record_from_inventory();sp=ROOT/rec["local_path"];src=load(sp)
 if sha_bytes(canonical(src))!=rec["canonical_sha256"]: raise ValueError("frozen Chilca source hash mismatch")
 norm,val=build_documents(src,rec);expected={GEOMETRY:norm,VALIDATION:val,CONTRACT:expected_contract_document(load(CONTRACT),GEOMETRY.relative_to(ROOT).as_posix())}
 for p in INVENTORIES: expected[p]=expected_inventory_document(load(p))
 for p,v in expected.items():
  if check_only:
   if not p.is_file() or p.read_bytes()!=canonical(v): raise ValueError(f"stale deterministic artifact: {p.relative_to(ROOT)}")
  else: write(p,v)
def refresh_source():
 src,rawsha=fetch_source();f=validate_source(src);write(SOURCE,src);p=f["properties"]
 inv={"version":"phase2-chilca-pucusana-source-inventory-v1",**GUARDS,"sources":[{"candidate_id":CANDIDATE_ID,"source_id":SOURCE_ID,"institution":"Autoridad Nacional del Agua / IDEP","url":query_url(),"role":"official_chilca_basin_geometry_research_context_only","local_path":SOURCE.relative_to(ROOT).as_posix(),"canonical_sha256":sha_bytes(canonical(src)),"raw_response_sha256_at_freeze":rawsha,"official_unit_code":str(p["CODIGO"]),"official_unit_name":p["NOMBRE"],"official_area_km2":float(p["AREA_KM2"]),"acquired_at_utc":datetime.now(timezone.utc).isoformat()}],"forbidden":["treat Cuenca Chilca as a composite Chilca-Pucusana geometry","invent Pucusana or local-ravine geometry","treat basin/faja as event footprint","infer hydraulic capacity, discharge or thresholds","infer negative controls from documentary silence","derive risk levels or alerts"]}
 write(SOURCE_INVENTORY,inv);sync(False)
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--refresh-source",action="store_true");ap.add_argument("--check-only",action="store_true");a=ap.parse_args()
 if a.refresh_source and a.check_only: raise ValueError("mutually exclusive")
 if a.refresh_source: refresh_source()
 else:
  if not SOURCE_INVENTORY.is_file(): raise ValueError("frozen source missing; use --refresh-source once")
  sync(a.check_only)
 print(json.dumps({"status":"PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY","candidate_id":CANDIDATE_ID,"official_unit_code":EXPECTED_CODE,"counts_as_complete_candidate_geometry":False,"activation_gate":"BLOCKED"},ensure_ascii=False,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
