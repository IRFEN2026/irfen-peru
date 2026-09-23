import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"site/data/validation/phase2_discovery_contracts/lalibertad_jequetepeque.json"
PACKAGE=ROOT/"site/data/validation/phase2_discovery_packages/lalibertad_jequetepeque.json"
SOURCE_REGISTRY=ROOT/"site/data/phase2/sources/lalibertad_jequetepeque_official_evidence_v0_1.json"
GEOMETRY=ROOT/"site/data/phase2/geometries/lalibertad_jequetepeque_basin_context.geojson"
VALIDATION=ROOT/"site/data/phase2/geometries/lalibertad_jequetepeque_geometry_validation.json"
CATALOG=ROOT/"site/data/map_layers.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
MAP_SAFE={k:v for k,v in SAFE.items() if k!="test_mode"}
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def test_jequetepeque_identity_query_and_guards_are_fail_closed():
 c=load(CONTRACT); p=load(PACKAGE); s=load(SOURCE_REGISTRY)
 for o in (c,p,s):
  for k,e in SAFE.items(): assert o[k]==e
 for o in (c,p):
  i=o["hydrologic_identity"]; assert i["ana_unit_code"]=="13774"; assert i["ana_unit_name"]=="Cuenca Jequetepeque"; assert i["territorial_reference_is_basin"] is False
 assert p["hydrologic_identity"]["chepen_is_hydrologic_unit"] is False
 q=c["source_query"]; assert q["endpoint"]=="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"; assert q["where"]=="CODIGO='13774'"; assert q==p["assets"]["geometry"]["source_query"]
 for o in (c,p):
  g=o["assets"]["geometry"]; assert g["counts_as_operational_geometry"] is False; assert g["counts_as_event_footprint"] is False
def test_jequetepeque_regulation_and_neighbor_separation_remain_explicit():
 p=load(PACKAGE); s=load(SOURCE_REGISTRY)
 assert p["assets"]["hydraulic_context"]["capacity_values"] is None
 assert p["assets"]["hydraulic_context"]["works_are_historical_capacity"] is False
 assert p["assets"]["hydraulic_context"]["reservoir_operation_is_natural_response"] is False
 assert p["mechanism_policy"]["chaman_auto_merge_forbidden"] is True
 assert p["mechanism_policy"]["zana_or_chicama_auto_merge_forbidden"] is True
 assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
 assert s["qa"]["chaman_merged_into_jequetepeque"] is False
 assert s["qa"]["chepen_materialized_as_river"] is False
 assert s["qa"]["provider_bands_are_irfen_thresholds"] is False
def test_jequetepeque_geometry_is_missing_or_exactly_hash_linked():
 c=load(CONTRACT); p=load(PACKAGE); cg=c["assets"]["geometry"]; pg=p["assets"]["geometry"]
 if str(cg["status"]).startswith("MISSING"):
  assert str(pg["status"]).startswith("MISSING"); assert not GEOMETRY.exists(); return
 assert cg["status"]==pg["status"]=="PARTIAL_OFFICIAL_BASIN_CONTEXT"; assert GEOMETRY.is_file() and VALIDATION.is_file(); assert cg["sha256"]==pg["sha256"]==digest(GEOMETRY); assert cg["validation_sha256"]==pg["validation_sha256"]==digest(VALIDATION)
 d=load(GEOMETRY); props=d["properties"]
 for k,e in SAFE.items(): assert props[k]==e
 assert len(d["features"])==1; fp=d["features"][0]["properties"]; assert fp["official_unit_code"]=="13774"; assert fp["name"]=="Cuenca Jequetepeque"; assert fp["counts_as_event_footprint"] is False; assert fp["counts_as_operational_geometry"] is False; assert fp["alerting_enabled"] is False
 v=load(VALIDATION); assert v["ana_unit_name"]=="Cuenca Jequetepeque"; assert v["outcomes_read"] is False; assert v["rainfall_read"] is False; assert v["hydraulic_capacity_read"] is False; assert v["thresholds_used"] is False; assert v["negative_controls_read"] is False; assert v["approximate_geometry_used"] is False; assert v["event_footprint_created"] is False
def test_jequetepeque_map_catalog_only_publishes_reproducible_context_geometry():
 c=load(CONTRACT)
 if str(c["assets"]["geometry"]["status"]).startswith("MISSING"): return
 rows=[x for x in load(CATALOG)["research_discovery_units"] if x.get("discovery_id")=="lalibertad_jequetepeque"]; assert len(rows)==1; r=rows[0]
 for k,e in MAP_SAFE.items(): assert r[k]==e
 assert r["geometry"]["map_eligible"] is True; assert r["geometry"]["path"]=="site/data/phase2/geometries/lalibertad_jequetepeque_basin_context.geojson"
