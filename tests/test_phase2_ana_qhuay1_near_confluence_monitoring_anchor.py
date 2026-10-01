import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "config/phase2_ana_qhuay1_near_confluence_monitoring_anchor_v0_1.json"


def load():
    return json.loads(P.read_text(encoding="utf-8"))


def test_qhuay1_anchor_is_fail_closed_and_research_only():
    d = load()
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None

    a = d["monitoring_anchor"]
    assert a["station_id"] == "QHuay1"
    assert a["waterbody"] == "Quebrada Huaycoloro"
    assert a["coordinate_reference_system"] == "WGS84_UTM_ZONE_18S"
    assert a["easting_m"] == 287433
    assert a["northing_m"] == 8670443
    assert a["distance_before_documented_confluence_m"] == 40
    assert a["coordinate_role"] == "MONITORING_POINT_NOT_CONFLUENCE"
    assert a["official_near_confluence_monitoring_anchor"] is True
    assert a["exact_surface_confluence_confirmed"] is False
    assert a["exact_surface_confluence_coordinate"] is None
    assert a["exact_outlet_coordinate"] is None
    assert a["official_channel_axis_geometry"] is None
    assert a["catchment_geometry"] is None
    assert a["reproducible_map_geometry_recovered"] is False


def test_qhuay1_anchor_does_not_enable_routing_capacity_overflow_or_thresholds():
    d = load()
    c = d["coupling_context"]
    assert c["local_unit_id"] == "huaycoloro"
    assert c["documentary_receiver"] == "Rio Rimac"
    assert c["documentary_receiver_relation_supported"] is True
    assert c["exact_confluence_geometry_resolved"] is False
    assert c["routing_method"] is None
    assert c["q_i_t"] is None
    assert c["travel_time_tau"] is None
    assert c["attenuation_or_storage"] is None
    assert c["receiver_response"] is None
    assert c["receiver_capacity"] == "UNKNOWN"
    assert c["receiver_overflow_inferred"] is False

    o = d["observation_semantics"]
    assert o["station_role"] == "WATER_QUALITY_MONITORING_POINT"
    assert o["is_flow_gauge"] is False
    assert o["is_stage_gauge"] is False
    assert o["is_event_activation_sensor"] is False
    assert o["may_be_used_as_hydraulic_capacity_observation"] is False
    assert o["may_be_used_as_irfen_decision_threshold"] is False
    assert o["may_be_used_as_exact_confluence_without_independent_geometry"] is False

    a = d["adjudication"]
    assert a["strengthens_huaycoloro_receiver_relation_to_rimac"] is True
    assert a["freezes_official_near_confluence_monitoring_anchor"] is True
    for key in (
        "resolves_exact_surface_confluence",
        "resolves_exact_outlet",
        "resolves_channel_axis",
        "resolves_catchment_geometry",
        "creates_map_geometry",
        "enables_child_routing",
        "enables_travel_time_estimation",
        "establishes_receiver_capacity",
        "establishes_receiver_overflow",
        "creates_irfen_decision_threshold",
    ):
        assert a[key] is False

    assert d["map_updates"]["new_geometries_published"] == 0
    assert d["map_updates"]["new_nodes_published"] == 0
