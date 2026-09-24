import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_1.json"
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_1.json"

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


def assert_safe(doc):
    for key, expected in SAFE.items():
        assert doc[key] == expected


def test_union_contract_is_fail_closed():
    c = load(CFG)
    assert_safe(c)
    assert c["existing_huaycoloro_reference"] == "chosica_huaycoloro"
    assert c["status"].endswith("GEOMETRY_UNRESOLVED")


def test_official_topology_separates_children_and_does_not_invent_coordinates():
    t = load(CFG)["local_topology"]
    assert t["components"] == ["huaycoloro", "rio_seco"]
    assert t["components_are_distinct"] is True
    assert t["channels_join"] is True
    assert t["exact_join_coordinate"] is None
    assert t["join_is_reproducible_outlet_geometry"] is False
    assert t["direct_rimac_confluence_coordinate"] is None
    assert t["direct_rimac_connection_geometry_resolved"] is False
    assert t["synthetic_jicamarca_local_unit_created"] is False


def test_2017_field_values_remain_event_specific_observations_only():
    events = {x["event_id"]: x for x in load(CFG)["event_observations"]}
    first = events["JICAMARCA-HUAYCOLORO-2017-01-31"]
    assert first["component_id"] == "huaycoloro"
    assert first["research_state"] == "DIRECT_FLOW_EVIDENCE"
    assert first["reported_first_detection_local"] == "2017-01-31T16:04:00-05:00"
    assert first["reported_discharge_m3_s"] is None
    assert first["receiver_overflow_inferred"] is False

    field = events["JICAMARCA-HUAYCOLORO-2017-FIELD-PETRAMAS"]
    assert field["reported_estimated_discharge_m3_s"] == 72.5
    assert field["reported_segment_travel_time_min"] == 4
    assert field["observation_location_coordinate"] is None
    assert field["reported_estimated_discharge_is_Q_i_t"] is False
    assert field["reported_segment_travel_time_is_collector_routing_parameter"] is False
    assert field["transferable_to_other_events"] is False
    assert field["transferable_to_rio_seco"] is False
    assert field["transferable_to_rimac_receiver"] is False
    assert field["hydraulic_capacity_inferred"] is False


def test_collector_coupling_is_unparameterized_and_child_does_not_promote_receiver():
    cc = load(CFG)["collector_coupling"]
    assert cc["local_union_node_coordinate"] is None
    for child_id in ("huaycoloro", "rio_seco"):
        child = cc[child_id]
        assert child["outlet_or_confluence"] is None
        assert child["Q_i_t"] is None
        assert child["travel_time"] is None
        assert child["attenuation"] is None
        assert child["quality"] == "UNKNOWN"
    assert cc["collector_stage_or_discharge_response"] is None
    assert cc["peak_coincidence"] is None
    assert cc["hydraulic_capacity"] is None
    assert cc["tributary_activation_implies_union_activation"] is False
    assert cc["tributary_activation_implies_rimac_overflow"] is False


def test_map_does_not_publish_approximate_union_or_duplicate_huaycoloro():
    mp = load(CFG)["map_policy"]
    assert mp["publish_union_point_now"] is False
    assert mp["publish_approximate_union_point"] is False
    assert mp["publish_petramas_point_now"] is False
    assert mp["publish_approximate_petramas_point"] is False
    assert mp["publish_new_huaycoloro_geometry"] is False
    assert mp["reuse_existing_huaycoloro_by_reference"] is True
    assert mp["publish_rio_seco_child_only_after_reproducible_geometry"] is True
    assert mp["risk_or_alert_symbology_allowed"] is False


def test_evidence_index_blocks_parameter_promotion():
    idx = load(INDEX)
    assert_safe(idx)
    path = "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_1.json"
    rows = {x["path"]: x for x in idx["packages"]}
    row = rows[path]
    assert row["role"] == "IGP_LOCAL_UNION_TOPOLOGY_AND_EVENT_SPECIFIC_FIELD_OBSERVATION"
    for key in (
        "may_define_exact_union_coordinate",
        "may_define_outlet",
        "may_define_Q_i_t",
        "may_transfer_reported_discharge",
        "may_transfer_reported_segment_travel_time",
        "may_define_hydraulic_capacity",
        "may_promote_receiver_overflow",
    ):
        assert row[key] is False
    assert idx["collector_effect"] == "NO_Q_TRAVEL_TIME_ATTENUATION_OR_RECEIVER_RESPONSE_PROMOTION"
