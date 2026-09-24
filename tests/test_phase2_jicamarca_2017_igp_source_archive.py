import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_jicamarca_2017_igp_source_archive_contract_v0_1.json"
EVENTS = ROOT / "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
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


def assert_safe(obj):
    for key, value in SAFE.items():
        assert obj[key] == value


def test_archive_contract_is_bounded_to_the_three_preregistered_official_igp_pages():
    contract = load(CONTRACT)
    events = load(EVENTS)
    discovery = load(DISCOVERY)
    assert_safe(contract)
    assert_safe(events)
    assert_safe(discovery)

    assert contract["metadata_contract"] == "config/phase2_jicamarca_huaycoloro_rio_seco_union_2017_v0_2.json"
    assert contract["effective_discovery_contract"] == "config/phase2_jicamarca_discovery_v0_2.json"
    assert contract["qa_rules"]["download_only_preregistered_urls"] is True
    assert contract["qa_rules"]["all_or_nothing_archive"] is True

    event_sources = {row["source_id"]: row for row in events["sources"]}
    contract_ids = [row["source_id"] for row in contract["sources"]]
    assert contract_ids == [
        "IGP-ROJ-HUAYCOLORO-2017-02-02",
        "IGP-HUAYCOLORO-FIELD-2017-02-06",
        "IGP-ROJ-MARCH-2017-CORRIDOR-CONTEXT",
    ]
    assert len(contract_ids) == len(set(contract_ids)) == 3
    for row in contract["sources"]:
        source = event_sources[row["source_id"]]
        assert source["url"] == row["url"]
        assert source["source_role"] == row["source_role"]
        assert source["source_bytes_sha256"] is None
        assert row["url"].startswith("https://www.gob.pe/institucion/igp/noticias/")


def test_archive_is_provenance_only_and_does_not_promote_hydrology_or_routing():
    contract = load(CONTRACT)
    events = load(EVENTS)
    discovery = load(DISCOVERY)
    qa = contract["qa_rules"]

    for key in (
        "content_interpretation_during_archive",
        "archive_bytes_modify_event_attribution",
        "archive_bytes_define_negative_evidence",
        "archive_bytes_define_geometry",
        "archive_bytes_define_outlet_or_confluence",
        "archive_bytes_define_Q_i_t",
        "archive_bytes_define_travel_time",
        "archive_bytes_define_attenuation",
        "archive_bytes_define_hydraulic_capacity",
        "archive_bytes_import_thresholds",
        "archive_bytes_enable_routing",
        "archive_bytes_enable_alerting",
    ):
        assert qa[key] is False

    assert events["adjudication"]["31_jan_2017_rio_seco_activation_supported_by_this_package"] is False
    assert events["adjudication"]["absence_of_rio_seco_report_is_negative_evidence"] is False
    assert events["adjudication"]["exact_confluence_geometry_resolved"] is False
    assert events["adjudication"]["downstream_rimac_connection_geometry_resolved"] is False
    assert events["collector_coupling_effect"]["Q_i_t_promoted"] is False
    assert events["collector_coupling_effect"]["travel_time_promoted"] is False
    assert events["collector_coupling_effect"]["receiver_response_promoted"] is False

    coupling = discovery["collector_coupling_effect"]
    assert coupling["routing_status"] == "BLOCKED_PENDING_REPRODUCIBLE_OUTLETS_AND_ROUTING"
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
    assert coupling["Q_i_t_promoted"] is False
    assert coupling["travel_time_promoted"] is False
    assert coupling["attenuation_promoted"] is False
    assert coupling["hydraulic_capacity_promoted"] is False


def test_manifest_is_either_not_bootstrapped_yet_or_a_complete_fail_closed_state():
    contract = load(CONTRACT)
    archive_root = ROOT / contract["archive_root"]
    expected_files = [archive_root / row["archive_filename"] for row in contract["sources"]]

    if not MANIFEST.exists():
        assert not any(path.exists() for path in expected_files)
        return

    manifest = load(MANIFEST)
    assert_safe(manifest)
    assert manifest["partial_archive_retained"] is False
    for key in (
        "content_interpreted",
        "event_attribution_modified",
        "negative_evidence_created",
        "geometry_modified",
        "outlet_or_confluence_inferred",
        "Q_i_t_inferred",
        "travel_time_inferred",
        "attenuation_inferred",
        "hydraulic_capacity_inferred",
        "thresholds_imported",
        "routing_enabled",
        "alerting_enabled",
    ):
        assert manifest[key] is False

    if manifest["status"] == "BLOCKED_PUBLIC_OFFICIAL_SOURCE_BYTES_NOT_REPRODUCIBLE":
        assert manifest["source_count"] == 0
        assert manifest["source_probe_failures"]
        assert not any(path.exists() for path in expected_files)
        return

    assert manifest["status"] == "PASS_REPRODUCIBLE_IGP_2017_BYTE_ARCHIVE"
    assert manifest["source_count"] == 3
    rows = {row["source_id"]: row for row in manifest["sources"]}
    assert set(rows) == {row["source_id"] for row in contract["sources"]}
    for source in contract["sources"]:
        row = rows[source["source_id"]]
        path = ROOT / row["archive_path"]
        data = path.read_bytes()
        assert data
        assert row["source_url"] == source["url"]
        assert row["sha256"] == hashlib.sha256(data).hexdigest()
        assert row["bytes"] == len(data)


def test_archive_provenance_hashes_bind_the_exact_preregistered_semantic_state_when_present():
    if not MANIFEST.exists():
        return
    manifest = load(MANIFEST)
    contract = load(CONTRACT)
    assert manifest["archive_contract_sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert manifest["metadata_contract_sha256"] == hashlib.sha256(EVENTS.read_bytes()).hexdigest()
    assert manifest["effective_discovery_contract_sha256"] == hashlib.sha256(DISCOVERY.read_bytes()).hexdigest()
    assert contract["metadata_contract"] == EVENTS.relative_to(ROOT).as_posix()
    assert contract["effective_discovery_contract"] == DISCOVERY.relative_to(ROOT).as_posix()
