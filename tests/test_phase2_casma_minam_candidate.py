import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "site/data/phase2/sources/ancash_casma_minam_candidate_v0_1.json"


def test_casma_minam_candidate_is_not_geometry():
    doc = json.loads(DOC.read_text(encoding="utf-8"))
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_mode"] == "TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None
    assert doc["geometry_retrieved"] is False
    assert doc["map_publication_enabled"] is False
    assert doc["source"]["source_spatial_reference"] == 32718
    assert doc["source"]["advertised_map_extent_spatial_reference"] == 4326
    assert doc["source"]["output_spatial_reference_must_be_explicit"] is True
