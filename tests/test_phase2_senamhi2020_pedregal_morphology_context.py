import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_senamhi2020_pedregal_morphology_context_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_fail_closed():
    d=load()
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d["test_mode"]=="TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"]=="BLOCKED"
    assert d["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None

def test_morphology_without_fake_confluence_or_tau():
    u=load()["unit"]
    assert u["local_unit_id"]=="pedregal_san_antonio"
    assert u["documentary_receiver"]=="Rio Rimac"
    assert u["documentary_receiver_relation_confirmed"] is True
    assert u["source_point_of_interest_is_exact_coordinate"] is False
    assert u["exact_surface_confluence_coordinate"] is None
    assert u["official_channel_axis_geometry"] is None
    m=u["morphology"]
    assert m["drainage_area_km2"]==10.28
    assert m["perimeter_km"]==18.53
    assert m["elevation_difference_m"]==1504.31
    assert m["main_channel_length_km"]==5.66
    assert m["mean_main_channel_slope_pct"]==14.74
    assert m["mean_hillslope_slope_pct"]==50.35
    assert u["qualitative_response_conflict_status"]=="SOURCE_INTERNAL_QUALITATIVE_TENSION_NOT_RESOLVED_TO_TAU"
    assert u["travel_time_tau"] is None
    assert u["q_i_t"] is None
    assert u["receiver_response"] is None
    assert u["capacity"]=="UNKNOWN"
