import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "config/phase2_casma_n7_recovery_candidate_v0_1.json"

EXPECTED_CODES = {f"137596{i}" for i in range(1, 10)}

def test_candidate_is_research_only_and_not_direct_official_download():
    doc = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_mode"] == "TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None
    src = doc["source"]
    assert src["classification"] == "PUBLIC_THIRD_PARTY_REDISTRIBUTION_OF_ANA_DERIVED_VECTOR"
    assert src["direct_current_ana_download"] is False
    assert src["embedded_metadata_origin"] == "Autoridad Nacional del Agua"
    assert src["archive_sha256"] == "21bc0c5661eab1091cc5d89da29a911036f5fc2a10316769bd36fbcc0edb1440"

def test_candidate_matches_all_nine_official_2007_codes_and_area_qa():
    doc = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    qa = doc["qa"]
    rows = qa["children"]
    assert {row["code"] for row in rows} == EXPECTED_CODES
    assert qa["exact_n7_count"] == 9
    assert qa["all_polygons_valid"] is True
    assert qa["polygon_overlaps_detected"] is False
    assert qa["union_is_single_polygon"] is True
    assert qa["max_absolute_child_area_delta_km2"] <= 0.5
    assert qa["max_relative_child_area_delta"] <= 0.01
    assert qa["manual_digitization_used"] is False
    assert qa["outcomes_used_for_geometry"] is False

def test_candidate_does_not_promote_hydraulic_or_operational_logic():
    doc = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    disp = doc["scientific_disposition"]
    assert disp["source_is_direct_current_official_ana_binary"] is False
    assert disp["geometry_may_be_published_only_after_freeze_replay_and_ci"] is True
    assert disp["parent_composite_polygon_forbidden"] is True
    assert disp["event_outcome_fitting_forbidden"] is True
    assert disp["outlet_travel_time_capacity_threshold_inference_forbidden"] is True
