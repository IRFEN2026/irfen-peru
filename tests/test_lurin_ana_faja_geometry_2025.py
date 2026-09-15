import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "site/data/validation/phase2_research_evidence/ana_lurin_faja_marginal_antioquia_2025.geojson"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_lurin_cieneguilla.json"


def test_lurin_ana_faja_geometry_is_research_only_context():
    geo = json.loads(GEO.read_text(encoding="utf-8"))
    meta = geo["metadata"]
    assert meta["source_point_count"] == 124
    assert meta["right_margin_points"] == 62
    assert meta["left_margin_points"] == 62
    assert meta["not_observed_flood_footprint"] is True
    assert meta["not_event_geometry"] is True
    assert meta["not_operational_threshold"] is True
    assert meta["tr100_use"] == "SOURCE_MODEL_CONTEXT_ONLY_NOT_IRFEN_THRESHOLD"
    assert len(geo["features"]) == 3
    assert geo["features"][2]["properties"]["observed_inundation"] is False


def test_lurin_contract_geometry_progress_does_not_unlock_activation():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["contract_status"] == "DRAFT"
    assert contract["deployment_status"] == "RESEARCH_ONLY"
    assert contract["production_use"] is False
    assert contract["alerting_enabled"] is False
    assert contract["decision_thresholds"] is None
    assert contract["validation"]["activation_gate"] == "BLOCKED"
    assert contract["assets"]["geometry"]["status"] == "PARTIAL"
    assert contract["assets"]["exposure"]["status"] == "MISSING"
    assert contract["hazard_model"]["mechanism_status"] == "TO_BE_RESOLVED"
