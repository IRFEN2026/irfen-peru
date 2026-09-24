import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_rio_seco_2023_event_metadata_extension_v0_1.json"

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


def test_phase2_guards_remain_fail_closed():
    doc = load()
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["status"] == "BOUNDED_RIO_SECO_EVENT_METADATA_EXTENSION_WITH_SOURCE_CONFLICT_QUARANTINE"
    assert doc["geometry_effect"] == "NONE"
    assert doc["map_effect"] == "NONE"


def test_only_consistent_dates_enter_accepted_event_records():
    doc = load()
    rows = {row["record_id"]: row for row in doc["accepted_event_records"]}
    assert set(rows) == {
        "IGP-RS2-2023-03-12T22:41:24-05:00",
        "IGP-RS1-2023-03-14T16:25:13-05:00",
    }
    for row in rows.values():
        assert row["source_header_date"] == row["source_data_date"]
        assert row["research_state"] == "DIRECT_FLOW_EVIDENCE"
        assert row["reported_discharge_m3_s"] is None
        assert row["source_reported_intensity_is_irfen_threshold"] is False
        assert row["source_reported_reference_is_reproducible_outlet"] is False
        assert row["station_label_is_reproducible_outlet"] is False
        assert row["station_label_is_reproducible_confluence"] is False
        assert row["may_infer_discharge"] is False
        assert row["may_infer_travel_time"] is False
        assert row["may_infer_attenuation"] is False
        assert row["may_infer_receiver_overflow"] is False
        assert row["event_report_sha256"] is None
        assert row["binary_frozen_in_repo"] is False


def test_rs1_intensity_conflict_is_preserved_not_adjudicated():
    rows = {row["record_id"]: row for row in load()["accepted_event_records"]}
    rs1 = rows["IGP-RS1-2023-03-14T16:25:13-05:00"]
    assert rs1["reported_intensity_field"] == "Alta"
    assert rs1["reported_intensity_narrative"] == "media"
    assert rs1["intensity_label_conflict"] is True
    assert rs1["intensity_conflict_may_be_resolved_by_choosing_one_label"] is False


def test_explicit_flow_confirmation_does_not_create_q_or_threshold():
    rows = {row["record_id"]: row for row in load()["accepted_event_records"]}
    rs2 = rows["IGP-RS2-2023-03-12T22:41:24-05:00"]
    assert rs2["source_explicit_flow_confirmation"] is True
    assert rs2["reported_height_m"] is None
    assert rs2["reported_discharge_m3_s"] is None
    assert rs2["source_reported_intensity_is_irfen_threshold"] is False
    assert rs2["may_infer_discharge"] is False


def test_internal_date_conflict_is_quarantined_from_time_alignment():
    conflicts = load()["quarantined_source_conflicts"]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["conflict_id"] == "IGP-RS1-FILENAME-HEADER-VS-DATA-DATE-2023-03-15"
    assert conflict["filename_date"] == "2023-03-15"
    assert conflict["source_header_date"] == "2023-03-15"
    assert conflict["source_data_date"] == "2023-03-14"
    assert conflict["status"] == "QUARANTINED_SOURCE_INTERNAL_DATE_CONFLICT_DO_NOT_TIME_ALIGN"
    assert conflict["may_enter_time_aligned_event_ledger"] is False
    assert conflict["may_be_deduplicated_against_other_rs1_reports_without_source_reconciliation"] is False
    assert conflict["may_define_peak_coincidence"] is False
    assert conflict["may_define_travel_time"] is False
    assert conflict["may_define_receiver_response"] is False
    assert conflict["may_define_threshold"] is False


def test_qa_blocks_negative_controls_routing_and_receiver_inference():
    doc = load()
    qa = doc["qa_rules"]
    assert qa["source_header_and_data_date_mismatch_fails_closed_for_time_alignment"] is True
    assert qa["source_intensity_internal_conflict_is_preserved_not_adjudicated"] is True
    assert qa["reported_intensity_is_not_irfen_threshold"] is True
    assert qa["sensor_height_is_not_discharge"] is True
    assert qa["station_label_is_not_outlet"] is True
    assert qa["station_reference_is_not_outlet"] is True
    assert qa["same_day_or_nearby_station_records_do_not_define_travel_time"] is True
    assert qa["same_day_child_records_do_not_define_receiver_peak_coincidence"] is True
    assert qa["absence_of_report_is_not_negative_control"] is True

    coupling = doc["collector_coupling"]
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["quality"] == "UNKNOWN"
    assert coupling["peak_coincidence"] is None
    assert coupling["receiver_stage_or_discharge_response"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
