import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "site/data/phase2/source_assessments/casma_minam_n7_all_nine_live_observations_v0_1.json"

def load():
    return json.loads(DOC.read_text(encoding="utf-8"))

def test_all_nine_exact_codes_are_recorded_without_map_promotion():
    d = load()
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None
    assert [x["code"] for x in d["observations"]] == [
        "1375961","1375962","1375963","1375964","1375965",
        "1375966","1375967","1375968","1375969",
    ]
    assert d["adjudication"]["exact_code_match_count"] == 9
    assert d["adjudication"]["polygon_geometry_count"] == 9
    assert d["adjudication"]["map_publication_authorized"] is False

def test_attribute_drift_is_preserved_not_silently_tolerated():
    d = load()
    a = d["adjudication"]
    assert a["strict_2007_area_equivalence_passed"] is False
    assert a["current_service_geometry_is_exact_2007_geometry"] is False
    assert a["current_service_is_original_uh_pfas100_bytes"] is False
    assert a["raw_feature_bytes_frozen"] is False
    assert a["raw_response_sha256_frozen"] is False
    assert a["topology_union_adjudicated"] is False

def test_live_observation_values_are_bounded_and_traceable():
    d = load()
    assert d["source"]["github_actions_run_id"] == 36292439777
    assert d["source"]["github_actions_job_id"] == 108544977635
    assert d["source"]["query_script_head_sha"] == "eb03ca3f9a4d1fcc6bdfca497704ec7993d79cfc"
    for row in d["observations"]:
        assert row["geometry_type"] == "Polygon"
        minx, miny, maxx, maxy = row["bbox_wgs84"]
        assert -79.2 <= minx <= maxx <= -77.0
        assert -10.2 <= miny <= maxy <= -8.4
        assert row["service_area_km2"] > 0
