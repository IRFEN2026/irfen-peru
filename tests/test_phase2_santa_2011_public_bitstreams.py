import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "site/data/phase2/source_assessments/santa_2011_public_bitstream_inventory_v0_1.json"

def test_santa_2011_public_bitstream_inventory_stays_fail_closed():
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

def test_santa_2011_public_record_does_not_promote_missing_model_assets():
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    original = next(x for x in data["repository_record"]["bitstreams"] if x["role"] == "ORIGINAL")
    assert original["name"] == "ANA0001097.pdf"
    assert original["size_bytes"] == 5981714
    assert original["checksum_algorithm"] == "MD5"
    assert original["checksum"] == "b920108b7054aa77f164b979ea618ec0"
    search = data["model_asset_search"]
    assert search["hec_ras_project_listed"] is False
    assert search["hec_georas_project_listed"] is False
    assert search["dem_or_tin_listed_as_separate_bitstream"] is False
    assert search["cross_sections_listed_as_separate_bitstream"] is False
    assert "not evidence" in search["inference_limit"].lower()
    assert data["scientific_effect"]["exact_model_geometry_reproducible_from_public_assets"] is False
    assert data["scientific_effect"]["map_geometry_promotion_allowed"] is False
