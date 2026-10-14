import copy
import hashlib
import json
from pathlib import Path

CFG=Path("config/phase2_ica_grande_parent_geometry_bridge_v0_1.json")
BASE=Path("config/phase2_south_coast_ica_arequipa_discovery_v0_1.json")
CONTRACT=Path("site/data/validation/phase2_zone_contracts/ica_palpa_changuillo.json")

GRANDE_ID="ica_rio_grande_palpa_nasca"
GRANDE_CODE="1372"
YAUCA_SYSTEM="ica_rio_grande_local_ravines"
YAUCA_CHILDREN=("ica_san_jose_de_curis","ica_san_isidro_de_macchanga")
YAUCA_EVENT="ica_yauca_rosario_2024_03_16"
UNRESOLVED="UNRESOLVED_PARENT_HYDROGRAPHIC_ASSIGNMENT"
PARENT_KEYS=("parent_basin_id","parent_uh_code","parent_discovery_id","official_unit_code","expected_parent_uh_code","expected_parent_discovery_id")

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def sha(p):
    raw=(json.dumps(load(p),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    return hashlib.sha256(raw).hexdigest()

def yauca_bindings_to_grande(bridge, base):
    """Every way the withdrawn Yauca del Rosario -> Cuenca Grande UH 1372 binding could come
    back, directly or by implication. Returns a list of violations; empty means clean."""
    found=[]
    system=next(x for x in base["local_discovery_systems"] if x["discovery_id"]==YAUCA_SYSTEM)

    # 1. Inventory: the system itself.
    if system.get("parent_basin_id") is not None:
        found.append(f"system parent_basin_id={system['parent_basin_id']}")
    if system.get("parent_assignment_status")!=UNRESOLVED:
        found.append("system parent_assignment_status is not unresolved")
    pa=system.get("parent_assignment") or {}
    if pa.get("status")!=UNRESOLVED:
        found.append("parent_assignment.status is not unresolved")
    if pa.get("reassigned_to") is not None:
        found.append(f"reassigned_to={pa.get('reassigned_to')}")
    if pa.get("candidate_parent_basin_ids")!=[]:
        found.append(f"candidate_parent_basin_ids={pa.get('candidate_parent_basin_ids')}")
    if pa.get("discovery_id_is_legacy_label_not_basin_assertion") is not True:
        found.append("legacy-label flag missing")

    # 2. Inventory: the two ravines.
    children={x["child_id"]:x for x in system.get("children",[])}
    for child_id in YAUCA_CHILDREN:
        child=children.get(child_id)
        if child is None:
            found.append(f"{child_id} missing from its system")
            continue
        if child.get("parent_assignment_status")!=UNRESOLVED:
            found.append(f"{child_id} parent_assignment_status is not unresolved")
        for key in PARENT_KEYS:
            if child.get(key) in (GRANDE_ID, GRANDE_CODE):
                found.append(f"{child_id}.{key}={child.get(key)}")
    # The ravines must not appear under any other system either.
    for other in base["local_discovery_systems"]:
        if other["discovery_id"]==YAUCA_SYSTEM:
            continue
        for child in other.get("children",[]):
            if child["child_id"] in YAUCA_CHILDREN:
                found.append(f"{child['child_id']} listed under {other['discovery_id']}")

    # 3. Inventory: probes must not presuppose the parent.
    for probe in base.get("hydrography_probe_contracts",[]):
        if probe.get("discovery_system_id")==YAUCA_SYSTEM:
            for key in ("expected_parent_uh_code","expected_parent_discovery_id"):
                if probe.get(key) is not None:
                    found.append(f"probe {probe.get('child_name')} {key}={probe.get(key)}")

    # 4. Bridge: must not claim the system, its ravines or its event.
    scope=bridge.get("parent_context_scope") or {}
    if scope.get("local_systems_bound_by_this_bridge")!=[]:
        found.append(f"bridge binds local systems: {scope.get('local_systems_bound_by_this_bridge')}")
    if scope.get("existing_candidate_id")!="ica_palpa_changuillo":
        found.append("bridge candidate is not ica_palpa_changuillo")
    excluded=[x for x in bridge.get("excluded_unresolved_systems",[]) if x.get("discovery_id")==YAUCA_SYSTEM]
    if len(excluded)!=1:
        found.append("bridge does not list the Yauca del Rosario system as excluded exactly once")
    else:
        row=excluded[0]
        if row.get("bound_by_this_bridge") is not False:
            found.append("excluded system marked as bound")
        if row.get("parent_basin_id_asserted_by_this_bridge") is not None:
            found.append("bridge asserts a parent for the excluded system")
        if row.get("event_transferred_to_candidate") is not False:
            found.append("bridge transfers the Yauca del Rosario event")
    names=set(YAUCA_CHILDREN)|{YAUCA_SYSTEM,YAUCA_EVENT}
    def walk(node,path=""):
        if isinstance(node,dict):
            for k,v in node.items():
                yield from walk(v,f"{path}/{k}")
        elif isinstance(node,list):
            for i,v in enumerate(node):
                yield from walk(v,f"{path}/{i}")
        elif isinstance(node,str) and node in names:
            yield path,node
    for path,value in walk(bridge):
        if not path.startswith("/excluded_unresolved_systems/"):
            found.append(f"bridge references {value} at {path}")
    for key in ("local_children_remaining_fail_closed","bound_children","local_children","territorial_events"):
        if key in bridge:
            found.append(f"bridge has block {key}")
    return found

def test_grande_bridge():
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
    assert c["official_parent_identity"]["official_unit_code"]=="1372"
    r=c["reused_frozen_geometry"]
    assert len(r["normalized_geometry_sha256"])==64
    assert len(r["source_snapshot_sha256"])==64
    assert c["homonym_and_scope_guards"]["parent_uh_match_required_for_local_assignment"] is True
    assert all(c["homonym_and_scope_guards"].values())
    assert all(c["scientific_guards"].values())
    assert c["summary"]["new_operational_zones"]==0

def test_frozen_grande_geometry_chain_is_reference_only_and_unchanged():
    c=load(CFG)
    r=c["reused_frozen_geometry"]
    assert r["existing_candidate_id"]=="ica_palpa_changuillo"
    assert r["geometry_reuse_policy"]=="REFERENCE_EXISTING_FROZEN_ASSET_DO_NOT_DUPLICATE"
    assert r["normalized_geometry_sha256"]=="a5691982accf7f3ef1458a2fdb93c05f2f779af028f2d337e00d37da309e1fef"
    assert r["source_snapshot_sha256"]=="3ac91009d90eaf5f245fb0d481b7fb0777f1d8265b081bc23601f83bf6b3de70"
    v=load(Path(r["geometry_validation_path"]))
    assert v["candidate_id"]=="ica_palpa_changuillo"
    assert v["official_unit"]=={"area_km2":10991.2703,"code":"1372","name":"Cuenca Grande"}
    assert v["normalized_geometry_path"]==r["geometry_path"]
    assert v["source_snapshot_path"]==r["source_snapshot_path"]
    assert v["normalized_geometry_sha256"]==r["normalized_geometry_sha256"]==sha(Path(r["geometry_path"]))
    assert v["source_snapshot_sha256"]==r["source_snapshot_sha256"]==sha(Path(r["source_snapshot_path"]))
    assert v["counts_as_complete_candidate_geometry"] is False
    assert v["component_resolution"]=={
        "cuenca_grande_polygon":"REPRODUCIBLE_OFFICIAL_GEOMETRY",
        "event_footprint":"NOT_ASSERTED",
        "hydraulic_capacity":"UNKNOWN",
        "local_ravines":"UNRESOLVED_NO_GEOMETRY_DRAWN",
        "palpa_changuillo_local_river_reaches":"UNRESOLVED_NO_GEOMETRY_DRAWN",
    }
    g=load(Path(r["geometry_path"]))
    assert len(g["features"])==1
    props=g["features"][0]["properties"]
    assert props["candidate_id"]=="ica_palpa_changuillo"
    assert props["official_hydrologic_unit_code"]=="1372"
    assert props["official_hydrologic_unit_name"]==c["official_parent_identity"]["official_unit_name"]=="Cuenca Grande"
    assert props["official_area_km2"]==c["official_parent_identity"]["official_area_km2"]==10991.2703
    assert props["hydrologic_role"]=="OFFICIAL_BASIN_BOUNDARY_NOT_EVENT_FOOTPRINT"
    assert props["counts_as_complete_candidate_geometry"] is False
    assert props["local_ravines_geometry_resolved"] is False
    assert props["local_river_reaches_geometry_resolved"] is False
    assert props["event_footprint_asserted"] is False
    assert props["loaded_into_operational_calculation"] is False
    assert props["carries_alert_values"] is False
    assert props["carries_risk_classification"] is False
    assert props["outlet"] is None
    assert props["decision_thresholds"] is None and props["hydraulic_factors"] is None
    assert c["summary"]["official_parent_geometry_reused"]==1
    assert c["summary"]["new_geometry_assets_created"]==0
    text=json.dumps(c,ensure_ascii=False)
    for token in ("coordinates","LineString","Polygon"):
        assert token not in text

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
    assert dep["discovery_id"]==GRANDE_ID
    assert parent["official_unit_code"]==dep["official_unit_code"]==GRANDE_CODE
    identity=c["official_parent_identity"]
    assert identity["discovery_id"]==parent["discovery_id"]
    assert identity["official_unit_code"]==parent["official_unit_code"]
    # Reusing the frozen polygon does not rewrite or promote the inventory row.
    assert parent["entity_role"]==identity["entity_role"]=="OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
    assert parent["parent_geometry_asset"] is None
    assert parent["parent_map_publishable"] is False
    assert parent["activation_gate"]=="BLOCKED"
    assert parent["decision_thresholds"] is None and parent["hydraulic_factors"] is None
    assert c["map_binding_policy"]["new_discovery_parent_registry_update_in_this_pr"] is False

def test_parent_geometry_is_context_only_for_the_palpa_changuillo_candidate():
    c=load(CFG)
    scope=c["parent_context_scope"]
    assert scope["existing_candidate_id"]==c["reused_frozen_geometry"]["existing_candidate_id"]=="ica_palpa_changuillo"
    assert scope["scope"]=="PARENT_BASIN_RESEARCH_CONTEXT_ONLY"
    for key in ("resolves_local_river_reaches","resolves_local_ravines","resolves_event_footprints","resolves_cross_component_routing"):
        assert scope[key] is False
    assert scope["local_systems_bound_by_this_bridge"]==[]
    assert Path(scope["candidate_contract_path"])==CONTRACT
    contract=load(CONTRACT)
    assert contract["candidate_id"]=="ica_palpa_changuillo"
    assert contract["contract_status"]=="DRAFT"
    assert contract["assets"]["geometry"]["status"]=="PARTIAL"
    assert contract["assets"]["geometry"]["path"]==c["reused_frozen_geometry"]["geometry_path"]
    assert contract["validation"]["activation_gate"]=="BLOCKED"
    assert contract["decision_thresholds"] is None and contract["hydraulic_factors"] is None
    assert any(
        "local river reaches, ravines, event footprints and cross-component routing remain unresolved" in note
        for note in contract["notes"]
    )
    # No discovery system hangs from Cuenca Grande in the inventory, and the bridge adds none.
    base=load(BASE)
    assert [s["discovery_id"] for s in base["local_discovery_systems"] if s.get("parent_basin_id")==GRANDE_ID]==[]
    s=c["summary"]
    assert s["local_children_promoted"]==0
    assert s["unresolved_systems_bound_to_parent"]==0
    assert s["events_transferred"]==0

def test_yauca_del_rosario_curis_and_macchanga_are_not_bound_to_cuenca_grande_1372():
    c=load(CFG)
    base=load(BASE)
    assert yauca_bindings_to_grande(c,base)==[]

    # Authoritative inventory state, pinned exactly.
    system=next(x for x in base["local_discovery_systems"] if x["discovery_id"]==YAUCA_SYSTEM)
    assert system["parent_basin_id"] is None
    assert system["parent_assignment_status"]==UNRESOLVED
    pa=system["parent_assignment"]
    assert pa["withdrawn_parent_basin_id"]==GRANDE_ID
    assert pa["withdrawn_parent_uh_code"]==GRANDE_CODE
    assert pa["reassigned_to"] is None
    assert pa["candidate_parent_basin_ids"]==[]
    assert pa["discovery_id_is_legacy_label_not_basin_assertion"] is True
    assert "ANA Cuenca Grande UH 1372" in system["homonym_guard"]
    assert "receiver name" in system["homonym_guard"]

    children={x["child_id"]:x for x in system["children"]}
    assert set(children)==set(YAUCA_CHILDREN)
    for child in children.values():
        assert child["parent_assignment_status"]==UNRESOLVED
        assert child["geometry_asset"] is None and child["outlet"] is None
        assert child["map_publishable"] is False
        assert child["activation_gate"]=="BLOCKED"
        assert child["decision_thresholds"] is None and child["hydraulic_factors"] is None
        # Child-level event attribution stands, and it is not a parent-UH statement.
        assert child["evidence_state"]=="IMPACT_CONFIRMED"
        assert child["source_ids"]==["INDECI-YAUCA-ROSARIO-2024"]

    events=system["territorial_events"]
    assert [e["event_id"] for e in events]==[YAUCA_EVENT]
    event=events[0]
    assert "Río Chico and Río Grande" in event["receiver_reference"]
    assert "official receiver identity unresolved" in event["receiver_reference"]
    assert "Do not use the receiver name 'Río Grande' to assign these ravines to ANA Cuenca Grande UH 1372 or to any other official basin." in event["do_not_infer"]

    # The bridge names the system only to exclude it.
    row=c["excluded_unresolved_systems"][0]
    assert row["discovery_id"]==YAUCA_SYSTEM
    assert row["child_ids"]==list(YAUCA_CHILDREN)
    assert row["event_ids"]==[YAUCA_EVENT]
    assert row["required_inventory_parent_basin_id"] is None
    assert row["required_inventory_parent_assignment_status"]==UNRESOLVED
    assert row["discovery_id_is_legacy_label_not_basin_assertion"] is True
    assert "does not restore that binding" in row["do_not_infer"]
    assert "does not transfer their 2024 event" in row["do_not_infer"]

def test_detector_catches_every_way_of_restoring_the_withdrawn_binding():
    def mutated(mutate):
        bridge,base=copy.deepcopy(load(CFG)),copy.deepcopy(load(BASE))
        system=next(x for x in base["local_discovery_systems"] if x["discovery_id"]==YAUCA_SYSTEM)
        mutate(bridge,base,system)
        return yauca_bindings_to_grande(bridge,base)

    assert mutated(lambda b,i,s: None)==[]
    # Inventory-side restorations.
    assert mutated(lambda b,i,s: s.update(parent_basin_id=GRANDE_ID))
    assert mutated(lambda b,i,s: s.update(parent_assignment_status="CONFIRMED"))
    assert mutated(lambda b,i,s: s["parent_assignment"].update(reassigned_to=GRANDE_ID))
    assert mutated(lambda b,i,s: s["parent_assignment"].update(candidate_parent_basin_ids=[GRANDE_ID]))
    assert mutated(lambda b,i,s: s["parent_assignment"].update(discovery_id_is_legacy_label_not_basin_assertion=False))
    for index in (0,1):
        assert mutated(lambda b,i,s,k=index: s["children"][k].update(parent_basin_id=GRANDE_ID))
        assert mutated(lambda b,i,s,k=index: s["children"][k].update(parent_uh_code=GRANDE_CODE))
        assert mutated(lambda b,i,s,k=index: s["children"][k].pop("parent_assignment_status"))
    def expect_probe(b,i,s):
        probe=next(p for p in i["hydrography_probe_contracts"] if p["discovery_system_id"]==YAUCA_SYSTEM)
        probe["expected_parent_uh_code"]=GRANDE_CODE
    assert mutated(expect_probe)
    def move_child(b,i,s):
        other=next(x for x in i["local_discovery_systems"] if x["discovery_id"]=="ica_ica_local_ravines")
        other["children"].append(copy.deepcopy(s["children"][0]))
    assert mutated(move_child)
    # Bridge-side claims, direct or implicit.
    assert mutated(lambda b,i,s: b["parent_context_scope"].update(local_systems_bound_by_this_bridge=[YAUCA_SYSTEM]))
    assert mutated(lambda b,i,s: b["excluded_unresolved_systems"][0].update(bound_by_this_bridge=True))
    assert mutated(lambda b,i,s: b["excluded_unresolved_systems"][0].update(parent_basin_id_asserted_by_this_bridge=GRANDE_ID))
    assert mutated(lambda b,i,s: b["excluded_unresolved_systems"][0].update(event_transferred_to_candidate=True))
    assert mutated(lambda b,i,s: b.update(excluded_unresolved_systems=[]))
    assert mutated(lambda b,i,s: b.update(local_children_remaining_fail_closed=[{"child_id":"ica_san_jose_de_curis"}]))
    assert mutated(lambda b,i,s: b["reused_frozen_geometry"].update(also_context_for=YAUCA_SYSTEM))
    assert mutated(lambda b,i,s: b["parent_context_scope"].update(transferred_events=[YAUCA_EVENT]))
    assert mutated(lambda b,i,s: b["parent_context_scope"].update(existing_candidate_id=YAUCA_SYSTEM))
