import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "site/data/phase2/source_assessments/casma_minam_n7_candidate_service_v0_1.json"


def test_casma_minam_candidate_route_stays_fail_closed():
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


def test_casma_minam_route_requires_exact_n7_replay_before_geometry():
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    assert data["source"]["layer_id"] == 1
    assert data["source"]["spatial_reference"] == 4326
    assert "geoJSON" in data["source"]["supported_query_formats"]
    assert "NIVEL7" in data["source"]["fields_relevant_to_replay"]
    assert data["target_codes"] == [
        "1375961","1375962","1375963","1375964","1375965",
        "1375966","1375967","1375968","1375969"
    ]
    probe = data["probe_status"]
    assert probe["service_metadata_publicly_resolved"] is True
    assert probe["n7_fields_exposed_by_layer_schema"] is True
    assert probe["exact_target_feature_queries_completed"] is False
    assert probe["exact_target_features_retrieved"] is False
    assert probe["exact_geometry_bytes_frozen"] is False
    effect = data["scientific_effect"]
    assert effect["n7_geometry_recovered"] is False
    assert effect["map_publication_enabled"] is False
    assert effect["pdf_digitization_authorized"] is False
    assert data["acceptance_gate"]["required_feature_count_per_code"] == 1
