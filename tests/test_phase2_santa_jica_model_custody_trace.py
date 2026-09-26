import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "site/data/phase2/source_assessments/santa_jica_ana_model_custody_trace_v0_1.json"


def test_santa_jica_custody_trace_stays_fail_closed():
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None


def test_santa_jica_trace_narrows_custody_without_inventing_model_assets():
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    custody = data["custody_interpretation"]
    assert custody["confirms_santa_study_results_existed_outside_the_single_public_pdf"] is True
    assert custody["confirms_jica_received_santa_results"] is True
    assert custody["proves_jica_received_original_hecras_project"] is False
    assert custody["proves_jica_received_georas_project_or_geodatabase"] is False
    assert custody["proves_model_assets_are_currently_public"] is False
    recovery = data["recovery_status"]
    assert all(value is False for value in recovery.values())
    effect = data["scientific_effect"]
    assert effect["custody_search_scope_narrowed"] is True
    assert effect["native_axis_crs_resolved"] is False
    assert effect["exact_lower_reach_geometry_ready"] is False
    assert effect["map_publication_enabled"] is False
    assert effect["design_flow_promoted_to_capacity"] is False
    assert effect["modeled_area_promoted_to_event_footprint"] is False
