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
