import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_paita_parent_is_context_only_and_fail_closed():
    p = load(PKG)
    assert p["deployment_status"] == "RESEARCH_ONLY"
    assert p["test_mode"] == "TEST_ONLY"
    assert p["production_use"] is False
    assert p["production_ready"] is False
    assert p["operational_alerting_enabled"] is False
    assert p["activation_gate"] == "BLOCKED"
    assert p["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None
    assert p["territorial_identity"]["parent_is_context_only"] is True
    assert p["territorial_identity"]["parent_activation_synthesis_forbidden"] is True

def test_every_local_child_is_independent_and_unmapped_without_geometry():
    p = load(PKG)
    expected = {
        "el_zanjon",
        "nueva_esperanza",
        "la_piscina",
        "la_catarata",
        "villa_naval",
        "paita_alta_blind_basins",
    }
    assert expected == set(p["hydrologic_components"])
    for child in p["hydrologic_components"].values():
        assert child["map_materialization_allowed"] is False
        assert child["outlet_status"].startswith("UNKNOWN")
        assert "UNKNOWN" in child["receiver_relation"]

def test_local_hierarchy_forbids_parent_and_child_state_transfer():
    p = load(PKG)
    h = p["local_hierarchy"]
    assert h["parent_role"] == "TERRITORIAL_CONTEXT_CONTAINER_NON_ACTIVABLE"
    assert h["activation_unit_rule"] == "EACH_REPRODUCIBLE_LOCAL_CHILD_ONLY"
    assert h["parent_geometry_union_forbidden"] is True
    assert h["child_state_transfer_forbidden"] is True
    assert h["unknown_receiver_relations_must_remain_unknown"] is True
    assert h["allowed_states_are_alerts"] is False
    assert h["allowed_research_states"] == [
        "METEOROLOGICAL_CONDITIONS_PRESENT",
        "RUNOFF_RESPONSE_PLAUSIBLE",
        "DIRECT_FLOW_EVIDENCE",
        "IMPACT_CONFIRMED",
    ]

def test_historical_windows_remain_child_bounded():
    p = load(PKG)
    e83 = p["event_ledger"]["1982_1983"]
    assert e83["transfer_to_other_ravines_forbidden"] is True
    assert e83["exact_event_footprint_available"] is False
    assert e83["operational_threshold_inferred"] is False

    e98 = p["event_ledger"]["1997_1998"]
    assert e98["status"] == "UNKNOWN_NOT_NEGATIVE_CHILD_LEVEL_SOURCE_GAP"
    assert e98["local_child_activation_assigned"] is False
    assert e98["absence_of_local_report_is_negative"] is False
    assert e98["source_ids"] == []

    e17 = p["event_ledger"]["2017"]
    assert e17["transfer_to_other_ravines_forbidden"] is True
    assert e17["exact_event_footprint_available"] is False
    assert e17["operational_threshold_inferred"] is False

def test_collector_coupling_fails_closed_until_topology_and_hydrographs_exist():
    p = load(PKG)
    c = p["collector_coupling"]
    assert c["status"].startswith("BLOCKED_")
    assert c["q_i_t_allowed"] is False
    assert c["travel_time_allowed"] is False
    assert c["attenuation_allowed"] is False
    assert c["hydraulic_capacity_inference_allowed"] is False
    assert c["synthetic_receiver_assignment_forbidden"] is True
    assert c["child_activation_implies_receiver_overflow"] is False

def test_map_and_qa_prohibit_synthetic_fill():
    p = load(PKG)
    assert p["map_policy"]["parent_polygon_forbidden"] is True
    assert p["map_policy"]["child_only_after_reproducible_geometry"] is True
    assert p["map_policy"]["synthetic_union_forbidden"] is True
    assert p["map_policy"]["approximate_points_forbidden"] is True
    assert p["map_policy"]["risk_colors_forbidden"] is True
    assert p["map_policy"]["alerts_forbidden"] is True
    assert p["qa"]["documented_name_is_not_geometry"] is True
    assert p["qa"]["unknown_outlet_is_not_approximated"] is True
    assert p["qa"]["unknown_child_outcome_is_not_negative_control"] is True
