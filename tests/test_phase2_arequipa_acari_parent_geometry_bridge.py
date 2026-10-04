import hashlib, json
from pathlib import Path

CFG=Path("config/phase2_arequipa_acari_parent_geometry_bridge_v0_1.json")
BASE=Path("config/phase2_south_coast_ica_arequipa_discovery_v0_1.json")
CONTRACT=Path("site/data/validation/phase2_zone_contracts/arequipa_acari_san_agustin.json")
REVIEW=Path("site/data/validation/phase2_research_evidence/acari_san_agustin_identity_review_20260923.json")

UNSUPPORTED=(
    "full_channel_geometry_supported",
    "catchment_geometry_supported",
    "outlet_supported",
    "routing_to_rio_acari_supported",
    "event_footprint_supported",
    "historical_hydraulic_capacity_supported",
    "map_geometry_materialized",
)

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def sha(p):
    d=load(p)
    raw=(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    return hashlib.sha256(raw).hexdigest()

def test_acari_parent_geometry_bridge():
    c=load(CFG)
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    r=c["reused_frozen_geometry"]
    v=load(Path(r["geometry_validation_path"]))
    assert v["official_unit"]["code"]=="13718"
    assert v["official_unit"]["name"]=="Cuenca Acarí"
    assert sha(Path(r["geometry_path"]))==r["normalized_geometry_sha256"]
    assert sha(Path(r["source_snapshot_path"]))==r["source_snapshot_sha256"]
    # San Agustín is an unresolved component of the existing candidate, never a discovery child.
    assert "local_children_remaining_fail_closed" not in c
    comp=c["existing_candidate_unresolved_component"]
    assert comp["candidate_id"]=="arequipa_acari_san_agustin"
    assert comp["component_id"]=="quebrada_san_agustin"
    assert "child_id" not in comp
    assert comp["geometry_asset"] is None
    assert comp["outlet"] is None
    assert comp["map_publishable"] is False
    assert c["summary"]["new_operational_zones"]==0

def test_frozen_acari_geometry_chain_is_reference_only_and_unchanged():
    c=load(CFG)
    r=c["reused_frozen_geometry"]
    assert r["existing_candidate_id"]=="arequipa_acari_san_agustin"
    assert r["geometry_reuse_policy"]=="REFERENCE_EXISTING_FROZEN_ASSET_DO_NOT_DUPLICATE"
    assert r["normalized_geometry_sha256"]=="fcfa8d4dd3216cd4e548bfac9edff15985779037526cf505a13079646c8c3ade"
    assert r["source_snapshot_sha256"]=="e603ccf0a081b67edcad61c41fca2b8392d36a6eb25ea236e677b157b2477be1"
    v=load(Path(r["geometry_validation_path"]))
    assert v["candidate_id"]=="arequipa_acari_san_agustin"
    assert v["official_unit"]=={"area_km2":4293.0766,"code":"13718","name":"Cuenca Acarí"}
    assert v["normalized_geometry_path"]==r["geometry_path"]
    assert v["source_snapshot_path"]==r["source_snapshot_path"]
    assert v["normalized_geometry_sha256"]==r["normalized_geometry_sha256"]==sha(Path(r["geometry_path"]))
    assert v["source_snapshot_sha256"]==r["source_snapshot_sha256"]==sha(Path(r["source_snapshot_path"]))
    assert v["counts_as_complete_candidate_geometry"] is False
    assert v["component_resolution"]=={
        "event_footprint":"NOT_ASSERTED",
        "hydraulic_capacity":"UNKNOWN",
        "official_basin_polygon":"REPRODUCIBLE_OFFICIAL_GEOMETRY",
        "unresolved_component":"quebrada San Agustín",
        "unresolved_component_geometry":"NOT_ASSERTED",
    }
    g=load(Path(r["geometry_path"]))
    assert len(g["features"])==1
    props=g["features"][0]["properties"]
    assert props["official_hydrologic_unit_code"]=="13718"
    assert props["official_hydrologic_unit_name"]=="Cuenca Acarí"
    assert props["official_area_km2"]==c["official_parent_identity"]["official_area_km2"]==4293.0766
    assert props["hydrologic_role"]=="OFFICIAL_BASIN_BOUNDARY_NOT_EVENT_FOOTPRINT"
    assert props["unresolved_component"]=="quebrada San Agustín"
    assert props["counts_as_complete_candidate_geometry"] is False
    assert props["loaded_into_operational_calculation"] is False
    assert props["carries_alert_values"] is False
    assert props["carries_risk_classification"] is False
    assert props["outlet"] is None
    assert props["decision_thresholds"] is None
    assert props["hydraulic_factors"] is None
    assert c["summary"]["official_parent_geometry_reused"]==1
    assert c["summary"]["new_geometry_assets_created"]==0

def test_base_discovery_dependency_is_internal_and_verified_against_the_real_inventory():
    c=load(CFG)
    dep=c["base_discovery_dependency"]
    assert set(dep)=={"dependency_type","path","base_schema_version","discovery_id","official_unit_code","merge_order"}
    assert not any("pull_request" in k or k.startswith("future_") for k in dep)
    assert "future" not in c["purpose"].lower()
    assert dep["dependency_type"]=="INTERNAL_REPOSITORY_FILE"
    assert Path(dep["path"])==BASE and BASE.is_file()
    base=load(BASE)
    assert dep["base_schema_version"]==base["schema_version"]
    rows=[x for x in base["official_basin_hierarchy"] if x["discovery_id"]==dep["discovery_id"]]
    assert len(rows)==1
    parent=rows[0]
    assert dep["discovery_id"]=="arequipa_acari"
    assert parent["official_unit_code"]==dep["official_unit_code"]=="13718"
    identity=c["official_parent_identity"]
    assert identity["discovery_id"]==parent["discovery_id"]
    assert identity["official_unit_code"]==parent["official_unit_code"]
    assert identity["name"]==parent["name"]=="Cuenca Acarí"
    # Reusing the frozen polygon does not rewrite or promote the inventory row.
    assert parent["entity_role"]==identity["entity_role"]=="OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
    assert parent["parent_geometry_asset"] is None
    assert parent["parent_map_publishable"] is False
    assert parent["activation_gate"]=="BLOCKED"
    assert parent["decision_thresholds"] is None and parent["hydraulic_factors"] is None
    assert c["map_binding_policy"]["new_discovery_parent_registry_update_in_this_pr"] is False

def test_san_agustin_stays_an_unresolved_component_and_no_discovery_child_exists():
    c=load(CFG)
    comp=c["existing_candidate_unresolved_component"]
    review=load(REVIEW)
    assert Path(comp["identity_review_path"])==REVIEW
    assert comp["candidate_id"]==review["candidate_id"]=="arequipa_acari_san_agustin"
    assert comp["component_id"]==review["component_id"]=="quebrada_san_agustin"
    assert comp["review_status"]==review["review_status"]=="TERRITORIAL_IDENTITY_BOUNDED_HYDROLOGIC_IDENTITY_UNRESOLVED"
    interp=review["scientific_interpretation"]
    for key in UNSUPPORTED:
        assert comp[key] is False, key
        assert interp[key] is False, key
    assert comp["component_role"]=="UNRESOLVED_LOCAL_COMPONENT_OF_EXISTING_CANDIDATE_NOT_A_DISCOVERY_CHILD"
    assert comp["new_discovery_child_created"] is False
    assert comp["discovery_child_id"] is None

    # No discovery child for San Agustín anywhere: not in the bridge, not in the inventory.
    assert "arequipa_san_agustin" not in json.dumps(c, ensure_ascii=False).replace("arequipa_acari_san_agustin", "")
    base=load(BASE)
    assert not any(s.get("parent_basin_id")=="arequipa_acari" for s in base["local_discovery_systems"])
    child_ids=[ch["child_id"] for s in base["local_discovery_systems"] for ch in s.get("children", [])]
    assert not any("agustin" in x for x in child_ids)
    assert "agust" not in json.dumps(base, ensure_ascii=False).lower()

    s=c["summary"]
    assert s["local_children_promoted"]==0
    assert s["new_discovery_children_created"]==0
    assert s["unresolved_components_resolved"]==0
    guards=c["scientific_guards"]
    assert all(guards.values())
    for key in ("unresolved_component_is_not_hydrologic_child","protection_reach_endpoints_are_not_channel_geometry","no_routing_to_rio_acari_inference"):
        assert guards[key] is True

def test_candidate_contract_stays_draft_partial_blocked_and_reach_endpoints_are_not_geometry():
    c=load(CFG)
    comp=c["existing_candidate_unresolved_component"]
    contract=load(Path(comp["candidate_contract_path"]))
    assert Path(comp["candidate_contract_path"])==CONTRACT
    assert contract["candidate_id"]=="arequipa_acari_san_agustin"
    assert contract["contract_status"]=="DRAFT"
    assert contract["assets"]["geometry"]["status"]=="PARTIAL"
    assert contract["assets"]["geometry"]["path"]==c["reused_frozen_geometry"]["geometry_path"]
    assert contract["validation"]["activation_gate"]=="BLOCKED"
    assert contract["decision_thresholds"] is None and contract["hydraulic_factors"] is None
    assert contract["operational_alerting_enabled"] is False
    notes=" ".join(contract["notes"])
    assert "remain separate unresolved components; no cross-component routing is assumed" in notes
    assert "No reproducible official geometry for quebrada San Agustín is normalized in IRFEN." in notes

    review=load(REVIEW)
    assert review["san_agustin_reference"]["coordinate_role"]=="PROJECT_PROTECTION_REACH_ENDPOINTS_ONLY"
    forbidden=review["forbidden_uses"]
    assert "draw a straight channel line between the two protection-reach endpoints" in forbidden
    assert "infer a hydrologic connection to Río Acarí from shared provincial or administrative context" in forbidden
    implication=review["candidate_implication"]
    assert implication["san_agustin_component_remains_separate"] is True
    assert implication["map_action"]=="NO_NEW_GEOMETRY"
    # The bridge copies no coordinate and carries no geometry of its own.
    text=json.dumps(c, ensure_ascii=False)
    for token in ("easting", "northing", "coordinates", "LineString", "Polygon"):
        assert token not in text
    for key in ("PPRRD", "protection-reach endpoints", "no routing to Río Acarí"):
        assert key in comp["do_not_infer"]
