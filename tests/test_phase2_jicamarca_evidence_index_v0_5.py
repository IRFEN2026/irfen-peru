import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_5.json"
PREVIOUS = ROOT / "config/phase2_jicamarca_evidence_index_v0_4.json"
IDENTITY = ROOT / "config/phase2_jicamarca_igp2016_local_identity_evidence_v0_1.json"
RIO_SECO_2023 = ROOT / "config/phase2_jicamarca_rio_seco_2023_event_metadata_extension_v0_1.json"
DISCOVERY = ROOT / "config/phase2_jicamarca_discovery_v0_2.json"
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


def assert_safe(obj):
    for key, expected in SAFE.items():
        assert obj[key] == expected


def test_v05_is_additive_and_binds_only_closed_evidence():
    index = load(INDEX)
    previous = load(PREVIOUS)
    identity = load(IDENTITY)
    rio_seco = load(RIO_SECO_2023)
    discovery = load(DISCOVERY)

    for obj in (index, previous, identity, rio_seco, discovery):
        assert_safe(obj)

    assert index["extends"] == PREVIOUS.relative_to(ROOT).as_posix()
    assert index["effective_discovery_contract"] == DISCOVERY.relative_to(ROOT).as_posix()
    assert index["inherited_event_monitoring_geometry_and_collector_rules_remain_authoritative"] is True
    bound = index["newly_bound_evidence"]
    assert bound["local_identity_evidence"] == IDENTITY.relative_to(ROOT).as_posix()
    assert bound["rio_seco_2023_event_metadata_extension"] == RIO_SECO_2023.relative_to(ROOT).as_posix()
    assert bound["binding_scope"] == "INDEX_AND_TRACEABILITY_ONLY_NO_GEOMETRY_OR_ROUTING_PROMOTION"


def test_local_identity_binding_preserves_child_separation_and_forbidden_shortcuts():
    index = load(INDEX)
    identity = load(IDENTITY)
    rules = index["effective_local_identity_rules"]

    assert identity["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert rules["jicamarca_parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert rules["rio_seco_is_distinct_from_colca_el_silencio_and_huaycoloro"] is True
    assert rules["synthetic_quebrada_jicamarca_unit_allowed"] is False
    assert rules["qada_colca_regulatory_geometry_may_define_rio_seco"] is False
    assert rules["report_figures_may_be_digitized_as_final_geometry"] is False
    assert rules["territorial_or_station_coordinates_may_define_outlet"] is False
    assert rules["use_A6680_as_geometry_calibration_target"] is False

    gate = identity["geometry_gate"]
    assert gate["rio_seco_channel_geometry_reproducible_from_this_source"] is False
    assert gate["rio_seco_catchment_geometry_reproducible_from_this_source"] is False
    assert gate["rio_seco_outlet_reproducible_from_this_source"] is False
    assert "use_A6680_as_geometry_calibration_target" in gate["forbidden_shortcuts"]


def test_rio_seco_2023_records_match_source_extension_and_quarantine_conflict():
    index = load(INDEX)
    source = load(RIO_SECO_2023)
    rules = index["effective_2023_rio_seco_event_rules"]

    source_accepted = {row["record_id"]: row for row in source["accepted_event_records"]}
    index_accepted = {row["record_id"]: row for row in rules["accepted_records"]}
    assert set(index_accepted) == {
        "IGP-RS2-2023-03-12T22:41:24-05:00",
        "IGP-RS1-2023-03-14T16:25:13-05:00",
    }
    assert set(index_accepted) <= set(source_accepted)
    for record_id, row in index_accepted.items():
        assert row["component_id"] == "rio_seco"
        assert row["research_state"] == "DIRECT_FLOW_EVIDENCE"
        assert row["reported_intensity_is_irfen_threshold"] is False
        assert row["may_define_discharge"] is False
        assert row["may_define_travel_time"] is False
        assert row["may_define_receiver_overflow"] is False
        assert source_accepted[record_id]["component_id"] if "component_id" in source_accepted[record_id] else source["component_id"] == "rio_seco"

    rs1 = index_accepted["IGP-RS1-2023-03-14T16:25:13-05:00"]
    assert rs1["intensity_label_conflict_must_remain_unadjudicated"] is True
    assert source_accepted[rs1["record_id"]]["intensity_label_conflict"] is True

    source_quarantine = {row["conflict_id"]: row for row in source["quarantined_source_conflicts"]}
    quarantine = rules["quarantined_records"]
    assert len(quarantine) == 1
    q = quarantine[0]
    assert q["conflict_id"] in source_quarantine
    assert q["status"] == source_quarantine[q["conflict_id"]]["status"]
    assert q["may_enter_time_aligned_event_ledger"] is False
    assert q["may_define_peak_coincidence"] is False
    assert q["may_define_travel_time"] is False
    assert q["may_define_receiver_response"] is False
    assert q["may_define_threshold"] is False

    assert rules["absence_of_report_may_define_negative_control"] is False
    assert rules["sensor_height_may_be_treated_as_discharge"] is False
    assert rules["station_label_may_define_outlet_or_confluence"] is False


def test_geometry_map_and_collector_gates_remain_fail_closed():
    index = load(INDEX)
    geometry = index["geometry_and_map_effect"]
    collector = index["collector_effect"]

    for key in (
        "new_geometry_created",
        "rio_seco_channel_or_catchment_resolved",
        "rio_seco_outlet_or_confluence_resolved",
        "parent_polygon_allowed",
        "approximate_points_allowed",
        "event_footprint_created",
        "risk_or_alert_symbology_allowed",
    ):
        assert geometry[key] is False
    assert geometry["existing_reproducible_child_lines_remain_research_context_only"] is True

    assert collector["receiver_system"] == "rimac_mainstem"
    for key in (
        "routing_enabled",
        "Q_i_t_promoted",
        "travel_time_promoted",
        "attenuation_promoted",
        "peak_coincidence_promoted",
        "hydraulic_capacity_promoted",
        "receiver_overflow_promoted",
        "tributary_activation_implies_rimac_overflow",
    ):
        assert collector[key] is False


def test_next_gate_is_local_geometry_not_threshold_or_routing_promotion():
    index = load(INDEX)
    text = " ".join(index["remaining_safe_gates"] + [index["next_safe_gate"]]).lower()
    assert "rio seco" in text
    assert "outlet" in text
    assert "colca" in text
    assert "15-mar-2023" in text
    assert "sophy" in text
    assert "routing" in text
    assert "tributary activation never implies rímac overflow" in text or "tributary activation never implies rimac overflow" in text
    assert index["decision_thresholds"] is None
    assert index["hydraulic_factors"] is None
