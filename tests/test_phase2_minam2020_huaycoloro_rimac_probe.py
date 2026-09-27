import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_phase2_minam2020_huaycoloro_rimac.py"

spec = importlib.util.spec_from_file_location("minam_probe", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

def test_query_is_exact_named_feature_probe():
    url = mod.query_url()
    assert "NOM_RIO%3D%27HUAYCOLORO%27" in url
    assert "NOM_RIO%3D%27RIMAC%27" in url
    assert "returnGeometry=true" in url
    assert "outSR=4326" in url
    assert "f=geojson" in url

def test_fail_closed_unavailable_state():
    d = mod.build_unavailable(mod.SourceAccessError("timed out"))
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None
    assert d["query_completed"] is False
    assert d["candidate_counts"] == {"huaycoloro": None, "rimac": None}
    assert d["matching_feature_count"] is None
    assert d["access"]["zero_candidates_inferred"] is False
    assert d["access"]["hydrologic_absence_inferred"] is False

def test_literal_intersection_is_candidate_only():
    data = {
        "type": "FeatureCollection",
        "features": [
            {"type":"Feature","properties":{"OBJECTID":1,"NOM_RIO":"HUAYCOLORO"},
             "geometry":{"type":"LineString","coordinates":[[0,0],[2,2]]}},
            {"type":"Feature","properties":{"OBJECTID":2,"NOM_RIO":"RIMAC"},
             "geometry":{"type":"LineString","coordinates":[[0,2],[2,0]]}},
        ],
    }
    d = mod.build(b"{}", data)
    assert d["query_completed"] is True
    assert d["candidate_counts"] == {"huaycoloro": 1, "rimac": 1}
    assert d["matching_objectids"] == [1,2]
    assert len(d["literal_intersection_candidates"]) == 1
    row = d["literal_intersection_candidates"][0]
    assert row["scientific_status"] == "GEOMETRIC_INTERSECTION_CANDIDATE_NOT_ADJUDICATED_CONFLUENCE"
    g = d["guards"]
    assert g["name_match_confirms_local_identity"] is False
    assert g["literal_line_intersection_confirms_official_confluence"] is False
    assert g["exact_huaycoloro_rimac_confluence_resolved"] is False
    assert g["routing_enabled"] is False
    assert g["travel_time_enabled"] is False
    assert g["flow_or_capacity_inference_enabled"] is False
    assert g["overflow_inference_enabled"] is False
    assert g["map_publish_enabled"] is False
    assert g["zero_query_result_may_be_inferred_as_hydrologic_absence"] is False

def test_zero_completed_query_is_not_absence():
    d = mod.build(b'{"type":"FeatureCollection","features":[]}',
                  {"type":"FeatureCollection","features":[]})
    assert d["query_completed"] is True
    assert d["candidate_counts"] == {"huaycoloro": 0, "rimac": 0}
    assert d["matching_feature_count"] == 0
    assert d["guards"]["zero_query_result_may_be_inferred_as_hydrologic_absence"] is False
