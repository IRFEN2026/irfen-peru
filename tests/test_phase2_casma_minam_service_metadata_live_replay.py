import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "site/data/phase2/source_assessments/casma_minam_service_metadata_live_replay_v0_1.json"


def load():
    return json.loads(ASSET.read_text(encoding="utf-8"))


def test_live_minam_metadata_replay_stays_fail_closed():
    data = load()
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None


def test_live_minam_metadata_does_not_promote_unfrozen_geometry():
    data = load()
    source = data["source"]
    assert source["geometry_type"] == "esriGeometryPolygon"
    assert source["source_spatial_reference_wkid"] == 32718
    assert source["advertised_extent_spatial_reference_wkid"] == 4326
    assert "Query" in source["capabilities"]
    assert "geoJSON" in source["supported_query_formats"]
    gate = data["exact_recovery_gate"]
    assert gate["metadata_endpoint_accessible"] is True
    assert gate["exact_code_feature_responses_frozen"] is False
    assert gate["raw_response_sha256_frozen"] is False
    assert gate["all_nine_identity_checks_passed"] is False
    assert gate["all_nine_area_checks_passed"] is False
    assert gate["all_nine_geometry_checks_passed"] is False
    assert gate["normalized_geometry_created"] is False
    assert gate["map_registry_modified"] is False
    disposition = data["scientific_disposition"]
    assert disposition["live_service_metadata_is_geometry"] is False
    assert disposition["map_eligible"] is False
    assert disposition["activation_geometry"] is False
    assert disposition["pdf_digitization_allowed"] is False


def test_live_minam_replay_targets_exact_casma_n7_codes():
    data = load()
    assert data["exact_recovery_gate"]["target_codes"] == [
        "1375961", "1375962", "1375963", "1375964", "1375965",
        "1375966", "1375967", "1375968", "1375969",
    ]
    assert data["independent_qa"]["original_vector_target"] == "Uh_pfas100"
    assert data["independent_qa"]["original_vector_public_bytes_recovered"] is False
