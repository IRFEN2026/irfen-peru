import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "site/data/phase2/sources/santa_2011_treatment/ana_santa_2011_documentary_gate_v0_1.json"

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

def test_santa_2011_documentary_gate_fails_closed():
    doc = json.loads(GATE.read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["component_id"] == "rio_santa_lower_reach"
    qa = doc["documentary_geometry_qa"]
    assert qa["critical_points_reported"] == 24
    assert qa["axis_coordinate_table_present"] is True
    assert qa["datum"] is None
    assert qa["utm_zone"] is None
    assert qa["epsg"] is None
    assert qa["reprojection_allowed"] is False
    assert qa["map_eligible"] is False
    assert qa["pdf_digitization_as_final_geometry_forbidden"] is True

def test_santa_2011_design_model_is_not_capacity_or_threshold():
    doc = json.loads(GATE.read_text(encoding="utf-8"))
    ctx = doc["hydraulic_design_context"]
    assert ctx["model"] == "HEC-RAS"
    assert ctx["design_model_values_are_current_capacity"] is False
    assert ctx["design_model_values_are_historical_observed_capacity"] is False
    assert ctx["design_model_values_are_irfen_thresholds"] is False
    assets = doc["original_assets_status"]
    assert all(value == "MISSING" for value in assets.values())
