import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "config/phase2_jicamarca_discovery_v0_2.json"
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_3.json"
EVENTS = ROOT / "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
SOPHY = ROOT / "config/phase2_jicamarca_sophy_access_assessment_v0_1.json"

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


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_effective_discovery_overlay_is_fail_closed_and_versioned():
    doc = load(DISCOVERY)
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["extends"] == "config/phase2_jicamarca_discovery_v0_1.json"
    assert doc["existing_huaycoloro_reference"] == "chosica_huaycoloro"
    assert doc["parent_policy"]["jicamarca_parent_is_context_only"] is True
    assert doc["parent_policy"]["parent_activation_state"] is None
    assert doc["parent_policy"]["child_evidence_promotes_parent_activation"] is False
    assert doc["parent_policy"]["synthetic_quebrada_jicamarca_unit_allowed"] is False
    assert doc["parent_policy"]["synthetic_child_geometry_union_allowed"] is False


def test_effective_2017_view_uses_event_specific_huaycoloro_without_union_or_negative_control():
    doc = load(DISCOVERY)
    assert doc["event_refinements"]["source_package"] == "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
    assert doc["event_refinements"]["coarse_2017_union_summary_in_base_contract_is_event_selection_authority"] is False
    events = {row["event_id"]: row for row in doc["event_refinements"]["events"]}
    huaycoloro = events["JICAMARCA-HUAYCOLORO-2017-01-31"]
    assert huaycoloro["component_id"] == "huaycoloro"
    assert huaycoloro["research_state"] == "DIRECT_FLOW_EVIDENCE"
    assert huaycoloro["rio_seco_activation_inferred"] is False
    assert huaycoloro["negative_evidence_for_rio_seco_created"] is False
    assert huaycoloro["event_footprint_geometry"] is None
    assert huaycoloro["rimac_overflow_inferred"] is False

    march = events["JICAMARCA-ROJ-2017-MARCH-CORRIDOR-CONTEXT"]
    assert march["child_attribution_status"] == "UNRESOLVED_NOT_UNIQUE"
    assert march["synthetic_union_event_assignment_allowed"] is False
    assert march["negative_evidence_for_unmentioned_child_allowed"] is False
    assert march["event_footprint_geometry"] is None
    assert march["rimac_overflow_inferred_from_local_child"] is False


def test_field_numbers_remain_bounded_event_evidence_not_collector_parameters():
    policy = load(DISCOVERY)["event_refinements"]["field_observation_policy"]
    for value in policy.values():
        assert value is False


def test_sophy_public_graphics_do_not_unlock_subcatchment_rainfall():
    doc = load(DISCOVERY)["monitoring_refinements"]["sophy_xband"]
    source = load(SOPHY)["data_access_assessment"]
    assert doc["public_graphical_product_evidence_identified"] is True
    assert doc["public_graphical_products_are_machine_readable_raw_or_level2_archive"] is False
    assert doc["public_machine_readable_archive_identified"] is False
    assert doc["documented_api_identified"] is False
    assert doc["raw_or_level2_data_retrieved"] is False
    assert doc["reported_range_values_km"] == [50, 60]
    assert doc["range_discrepancy_resolved"] is False
    assert doc["subcatchment_rainfall_reconstruction_allowed"] is False
    assert doc["provider_dbz_qa_values_are_irfen_thresholds"] is False
    assert source["public_machine_readable_archive_identified"] is False
    assert source["raw_or_level2_data_retrieved"] is False
    assert source["subcatchment_rainfall_reconstruction_allowed"] is False


def test_geometry_and_collector_remain_unparameterized():
    doc = load(DISCOVERY)
    geometry = doc["geometry_effect"]
    for key, value in geometry.items():
        assert value is False, key

    coupling = doc["collector_coupling_effect"]
    assert coupling["receiver_system"] == "rimac_mainstem"
    assert coupling["routing_status"] == "BLOCKED_PENDING_REPRODUCIBLE_OUTLETS_AND_ROUTING"
    for key in (
        "tributary_activation_implies_receiver_overflow",
        "outlet_or_confluence_promoted",
        "Q_i_t_promoted",
        "travel_time_promoted",
        "attenuation_promoted",
        "peak_coincidence_inferred",
        "collector_stage_or_discharge_response_promoted",
        "hydraulic_capacity_promoted",
    ):
        assert coupling[key] is False


def test_index_binds_effective_overlay_without_promotion():
    index = load(INDEX)
    for key, expected in SAFE.items():
        assert index[key] == expected
    assert index["extends"] == "config/phase2_jicamarca_evidence_index_v0_2.json"
    assert index["base_discovery_contract"] == "config/phase2_jicamarca_discovery_v0_1.json"
    assert index["effective_discovery_contract"] == "config/phase2_jicamarca_discovery_v0_2.json"
    assert index["inherited_packages_remain_authoritative"] is True
    row = index["effective_overlays"][0]
    assert row["path"] == "config/phase2_jicamarca_discovery_v0_2.json"
    for key, value in row.items():
        if key.startswith("may_"):
            assert value is False, key
    rules = index["effective_event_rules"]
    assert rules["huaycoloro_2017_01_31_child_attribution"] == "RESOLVED_HUAYCOLORO_ONLY"
    assert rules["rio_seco_2017_01_31_activation_inferred"] is False
    assert rules["march_2017_corridor_child_attribution"] == "UNRESOLVED_NOT_UNIQUE"
    assert rules["synthetic_huaycoloro_rio_seco_event_allowed"] is False
    assert rules["absence_of_report_may_define_negative_control"] is False
    assert rules["event_specific_field_numbers_may_parameterize_collector"] is False


def test_overlay_matches_closed_event_refinement_source():
    overlay = load(DISCOVERY)
    source = load(EVENTS)
    source_events = {row["event_id"]: row for row in source["event_attribution"]}
    event = next(row for row in overlay["event_refinements"]["events"] if row["event_id"] == "JICAMARCA-HUAYCOLORO-2017-01-31")
    assert source_events[event["event_id"]]["component_id"] == event["component_id"] == "huaycoloro"
    assert source_events[event["event_id"]]["rio_seco_activation_inferred"] is False
    assert source_events[event["event_id"]]["rimac_overflow_inferred"] is False
