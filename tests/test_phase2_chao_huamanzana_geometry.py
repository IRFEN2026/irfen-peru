import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DID="lalibertad_chao_huamanzaña_chorobal";CID="huamanzaña_basin_context"
C=ROOT/f"site/data/validation/phase2_discovery_contracts/{DID}.json";P=ROOT/f"site/data/validation/phase2_discovery_packages/{DID}.json";G=ROOT/"site/data/phase2/geometries/lalibertad_huamanzaña_basin_context.geojson";V=ROOT/"site/data/phase2/geometries/lalibertad_huamanzaña_basin_context_validation.json";CAT=ROOT/"site/data/map_layers.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
def load(p):return json.loads(p.read_text(encoding="utf-8"))
def dig(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def test_parent_never_becomes_composite_basin_geometry():
 c=load(C);p=load(P)
 for o in (c,p):
  for k,e in SAFE.items():assert o[k]==e
 assert c["assets"]["geometry"]["path"] is None;assert c["assets"]["geometry"]["status"]=="NO_COMPOSITE_GEOMETRY_PARENT_IS_TERRITORIAL_GROUPER"
 assert c["component_policy"]["composite_union_forbidden"] is True;assert c["component_policy"]["parent_is_map_polygon"] is False;assert p["parent_policy"]["composite_parent_geometry_forbidden"] is True;assert p["parent_policy"]["territorial_reference_is_basin"] is False
def test_huamanazana_exact_identity_and_chorobal_remains_separate():
 c=load(C);p=load(P);kids={x["child_id"]:x for x in p["hydrologic_children"]};h=kids[CID];ch=kids["chorobal_river_component"]
 assert h["ana_unit_code"]=="137712" and h["name"]=="Cuenca Huamanzaña";assert h["geometry"]["source_query"]["where"]=="CODIGO='137712'"
 assert ch["entity_role"]=="DISTINCT_RIVER_COMPONENT_WITHIN_HUAMANZANA_BASIN_CONTEXT";assert ch["geometry"]["path"] is None;assert str(ch["geometry"]["status"]).startswith("MISSING");assert "standalone basin" in ch["promotion_rule"].lower()
def test_frozen_geometry_hashes_and_scientific_guards():
 c=load(C);p=load(P);comps=c["assets"]["geometry_components"]
 if not comps:return
 assert len(comps)==1 and comps[0]["component_id"]==CID;g=comps[0]["geometry"];assert G.is_file() and V.is_file();assert g["sha256"]==dig(G);assert g["validation_sha256"]==dig(V);assert g["counts_as_event_footprint"] is False;assert g["counts_as_operational_geometry"] is False
 geo=load(G);props=geo["properties"]
 for k,e in SAFE.items():assert props[k]==e
 fp=geo["features"][0]["properties"];assert fp["official_unit_code"]=="137712";assert fp["counts_as_event_footprint"] is False;assert fp["counts_as_operational_geometry"] is False;assert fp["alerting_enabled"] is False
 v=load(V);assert v["outcomes_read"] is False;assert v["event_footprint_created"] is False;assert v["hydraulic_capacity_read"] is False;assert v["thresholds_used"] is False;assert v["negative_controls_read"] is False;assert v["chorobal_geometry_inferred"] is False;assert v["parent_composite_created"] is False
def test_map_only_materializes_huamanazana_child_context():
 c=load(C)
 if not c["assets"]["geometry_components"]:return
 rows=[x for x in load(CAT)["research_discovery_units"] if x.get("parent_discovery_id")==DID];assert len(rows)==1;r=rows[0];assert r["component_id"]==CID;assert r["geometry"]["map_eligible"] is True;assert r["geometry"]["path"]=="site/data/phase2/geometries/lalibertad_huamanzaña_basin_context.geojson";assert r["production_use"] is False;assert r["operational_alerting_enabled"] is False
