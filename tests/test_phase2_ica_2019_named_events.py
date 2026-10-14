import json
from pathlib import Path

CFG = Path("config/phase2_ica_2019_named_events_v0_1.json")

def load():
    return json.loads(CFG.read_text(encoding="utf-8"))

def test_safety_contract():
    c=load()
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    assert c["summary"]["geometry_assets_published"]==0
    assert c["summary"]["new_operational_zones"]==0

def test_event_count_and_joint_records():
    c=load()
    events={e["id"]:e for e in c["events"]}
    assert len(events)==6
    h=events["ica_huancano_huayanto_quitasol_remanso_2019_02_10"]
    assert h["reported_names"]==["Quebrada Huayanto","Quebrada Quitasol","Quebrada Remanso"]
    assert "MULTI_NAMED_RAVINE" in h["attribution"]
    rg=events["ica_rio_grande_san_jacinto_santa_rosa_2019_02_08"]
    assert len(rg["reported_names"])==2
    ll=events["ica_llipata_carlos_tijero_piedras_gordas_2019_02_08"]
    assert len(ll["reported_names"])==2

def test_tulin_receiver_response_is_bounded():
    c=load()
    e=next(x for x in c["events"] if x["id"]=="ica_el_ingenio_tulin_2019_02_08")
    assert e["receiver_context"]["receiver_system"]=="Cuenca del río Grande"
    assert e["receiver_context"]["reported_response"]=="incremento del caudal"
    assert e["receiver_context"]["exact_outlet"] is None
    assert e["receiver_context"]["receiver_overflow_inferred"] is False

def test_no_event_publishes_geometry():
    c=load()
    for e in c["events"]:
        assert e["geometry_asset"] is None
        assert e["map_publishable"] is False
