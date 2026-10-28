import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "site/data/phase2/source_assessments/santa_2020_igp_highres_topography_v0_1.json"


def test_santa_2020_igp_topography_control_is_fail_closed():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_mode"] == "TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None


def test_santa_2020_igp_topography_is_context_not_2011_model_geometry():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    crs = doc["survey"]["coordinate_reference"]
    assert crs["datum"] == "WGS 1984"
    assert crs["utm_zone"] == 17
    assert crs["hemisphere"] == "South"
    assert doc["products_reported"]["river_channel_dtm_resolution_cm_per_pixel"] == 29.3
    assert doc["asset_recovery"]["dtm_raster_recovered"] is False
    assert doc["asset_recovery"]["orthomosaic_recovered"] is False
    assert doc["scientific_role"]["proves_2011_ana_model_datum"] is False
    assert doc["scientific_role"]["may_replace_2011_hec_ras_geometry"] is False
    assert doc["scientific_role"]["map_publication_enabled"] is False


def test_santa_igp_2020_pdf_custody_is_hash_pinned_and_document_identity_checked():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    custody = doc["source_pdf_custody"]
    assert custody["raw_pdf_sha256"] == "e33870604c5b874fbd40c911c793fe0bbe835038c8644f91f15db5f2434d8fa4"
    assert custody["raw_pdf_bytes"] == 3614432
    assert custody["capture_workflow_run_id"] == 40645106838
    assert custody["capture_artifact_id"] == 12796579615
    assert custody["raw_pdf_stored_in_repository"] is False
    assert custody["raw_pdf_only_in_expiring_ci_artifact"] is True
    assert custody["document_content_qa"]["identity_confirmed_from_pdf_content"] is True
    assert custody["document_content_qa"]["pdf_pages"] == 22
    assert custody["document_content_qa"]["does_not_validate_2011_ana_datum"] is True
    assert custody["ana_2011_datum_established"] is False
    assert custody["model_equivalence_proven"] is False
    assert custody["map_publication_enabled"] is False


def test_santa_igp_2020_area_discrepancy_remains_unresolved_and_fail_closed():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    discrepancy = doc["source_internal_area_discrepancy"]
    totals = [observation["area_ha"] for observation in discrepancy["observations"]
              if "area_ha" in observation]
    assert 1758 in totals
    assert 1597 in totals
    assert discrepancy["discrepancy_ha"] == 161
    assert any(observation.get("component_sum_ha") == 1758
               and observation.get("component_areas_ha") == [992, 766]
               for observation in discrepancy["observations"])
    assert discrepancy["qa_disposition"] == "PRESERVE_BOTH_TOTALS_PENDING_INSTITUTIONAL_CLARIFICATION"
    assert discrepancy["effects"]["dtm_raster_recovered"] is False
    assert discrepancy["effects"]["proves_2011_ana_model_datum"] is False
    assert discrepancy["effects"]["map_publication_enabled"] is False
