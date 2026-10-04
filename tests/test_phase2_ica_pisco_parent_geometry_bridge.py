import hashlib
import json
from pathlib import Path

CFG = Path("config/phase2_ica_pisco_parent_geometry_bridge_v0_1.json")
VAL = Path("site/data/phase2/geometries/ica_pisco_san_andres_geometry_validation.json")
BASE = Path("config/phase2_south_coast_ica_arequipa_discovery_v0_1.json")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha(path):
    data = load(path)
    payload = (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_bridge_remains_fail_closed_and_research_only():
    cfg = load(CFG)
    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
    assert cfg["summary"]["new_operational_zones"] == 0


def test_bridge_matches_frozen_official_pisco_geometry_exactly():
    cfg = load(CFG)
    reused = cfg["reused_frozen_geometry"]
    validation = load(Path(reused["geometry_validation_path"]))
    assert validation["official_unit"] == {
        "area_km2": 4208.7453,
        "code": "13752",
        "name": "Cuenca Pisco",
    }
    assert validation["normalized_geometry_sha256"] == reused["normalized_geometry_sha256"]
    assert validation["source_snapshot_sha256"] == reused["source_snapshot_sha256"]
    assert canonical_sha(Path(reused["geometry_path"])) == reused["normalized_geometry_sha256"]
    assert canonical_sha(Path(reused["source_snapshot_path"])) == reused["source_snapshot_sha256"]

    geom = load(Path(reused["geometry_path"]))
    assert len(geom["features"]) == 1
    props = geom["features"][0]["properties"]
    assert props["official_hydrologic_unit_code"] == "13752"
    assert props["official_hydrologic_unit_name"] == "Cuenca Pisco"
    assert props["counts_as_complete_candidate_geometry"] is False
    assert props["loaded_into_operational_calculation"] is False
    assert props["carries_alert_values"] is False
    assert props["carries_risk_classification"] is False
    assert props["decision_thresholds"] is None
    assert props["hydraulic_factors"] is None


def test_local_pisco_children_are_not_promoted_by_parent_geometry_reuse():
    cfg = load(CFG)
    assert cfg["map_binding_policy"]["new_discovery_parent_registry_update_in_this_pr"] is False
    assert cfg["map_binding_policy"]["future_parent_style"] == "CONTEXT_GREY_ONLY"
    assert cfg["map_binding_policy"]["risk_colours_forbidden"] is True
    assert cfg["map_binding_policy"]["event_footprint_inference_forbidden"] is True

    children = {row["child_id"]: row for row in cfg["local_children_remaining_fail_closed"]}
    assert set(children) == {"ica_quitasol", "ica_paracas"}
    for row in children.values():
        assert row["geometry_asset"] is None
        assert row["outlet"] is None
        assert row["map_publishable"] is False
        assert row["event_state"] == "CRITICAL_POINT_CONTEXT_NOT_EVENT"

    guards = cfg["scientific_guards"]
    assert all(guards.values())


def test_base_discovery_dependency_is_internal_and_verified_against_the_real_inventory():
    cfg = load(CFG)
    dep = cfg["base_discovery_dependency"]
    # The base inventory is in the repository: no pull request, no "future" path.
    assert set(dep) == {
        "dependency_type", "path", "base_schema_version", "discovery_id", "official_unit_code", "merge_order",
    }
    assert not any("pull_request" in key or key.startswith("future_") for key in dep)
    assert dep["dependency_type"] == "INTERNAL_REPOSITORY_FILE"
    assert Path(dep["path"]) == BASE
    assert BASE.is_file()

    base = load(BASE)
    assert dep["base_schema_version"] == base["schema_version"]
    parents = [x for x in base["official_basin_hierarchy"] if x["discovery_id"] == dep["discovery_id"]]
    assert len(parents) == 1
    parent = parents[0]
    assert dep["discovery_id"] == "ica_pisco"
    assert parent["official_unit_code"] == dep["official_unit_code"] == "13752"

    # The bridge restates the parent identity; it must agree with the inventory and with
    # the frozen geometry validation, and must not turn the parent into anything activatable.
    identity = cfg["official_parent_identity"]
    assert identity["discovery_id"] == parent["discovery_id"]
    assert identity["official_unit_code"] == parent["official_unit_code"]
    assert identity["name"] == parent["name"] == load(VAL)["official_unit"]["name"]
    assert identity["entity_role"] == parent["entity_role"] == "OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
    assert parent["activation_gate"] == "BLOCKED"
    assert parent["decision_thresholds"] is None and parent["hydraulic_factors"] is None
    # The bridge does not rewrite the inventory: the parent row still carries no geometry asset.
    assert parent["parent_geometry_asset"] is None
    assert parent["parent_map_publishable"] is False
    assert cfg["map_binding_policy"]["new_discovery_parent_registry_update_in_this_pr"] is False
    assert cfg["summary"]["new_geometry_assets_created"] == 0


def test_parent_geometry_reuse_promotes_no_child_and_transfers_no_event():
    cfg = load(CFG)
    base = load(BASE)
    system = next(x for x in base["local_discovery_systems"] if x["discovery_id"] == "ica_pisco_local_ravines")
    assert system["parent_basin_id"] == cfg["base_discovery_dependency"]["discovery_id"]
    children = {x["child_id"]: x for x in system["children"]}
    bridge_children = {x["child_id"]: x for x in cfg["local_children_remaining_fail_closed"]}
    assert set(children) == set(bridge_children) == {"ica_quitasol", "ica_paracas"}
    for child_id, child in children.items():
        assert child["evidence_state"] == bridge_children[child_id]["event_state"] == "CRITICAL_POINT_CONTEXT_NOT_EVENT"
        assert child["geometry_asset"] is None
        assert child["outlet"] is None
        assert child["map_publishable"] is False
        assert child["activation_gate"] == "BLOCKED"
    assert cfg["summary"]["local_children_promoted"] == 0

    # The Huancano event stays unnamed and unbound, and its locally named Río Grande
    # stays separate from ANA Cuenca Grande UH 1372.
    events = system["territorial_events"]
    assert [e["event_id"] for e in events] == ["ica_huancano_2026_02_20"]
    event = events[0]
    assert event["named_child"] is None
    assert event["hydrologic_assignment_status"] == "TERRITORIAL_EVENT_PENDING_LOCAL_GEOMETRY"
    assert "ANA Cuenca Grande UH 1372" in event["do_not_infer"]
    grande = next(x for x in base["official_basin_hierarchy"] if x["official_unit_code"] == "1372")
    assert grande["discovery_id"] != cfg["base_discovery_dependency"]["discovery_id"]
    text = json.dumps(cfg, ensure_ascii=False)
    assert "1372" not in text and "huancano" not in text.lower()
