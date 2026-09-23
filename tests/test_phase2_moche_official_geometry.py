import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"site/data/validation/phase2_discovery_contracts/lalibertad_moche.json"
PACKAGE=ROOT/"site/data/validation/phase2_discovery_packages/lalibertad_moche.json"
GEOMETRY=ROOT/"site/data/phase2/geometries/lalibertad_moche_basin_context.geojson"
VALIDATION=ROOT/"site/data/phase2/geometries/lalibertad_moche_geometry_validation.json"
CATALOG=ROOT/"site/data/map_layers.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
MAP_SAFE={k:v for k,v in SAFE.items() if k!="test_mode"}
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def test_moche_identity_query_and_guards_are_fail_closed():
 c=load(CONTRACT); p=load(PACKAGE)
 for o in (c,p):
  for k,e in SAFE.items(): assert o[k]==e
  i=o["hydrologic_identity"]; assert i["ana_unit_code"]=="137716"; assert i["ana_unit_name"]=="Cuenca Moche"; assert i["territorial_reference_is_basin"] is False
 q=c["source_query"]; assert q["endpoint"]=="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"; assert q["where"]=="CODIGO='137716'"; assert q==p["assets"]["geometry"]["source_query"]
 for o in (c,p):
  g=o["assets"]["geometry"]; assert g["counts_as_operational_geometry"] is False; assert g["counts_as_event_footprint"] is False
def test_moche_geometry_is_missing_or_exactly_hash_linked():
 c=load(CONTRACT); p=load(PACKAGE); cg=c["assets"]["geometry"]; pg=p["assets"]["geometry"]
 if str(cg["status"]).startswith("MISSING"):
  assert str(pg["status"]).startswith("MISSING"); assert not GEOMETRY.exists(); return
 assert cg["status"]==pg["status"]=="PARTIAL_OFFICIAL_BASIN_CONTEXT"; assert GEOMETRY.is_file() and VALIDATION.is_file(); assert cg["sha256"]==pg["sha256"]==digest(GEOMETRY); assert cg["validation_sha256"]==pg["validation_sha256"]==digest(VALIDATION)
 d=load(GEOMETRY); props=d["properties"]
 for k,e in SAFE.items(): assert props[k]==e
 assert len(d["features"])==1; fp=d["features"][0]["properties"]; assert fp["official_unit_code"]=="137716"; assert fp["name"]=="Cuenca Moche"; assert fp["counts_as_event_footprint"] is False; assert fp["counts_as_operational_geometry"] is False; assert fp["alerting_enabled"] is False
 v=load(VALIDATION); assert v["ana_unit_name"]=="Cuenca Moche"; assert v["outcomes_read"] is False; assert v["rainfall_read"] is False; assert v["hydraulic_capacity_read"] is False; assert v["thresholds_used"] is False; assert v["negative_controls_read"] is False; assert v["approximate_geometry_used"] is False; assert v["event_footprint_created"] is False
def test_moche_map_catalog_only_publishes_reproducible_context_geometry():
 c=load(CONTRACT)
 if str(c["assets"]["geometry"]["status"]).startswith("MISSING"): return
 rows=[x for x in load(CATALOG)["research_discovery_units"] if x.get("discovery_id")=="lalibertad_moche"]; assert len(rows)==1; r=rows[0]
 for k,e in MAP_SAFE.items(): assert r[k]==e
 assert r["geometry"]["map_eligible"] is True; assert r["geometry"]["path"]=="site/data/phase2/geometries/lalibertad_moche_basin_context.geojson"
