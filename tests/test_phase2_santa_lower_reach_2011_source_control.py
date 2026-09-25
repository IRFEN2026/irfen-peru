import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"site/data/phase2/sources/ancash_santa_lower_reach_2011_source_control_v0_1.json"

SAFE={
    "deployment_status":"RESEARCH_ONLY",
    "test_mode":"TEST_ONLY",
    "production_use":False,
    "production_ready":False,
    "operational_alerting_enabled":False,
    "activation_gate":"BLOCKED",
    "missing_data_rule":"UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds":None,
    "hydraulic_factors":None,
}

def load():
    return json.loads(SOURCE.read_text(encoding="utf-8"))

def test_scientific_guards_remain_fail_closed():
    d=load()
    for k,v in SAFE.items():
        assert d[k]==v
    assert d["component_id"]=="rio_santa_lower_reach"
    assert d["map_eligible"] is False
    assert d["geometry_created"] is False
    assert d["event_footprint_created"] is False
    assert d["present_day_capacity_inferred"] is False
    assert d["irfen_threshold_created"] is False

def test_crs_gap_blocks_coordinate_promotion():
    d=load()
    assert d["crs_status"]=="UNRESOLVED_DO_NOT_TRANSFORM"
    assert d["axis_table_status"].endswith("CRS_UNRESOLVED")
    assert d["critical_point_table_status"].endswith("CRS_UNRESOLVED")
    assert "Resolve datum/UTM zone" in d["next_safe_gate"]

def test_source_inconsistencies_are_not_silently_resolved():
    d=load()
    notes=" ".join(d["source_inconsistency_notes"])
    assert "0+000" in notes and "1+000" in notes
    assert "two distinct rows" in notes and "50+000" in notes
