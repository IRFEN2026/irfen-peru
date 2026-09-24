import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_paita_talara_vichayito_chicama_context_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def by_id(cfg, discovery_id):
    return next(x for x in cfg["systems"] if x["discovery_id"] == discovery_id)


def test_global_phase2_safety_contract_is_fail_closed():
    cfg = load()
    for key, value in SAFE.items():
        assert cfg[key] == value
    rules = cfg["global_rules"]
    assert rules["parent_is_context_only"] is True
    assert rules["child_activation_does_not_activate_parent"] is True
    assert rules["no_synthetic_union_geometry"] is True
    assert rules["no_approximate_points"] is True
    assert rules["critical_point_is_not_event"] is True
    assert rules["intervention_is_not_event"] is True
    assert rules["work_or_design_is_not_historical_capacity"] is True
    assert rules["absence_of_report_is_not_negative_control"] is True
    assert rules["threshold_transfer_between_basins_forbidden"] is True
    assert rules["receiver_river_response_must_be_modelled_separately"] is True


def test_paita_is_separate_from_colan_and_keeps_mechanisms_split():
    cfg = load()
    paita = by_id(cfg, "piura_paita_urban_pluvial_ravines")
    assert "piura_colan_bajo_chira_local_ravines" in paita["must_not_merge_with"]
    assert paita["parent_geometry"] is None
    assert paita["parent_map_publishable"] is False

    children = {x["child_id"]: x for x in paita["children"]}
    expected = {
        "paita_el_zanjon",
        "paita_nueva_esperanza",
        "paita_la_piscina",
        "paita_la_catarata",
        "paita_villa_naval",
        "paita_alta_closed_depressions",
    }
    assert expected <= set(children)
    assert children["paita_alta_closed_depressions"]["unit_role"] == "URBAN_PLUVIAL_STORAGE_MECHANISM"
    assert children["paita_el_zanjon"]["unit_role"] == "LOCAL_DRAINAGE_AXIS"
    assert all(x["geometry_asset"] is None for x in children.values())
    assert all(x["map_publishable"] is False for x in children.values())


def test_paita_event_ledger_does_not_promote_regional_window_or_all_tributaries():
    cfg = load()
    paita = by_id(cfg, "piura_paita_urban_pluvial_ravines")
    ledger = paita["event_ledger"]
    fen98 = next(x for x in ledger if x["window"] == "1997-1998")
    assert fen98["component"] is None
    assert fen98["status"] == "METEOROLOGICAL_CONDITIONS_PRESENT"

    y2017 = [x for x in ledger if x["window"] == "2017"]
    assert {x["component"] for x in y2017} == {
        "paita_el_zanjon",
        "paita_alta_closed_depressions",
    }
    assert not any(x["component"] in {
        "paita_nueva_esperanza",
        "paita_la_piscina",
        "paita_la_catarata",
        "paita_villa_naval",
    } for x in y2017)


def test_talara_parinas_is_hydrologically_separate_from_mancora_organos():
    cfg = load()
    talara = by_id(cfg, "piura_talara_parinas_local_ravines")
    assert "piura_mancora_los_organos_coastal_ravines" in talara["must_not_merge_with"]
    children = {x["child_id"]: x for x in talara["children"]}
    assert {"talara_quebrada_parinas", "talara_quebrada_acholado"} <= set(children)
    assert children["talara_quebrada_parinas"]["geometry_asset"] is None
    assert children["talara_quebrada_acholado"]["geometry_asset"] is None
    assert children["talara_quebrada_acholado"]["evidence_state"] != "DIRECT_FLOW_EVIDENCE"
    assert children["talara_quebrada_acholado"]["evidence_state"] != "IMPACT_CONFIRMED"


def test_vichayito_is_explicit_but_remains_hydrologically_unknown():
    cfg = load()
    v = by_id(cfg, "piura_vichayito_local_hydrology")
    assert v["parent_corridor_reference"] == "piura_mancora_los_organos_coastal_ravines"
    assert v["official_territorial_identity"] == "CONFIRMED"
    assert v["hydrologic_identity"] == "UNKNOWN"
    assert v["activation_status"] == "UNKNOWN"
    assert v["geometry_status"] == "UNKNOWN"
    assert v["geometry_asset"] is None
    assert v["outlet"] is None
    assert v["map_publishable"] is False
    assert "Quebrada Fernandez" in v["must_not_inherit_events_from"]
    assert "Mancora" in v["must_not_inherit_events_from"]


def test_chicama_cartavio_and_santiago_are_context_nodes_not_activation_units():
    cfg = load()
    chicama = by_id(cfg, "lalibertad_chicama_cartavio_santiago_context_nodes")
    nodes = {x["node_id"]: x for x in chicama["nodes"]}
    assert "chicama_cartavio_15" in nodes
    assert "chicama_santiago_de_cao_critical_points" in nodes
    for node in nodes.values():
        assert node["activation_eligible"] is False
        assert node["event_status"] == "NOT_AN_EVENT"
        assert node["capacity_status"] == "UNKNOWN"
        assert node["geometry_asset"] is None
        assert node["map_publishable"] is False
        assert node["activation_gate"] == "BLOCKED"
        assert node["decision_thresholds"] is None
        assert node["hydraulic_factors"] is None

    ctx = chicama["intervention_context"]
    assert ctx["intervention_is_event"] is False
    assert ctx["intervention_defines_historical_capacity"] is False
    assert ctx["critical_point_defines_observed_flood"] is False


def test_every_local_child_or_context_node_keeps_phase2_null_hydraulics_and_blocked_gate():
    cfg = load()
    for system in cfg["systems"]:
        assert system["activation_gate"] == "BLOCKED"
        assert system["decision_thresholds"] is None
        assert system["hydraulic_factors"] is None
        for child in system.get("children", []):
            assert child["activation_gate"] == "BLOCKED"
            assert child["decision_thresholds"] is None
            assert child["hydraulic_factors"] is None
        for node in system.get("nodes", []):
            assert node["activation_gate"] == "BLOCKED"
            assert node["decision_thresholds"] is None
            assert node["hydraulic_factors"] is None


def test_map_policy_is_context_only_until_reproducible_geometry_exists():
    cfg = load()
    policy = cfg["map_policy"]
    assert policy["parents"] == "CONTEXT_GREY_ONLY"
    assert policy["children"] == "PUBLISH_ONLY_WITH_REPRODUCIBLE_GEOMETRY"
    assert policy["territorial_nodes"] == "CONTEXT_ONLY"
    assert policy["critical_points"] == "CONTEXT_ONLY"
    assert policy["risk_colours_forbidden"] is True
    assert policy["alert_semantics_forbidden"] is True
