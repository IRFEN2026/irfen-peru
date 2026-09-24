import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_jicamarca_el_silencio_ana_faja_contract_v0_1.json"
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


def test_contract_is_fail_closed_and_reuses_exact_frozen_source():
    doc = load(CONTRACT)
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["component_id"] == "el_silencio"
    assert doc["source"]["source_pdf_sha256"] == "dfe7f64913d424f160ed585db69c973493dbabc5a7c3918e1671bbe412d40dd1"
    assert doc["source"]["source_reuse_policy"] == "REUSE_IMMUTABLE_FROZEN_SOURCE_BYTES_NO_REDOWLOAD_REQUIRED"
    qa = doc["qa_rules"]
    assert qa["segment_union_forbidden"] is True
    assert qa["map_eligible_as_research_context"] is True
    assert qa["map_eligible_as_activation_geometry"] is False
    for key in (
        "faja_is_event_footprint", "faja_is_catchment_polygon", "faja_is_channel_centerline",
        "faja_is_outlet_or_confluence", "faja_is_historical_hydraulic_capacity",
        "may_enable_routing", "may_define_Q_i_t", "may_define_travel_time", "may_define_attenuation",
        "may_promote_parent_activation", "may_promote_receiver_overflow", "may_publish_risk_or_alert_semantics",
    ):
        assert qa[key] is False


def test_expected_segments_are_separate_and_exact():
    doc = load(CONTRACT)
    segments = {row["segment_id"]: row for row in doc["segments"]}
    assert set(segments) == {"el_silencio_main", "el_silencio_01", "el_silencio_02"}
    assert (segments["el_silencio_main"]["right_bank_count"], segments["el_silencio_main"]["left_bank_count"]) == (73, 94)
    assert (segments["el_silencio_01"]["right_bank_count"], segments["el_silencio_01"]["left_bank_count"]) == (17, 11)
    assert (segments["el_silencio_02"]["right_bank_count"], segments["el_silencio_02"]["left_bank_count"]) == (5, 4)
    assert segments["el_silencio_02"]["count_basis"].startswith("EXACT_ANNEX_CODE_SETS")
    assert len({row["ledger_path"] for row in segments.values()}) == 3


def test_frozen_artifacts_if_bootstrapped_are_hash_bound_and_non_operational():
    doc = load(CONTRACT)
    manifest_path = ROOT / doc["manifest_path"]
    if not manifest_path.exists():
        return
    manifest = load(manifest_path)
    for key, expected in SAFE.items():
        assert manifest[key] == expected
    assert manifest["status"] == "PASS_REPRODUCIBLE_ANA_EL_SILENCIO_FAJA_CONTEXT"
    assert manifest["source_pdf_sha256"] == doc["source"]["source_pdf_sha256"]
    assert manifest["source_segments_union_performed"] is False
    assert manifest["map_eligible_as_research_context"] is True
    assert manifest["map_eligible_as_activation_geometry"] is False
    assert manifest["faja_is_event_footprint"] is False
    assert manifest["faja_is_catchment_polygon"] is False
    assert manifest["faja_is_channel_centerline"] is False
    assert manifest["faja_is_outlet_or_confluence"] is False
    assert manifest["routing_enabled"] is False
    assert manifest["Q_i_t"] is None
    assert manifest["travel_time"] is None
    assert manifest["attenuation"] is None
    assert manifest["historical_hydraulic_capacity"] is None
    assert manifest["parent_activation_promoted"] is False
    assert manifest["receiver_overflow_inferred"] is False
    assert manifest["risk_or_alert_semantics"] is False

    for segment in doc["segments"]:
        segment_id = segment["segment_id"]
        path = ROOT / segment["ledger_path"]
        assert path.is_file()
        assert digest(path) == manifest["segments"][segment_id]["coordinate_ledger_sha256"]
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        right = [row for row in rows if row["bank"] == "RIGHT"]
        left = [row for row in rows if row["bank"] == "LEFT"]
        assert len(right) == segment["right_bank_count"]
        assert len(left) == segment["left_bank_count"]
        assert {row["segment_id"] for row in rows} == {segment_id}
        assert {int(row["epsg"]) for row in rows} == {32718}

    geometry_path = ROOT / doc["geometry_path"]
    assert geometry_path.is_file()
    assert digest(geometry_path) == manifest["geometry_sha256"]
    geometry = load(geometry_path)
    for key, expected in SAFE.items():
        assert geometry["properties"][key] == expected
    assert geometry["properties"]["source_segments_union_performed"] is False
    assert geometry["properties"]["geometry_role"] == "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY"
    assert len(geometry["features"]) == 6
    assert {f["geometry"]["type"] for f in geometry["features"]} == {"LineString"}
    for feature in geometry["features"]:
        p = feature["properties"]
        assert p["event_footprint"] is False
        assert p["catchment_polygon"] is False
        assert p["channel_centerline"] is False
        assert p["outlet_or_confluence"] is False
        assert p["historical_hydraulic_capacity"] is False
        assert p["routing_parameter"] is False
        assert p["risk_or_alert_layer"] is False
