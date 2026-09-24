import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_2.json"

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


def test_refinement_is_fail_closed_and_extends_existing_package():
    doc = load(PACKAGE)
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["extends"] == "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_1.json"
    assert doc["existing_huaycoloro_reference"] == "chosica_huaycoloro"


def test_31_jan_2017_is_local_huaycoloro_evidence_only():
    doc = load(PACKAGE)
    events = {row["event_id"]: row for row in doc["event_attribution"]}
    event = events["JICAMARCA-HUAYCOLORO-2017-01-31"]
    assert event["component_id"] == "huaycoloro"
    assert event["research_state"] == "DIRECT_FLOW_EVIDENCE"
    assert event["reported_first_detection_local"] == "2017-01-31T16:04:00-05:00"
    assert event["reported_discharge_m3_s"] is None
    assert event["reported_travel_time_min"] is None
    assert event["rio_seco_activation_inferred"] is False
    assert event["rimac_overflow_inferred"] is False


def test_petramas_field_numbers_are_event_specific_not_routing_parameters():
    doc = load(PACKAGE)
    events = {row["event_id"]: row for row in doc["event_attribution"]}
    event = events["JICAMARCA-HUAYCOLORO-2017-FIELD-PETRAMAS"]
    assert event["component_id"] == "huaycoloro"
    assert event["reported_estimated_discharge_m3_s"] == 72.5
    assert event["reported_segment_travel_time_min"] == 4
    assert event["reported_estimated_discharge_is_Q_i_t"] is False
    assert event["reported_segment_travel_time_is_collector_routing_parameter"] is False
    assert event["transferable_to_rio_seco"] is False
    assert event["transferable_to_rimac_receiver"] is False
    assert event["hydraulic_capacity_inferred"] is False


def test_march_corridor_context_does_not_force_child_attribution_or_negative_controls():
    doc = load(PACKAGE)
    events = {row["event_id"]: row for row in doc["event_attribution"]}
    event = events["JICAMARCA-ROJ-2017-MARCH-CORRIDOR-CONTEXT"]
    assert event["component_attribution_complete"] is False
    assert event["synthetic_union_event_assignment_allowed"] is False
    assert event["negative_evidence_for_unmentioned_child_allowed"] is False
    assert event["rimac_overflow_inferred_from_local_child"] is False


def test_adjudication_and_collector_effect_remain_blocked():
    doc = load(PACKAGE)
    adjudication = doc["adjudication"]
    assert adjudication["huaycoloro_and_rio_seco_are_distinct_local_children"] is True
    assert adjudication["31_jan_2017_huaycoloro_attribution_resolved"] is True
    assert adjudication["31_jan_2017_rio_seco_activation_supported_by_this_package"] is False
    assert adjudication["absence_of_rio_seco_report_is_negative_evidence"] is False
    assert adjudication["exact_huaycoloro_rio_seco_confluence_coordinate"] is None
    assert adjudication["exact_confluence_geometry_resolved"] is False
    assert adjudication["downstream_rimac_connection_geometry_resolved"] is False
    for value in doc["collector_coupling_effect"].values():
        assert value is False
    for value in doc["map_effect"].values():
        assert value is False


def test_evidence_index_registers_refinement_without_promotion():
    index = load(INDEX)
    path = "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
    row = next(item for item in index["packages"] if item["path"] == path)
    assert row["resolves_31_jan_2017_child_as_huaycoloro"] is True
    for key in (
        "may_infer_rio_seco_activation_from_huaycoloro_event",
        "may_treat_unmentioned_child_as_negative",
        "may_define_exact_union_coordinate",
        "may_define_outlet",
        "may_define_Q_i_t",
        "may_transfer_reported_discharge",
        "may_transfer_reported_segment_travel_time",
        "may_define_hydraulic_capacity",
        "may_promote_receiver_overflow",
        "may_create_map_geometry",
    ):
        assert row[key] is False
