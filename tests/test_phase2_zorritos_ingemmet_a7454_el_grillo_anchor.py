import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"site/data/phase2/sources/tumbes_zorritos_ingemmet_a7454_el_grillo_anchor_v0_1.json"

def test_el_grillo_anchor_is_context_only():
    x=json.loads(PATH.read_text(encoding="utf-8"))
    assert x["component_id"]=="el_grillo"
    assert x["deployment_status"]=="RESEARCH_ONLY"
    assert x["test_mode"]=="TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"]=="BLOCKED"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    assert x["anchor"]["utm_zone"]=="17S"
    assert x["anchor"]["northing_m"]==9592175
    assert x["anchor"]["easting_m"]==534001
    g=x["scientific_guards"]
    assert g["anchor_is_channel_geometry"] is False
    assert g["anchor_is_outlet"] is False
    assert g["anchor_is_catchment_geometry"] is False
    assert g["sector_critical_is_event_footprint"] is False
    assert g["map_publishable"] is False
