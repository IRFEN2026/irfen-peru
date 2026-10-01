import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "site/data/phase2/source_assessments/casma_inrena_uh_pfas100_original_vector_provenance_v0_1.json"

def test_uh_pfas100_provenance_is_fail_closed_and_count_discrepancy_is_not_a_gate():
    data = json.loads(DOC.read_text(encoding="utf-8"))
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None
    vector = data["original_vector_description"]
    assert vector["expected_shapefile"] == "Uh_pfas100.shp"
    assert vector["datum"] == "WGS84"
    assert vector["reliability_percent"] == 92
    discrepancy = data["source_internal_count_discrepancy"]
    assert discrepancy["metadata_section_element_count"] == 1266
    assert discrepancy["process_and_conclusions_element_count"] == 1268
    assert discrepancy["adjudication"] == "DO_NOT_USE_POLYGON_COUNT_AS_ACCEPTANCE_GATE"
    assert data["public_repository_bitstream_inventory"]["shapefile_or_zip_listed"] is False
    assert data["casma_recovery_effect"]["original_inrena_vector_bytes_recovered"] is False
    assert data["casma_recovery_effect"]["pdf_digitization_authorized"] is False
    assert data["casma_recovery_effect"]["map_publication_enabled"] is False
