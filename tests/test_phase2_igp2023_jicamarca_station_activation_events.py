import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "config/phase2_igp2023_jicamarca_station_activation_events_v0_1.json"


def load():
    return json.loads(P.read_text(encoding="utf-8"))


def test_station_activation_events_are_fail_closed_and_research_only():
    d = load()
    assert d["status"] == "FROZEN_RESEARCH_ONLY_STATION_LEVEL_ACTIVATION_EVENTS"
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None

    g = d["guards"]
    assert g["station_activation_is_not_collector_overflow"] is True
    assert g["station_activation_is_not_discharge"] is True
    assert g["reported_height_is_not_receiver_capacity"] is True
    assert g["event_sequence_may_not_be_used_for_travel_time_without_independent_synchronization"] is True
    assert g["internal_source_inconsistencies_must_be_preserved"] is True
    assert g["quarantined_records_may_not_be_promoted"] is True
    assert g["zero_or_missing_measurement_is_not_negative_evidence"] is True


def test_rio_seco2_events_are_frozen_exactly_without_hydraulic_promotion():
    d = load()
    events = {e["event_id"]: e for e in d["accepted_station_events"]}

    expected = {
        "igp_rio_seco2_2023-03-12T22:41:24": ("Leve", None, "Evento_12_03_2023_RS2.pdf"),
        "igp_rio_seco2_2023-03-14T16:37:37": ("Media", None, "Evento_14_03_2023_RS2.pdf"),
        "igp_rio_seco2_2023-03-15T16:27:41": ("Moderada", 0.43, "Evento_15_03_2023_RS2.pdf"),
    }

    for event_id, (intensity, height, source_file) in expected.items():
        e = events[event_id]
        assert e["local_unit_id"] == "rio_seco_jicamarca"
        assert e["station_name"] == "Rio Seco 2"
        assert e["reported_intensity_field"] == intensity
        assert e["reported_height_m"] == height
        assert e["reported_discharge"] is None
        assert e["source_file"] == source_file
        assert e["classification"] == "STATION_LEVEL_ACTIVATION_EVENT_ONLY"
        assert e["source_internal_inconsistency"] is False


def test_huaycoloro_events_preserve_source_label_and_wording_inconsistencies():
    d = load()
    events = {e["event_id"]: e for e in d["accepted_station_events"]}

    h1_12 = events["igp_huaycoloro1_2023-03-12T15:49:00"]
    assert h1_12["station_name"] == "Huaycoloro1"
    assert h1_12["reported_intensity_field"] == "Media"
    assert h1_12["reported_height_m"] is None
    assert h1_12["reported_discharge"] is None
    assert h1_12["source_internal_inconsistency"] is False

    h2_12 = events["igp_huaycoloro2_2023-03-12T17:43:00"]
    assert h2_12["station_name"] == "Huaycoloro2"
    assert h2_12["reported_intensity_field"] == "Media"
    assert h2_12["reported_height_m"] == 0.5
    assert h2_12["reported_discharge"] is None
    assert h2_12["source_internal_inconsistency"] is True
    assert h2_12["adjudicated_station_basis"] == "EXPLICIT_STATION_FIELD_PRESERVED_WITH_BODY_LABEL_MISMATCH_FLAGGED"

    h2_14 = events["igp_huaycoloro2_2023-03-14T15:24:33"]
    assert h2_14["source_internal_inconsistency"] is True
    assert h2_14["adjudicated_station_basis"] == "EXPLICIT_STATION_FIELD_PRESERVED_WITH_BODY_LABEL_MISMATCH_FLAGGED"

    h2_15 = events["igp_huaycoloro2_2023-03-15T14:44:19"]
    assert h2_15["reported_intensity_field"] == "Media"
    assert h2_15["reported_intensity_observation_text"] == "moderada"
    assert h2_15["source_internal_inconsistency"] is True

    h1_15 = events["igp_huaycoloro1_2023-03-15T15:36:56"]
    assert h1_15["reported_intensity_field"] == "Leve"
    assert h1_15["source_internal_inconsistency"] is False


def test_conflicting_records_remain_quarantined_and_cannot_drive_tau():
    d = load()
    quarantined = {e["source_file"]: e for e in d["quarantined_source_records"]}

    rs2 = quarantined["Evento_18_03_2023_RS2.pdf"]
    assert rs2["classification"] == "QUARANTINE_INTERNAL_DATE_CONFLICT"
    assert rs2["filename_or_report_date"] == "2023-03-18"
    assert rs2["internal_reported_datetime_local"] == "2023-03-15T17:21:35"
    assert rs2["may_be_frozen_as_2023_03_18_event"] is False
    assert rs2["may_be_used_for_travel_time"] is False

    hl2 = quarantined["Evento_17_03_2023_HL2.pdf"]
    assert hl2["classification"] == "QUARANTINE_INTERNAL_DATE_AND_INTENSITY_CONFLICT"
    assert hl2["filename_or_report_date"] == "2023-03-17"
    assert hl2["internal_reported_datetime_local"] == "2023-03-15T15:28:38"
    assert hl2["reported_intensity_field"] == "Media"
    assert hl2["reported_intensity_observation_text"] == "Leve"
    assert hl2["may_be_frozen_as_2023_03_17_event"] is False
    assert hl2["may_be_used_for_travel_time"] is False


def test_event_registry_does_not_resolve_geometry_routing_capacity_or_overflow():
    d = load()
    assert d["adjudication"]["accepted_station_event_count"] == 8
    assert d["adjudication"]["quarantined_source_record_count"] == 2

    for key in (
        "resolves_exact_outlet_or_confluence",
        "resolves_channel_or_catchment_geometry",
        "enables_routing",
        "enables_travel_time_estimation",
        "establishes_discharge",
        "establishes_receiver_capacity",
        "establishes_rimac_overflow",
        "creates_irfen_decision_threshold",
    ):
        assert d["adjudication"][key] is False

    c = d["corroborating_regional_context"]
    assert c["may_be_used_to_infer_child_routing"] is False
    assert c["may_be_used_to_infer_receiver_overflow"] is False

    assert d["map_updates"]["new_geometries_published"] == 0
    assert d["map_updates"]["new_nodes_published"] == 0
