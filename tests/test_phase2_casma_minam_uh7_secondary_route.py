import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "site/data/phase2/source_assessments/casma_minam_uh7_secondary_route_v0_1.json"

def test_secondary_casma_route_stays_fail_closed():
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

def test_secondary_casma_route_requires_exact_replay():
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    assert data["source"]["layer_name"] == "Subcuencas (UH 7)"
    assert data["source"]["source_wkid"] == 32718
    assert "NIVEL7" in data["source"]["required_fields_observed"]
    assert "CODIGO" in data["source"]["required_fields_observed"]
    assert data["target_codes"] == [str(x) for x in range(1375961, 1375970)]
    probe = data["probe_status"]
    assert probe["service_metadata_publicly_resolved"] is True
    assert probe["exact_target_feature_queries_completed"] is False
    assert probe["exact_geometry_bytes_frozen"] is False
    gate = data["acceptance_gate"]
    assert gate["required_feature_count_per_code"] == 1
    assert gate["require_ana_inrena_2007_name_and_area_qa"] is True
    assert gate["require_raw_response_bytes_and_sha256"] is True
    assert gate["require_cross_service_adjudication_if_geometries_disagree"] is True
    assert gate["pdf_digitization_allowed"] is False
    assert data["scientific_effect"]["map_publication_enabled"] is False
