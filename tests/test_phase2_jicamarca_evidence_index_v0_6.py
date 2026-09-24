import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_evidence_index_v0_6.json"
BOUND = ROOT / "config/phase2_jicamarca_indeci2013_confluence_topology_v0_1.json"
PREV = ROOT / "config/phase2_jicamarca_evidence_index_v0_5.json"

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


def load(path=CFG):
    return json.loads(path.read_text(encoding="utf-8"))


def test_index_extends_closed_v05_and_binds_existing_files():
    doc = load()
    assert PREV.exists()
    assert BOUND.exists()
    assert doc["extends"] == "config/phase2_jicamarca_evidence_index_v0_5.json"
    assert doc["newly_bound_evidence"]["documentary_confluence_topology"] == "config/phase2_jicamarca_indeci2013_confluence_topology_v0_1.json"
    assert doc["newly_bound_evidence"]["binding_scope"] == "IMMEDIATE_DOWNSTREAM_TOPOLOGY_CONTEXT_ONLY_NO_GEOMETRY_ROUTING_OR_OPERATIONAL_PROMOTION"


def test_scientific_guards_remain_strict():
    doc = load()
    for key, expected in SAFE.items():
        assert doc[key] == expected
    hierarchy = doc["effective_local_hierarchy"]
    assert hierarchy["jicamarca_parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert hierarchy["huaycoloro_and_rio_seco_remain_independent_local_children"] is True
    assert hierarchy["downstream_named_jicamarca_reach_is_context_not_activation_parent"] is True
    assert hierarchy["synthetic_quebrada_jicamarca_unit_allowed"] is False
    assert hierarchy["child_geometry_union_allowed"] is False
    assert hierarchy["child_evidence_promotes_parent_activation"] is False


def test_documentary_topology_does_not_resolve_geometry():
    topo = load()["effective_topology"]
    assert topo["huaycoloro_rio_seco_documentary_convergence_supported"] is True
    assert topo["immediate_downstream_named_reach"] == "jicamarca_named_channel"
    assert topo["exact_confluence_coordinate_resolved"] is False
    assert topo["rio_seco_channel_or_catchment_resolved"] is False
    assert topo["rio_seco_outlet_resolved"] is False
    assert topo["jicamarca_named_reach_geometry_resolved"] is False
    assert topo["jicamarca_to_rimac_connection_resolved"] is False
    assert topo["qada_colca_regulatory_geometry_may_define_rio_seco"] is False
    assert topo["report_figures_may_define_final_geometry"] is False
    assert topo["station_or_territorial_coordinates_may_define_outlet"] is False
    assert topo["use_A6680_as_geometry_calibration_target"] is False


def test_collector_coupling_remains_blocked_and_unparameterized():
    coupling = load()["collector_effect"]
    assert coupling["local_children"] == ["huaycoloro", "rio_seco"]
    assert coupling["immediate_downstream_context"] == "jicamarca_named_channel_after_huaycoloro_rio_seco_confluence"
    assert coupling["ultimate_receiver_context"] == "rimac_mainstem"
    assert coupling["ultimate_receiver_relation_status"] == "UNRESOLVED_BY_THIS_SOURCE"
    assert coupling["routing_enabled"] is False
    assert coupling["outlet_or_confluence_promoted"] is False
    assert coupling["Q_i_t_promoted"] is False
    assert coupling["travel_time_promoted"] is False
    assert coupling["attenuation_promoted"] is False
    assert coupling["peak_coincidence_promoted"] is False
    assert coupling["hydraulic_capacity_promoted"] is False
    assert coupling["receiver_overflow_promoted"] is False
    assert coupling["tributary_activation_implies_rimac_overflow"] is False


def test_no_new_event_negative_map_risk_or_alert_state():
    effect = load()["event_and_map_effect"]
    assert effect["new_event_evidence_created"] is False
    assert effect["new_negative_control_created"] is False
    assert effect["new_geometry_created"] is False
    assert effect["new_confluence_point_created"] is False
    assert effect["new_event_footprint_created"] is False
    assert effect["risk_or_alert_symbology_allowed"] is False
