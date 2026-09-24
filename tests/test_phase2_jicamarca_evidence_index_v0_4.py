import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_4.json"
PREVIOUS = ROOT / "config/phase2_jicamarca_evidence_index_v0_3.json"
ARCHIVE_CONTRACT = ROOT / "config/phase2_jicamarca_2017_igp_source_archive_contract_v0_1.json"
EVENT_METADATA = ROOT / "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
DISCOVERY = ROOT / "config/phase2_jicamarca_discovery_v0_2.json"
MANIFEST = ROOT / "site/data/phase2/sources/jicamarca_igp_2017/archive_manifest_v0_1.json"
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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_safe(obj):
    for key, expected in SAFE.items():
        assert obj[key] == expected


def test_v04_is_additive_archive_binding_over_effective_v03():
    index = load(INDEX)
    previous = load(PREVIOUS)
    assert_safe(index)
    assert_safe(previous)
    assert index["extends"] == PREVIOUS.relative_to(ROOT).as_posix()
    assert index["effective_discovery_contract"] == DISCOVERY.relative_to(ROOT).as_posix()
    assert index["inherited_event_monitoring_geometry_and_collector_rules_remain_authoritative"] is True


def test_archive_binding_matches_exact_frozen_manifest_and_source_set():
    index = load(INDEX)
    gate = index["completed_provenance_gate"]
    manifest = load(MANIFEST)
    contract = load(ARCHIVE_CONTRACT)
    assert_safe(manifest)
    assert_safe(contract)

    assert gate["archive_contract"] == ARCHIVE_CONTRACT.relative_to(ROOT).as_posix()
    assert gate["archive_manifest"] == MANIFEST.relative_to(ROOT).as_posix()
    assert manifest["status"] == gate["manifest_status_required"] == "PASS_REPRODUCIBLE_IGP_2017_BYTE_ARCHIVE"
    assert manifest["source_count"] == gate["source_count_required"] == 3
    assert manifest["partial_archive_retained"] is False

    assert gate["archive_contract_sha256"] == manifest["archive_contract_sha256"] == digest(ARCHIVE_CONTRACT)
    assert gate["metadata_contract_sha256"] == manifest["metadata_contract_sha256"] == digest(EVENT_METADATA)
    assert gate["effective_discovery_contract_sha256"] == manifest["effective_discovery_contract_sha256"] == digest(DISCOVERY)

    manifest_ids = [row["source_id"] for row in manifest["sources"]]
    contract_ids = [row["source_id"] for row in contract["sources"]]
    assert gate["source_ids"] == contract_ids
    assert set(manifest_ids) == set(contract_ids)
    assert len(manifest_ids) == len(set(manifest_ids)) == 3

    for row in manifest["sources"]:
        path = ROOT / row["archive_path"]
        data = path.read_bytes()
        assert data
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert len(data) == row["bytes"]


def test_byte_freeze_is_provenance_only_and_cannot_promote_scientific_state():
    index = load(INDEX)
    gate = index["completed_provenance_gate"]
    assert gate["use_scope"] == "PROVENANCE_ONLY_FOR_ALREADY_PREREGISTERED_OFFICIAL_2017_EVENT_SOURCES"
    for key in (
        "archive_bytes_are_new_event_interpretation",
        "archive_bytes_may_modify_child_attribution",
        "archive_bytes_may_create_negative_evidence",
        "archive_bytes_may_create_geometry",
        "archive_bytes_may_define_outlet_or_confluence",
        "archive_bytes_may_define_Q_i_t",
        "archive_bytes_may_define_travel_time",
        "archive_bytes_may_define_attenuation",
        "archive_bytes_may_define_hydraulic_capacity",
        "archive_bytes_may_import_thresholds",
        "archive_bytes_may_enable_routing",
        "archive_bytes_may_enable_alerting",
    ):
        assert gate[key] is False

    events = index["effective_event_rules"]
    assert events["huaycoloro_2017_01_31_child_attribution"] == "RESOLVED_HUAYCOLORO_ONLY"
    assert events["rio_seco_2017_01_31_activation_inferred"] is False
    assert events["march_2017_corridor_child_attribution"] == "UNRESOLVED_NOT_UNIQUE"
    assert events["synthetic_huaycoloro_rio_seco_event_allowed"] is False
    assert events["absence_of_report_may_define_negative_control"] is False
    assert events["event_specific_field_numbers_may_parameterize_collector"] is False


def test_local_geometry_routing_and_sophy_gates_remain_closed():
    index = load(INDEX)
    monitoring = index["effective_monitoring_rules"]
    geometry = index["geometry_and_map_effect"]
    collector = index["collector_effect"]

    assert monitoring["cendehua_station_identity_required_for_child_specific_direct_flow_use"] is True
    assert monitoring["sophy_public_graphics_are_raw_or_level2_archive"] is False
    assert monitoring["sophy_raw_or_level2_machine_readable_access_resolved"] is False
    assert monitoring["sophy_subcatchment_rainfall_reconstruction_allowed"] is False
    assert monitoring["provider_operational_thresholds_imported"] is False

    assert geometry["new_geometry_created"] is False
    assert geometry["parent_polygon_allowed"] is False
    assert geometry["approximate_points_allowed"] is False
    assert geometry["event_footprint_created"] is False
    assert geometry["risk_or_alert_symbology_allowed"] is False

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


def test_next_safe_gate_advances_past_byte_freeze_without_overclaiming_maturity():
    index = load(INDEX)
    text = " ".join(index["remaining_safe_gates"] + [index["next_safe_gate"]]).lower()
    assert "rio seco" in text
    assert "canto grande" in text
    assert "media luna" in text
    assert "sophy" in text
    assert "routing" in text
    assert "rímac overflow" in text or "rimac overflow" in text
    assert "freeze the remaining official 2017 source bytes" not in index["next_safe_gate"].lower()
