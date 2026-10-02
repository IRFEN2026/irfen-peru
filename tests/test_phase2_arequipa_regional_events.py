import json
from pathlib import Path

CFG = Path("config/phase2_arequipa_regional_events_v0_1.json")

def load():
    return json.loads(CFG.read_text(encoding="utf-8"))

def test_safety_contract():
    c = load()
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["test_mode"] == "TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"] == "BLOCKED"
    assert c["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    assert c["summary"]["geometry_assets_published"] == 0
    assert c["summary"]["new_operational_zones"] == 0

def test_named_events_are_fail_closed():
    c = load()
    events = {x["id"]: x for x in c["direct_named_events"]}
    assert len(events) == 8
    assert events["arequipa_panteon_2024_01_24"]["child_id"] == "arequipa_panteon_quequena"
    assert events["arequipa_umahuato_2024_03_08"]["child_id"] == "arequipa_umahuato_choco"
    assert events["arequipa_allachaya_2024_01_25"]["child_id"] == "arequipa_allachaya_chachas"
    assert events["arequipa_lucha_2024_01_19"]["child_id"] == "arequipa_lucha_alca"
    assert events["arequipa_ranrata_2026_02_19"]["child_id"] == "arequipa_ranrata_tomepampa"
    assert events["arequipa_huaylla_2026_01_24"]["child_id"] == "arequipa_huaylla_characato"
    assert events["arequipa_utupara_2026_02"]["time"] is None
    for e in events.values():
        assert e["geometry_asset"] is None
        assert e["map_publishable"] is False

def test_joint_source_wording_is_not_split_into_fake_independent_events():
    c = load()
    e = next(x for x in c["direct_named_events"] if x["id"] == "arequipa_anas_coy_gamarra_2023_03_20")
    assert e["child_ids"] == ["arequipa_anas_coy", "arequipa_gamarra"]
    assert e["joint_source_wording_preserved"] is True

def test_sources_cover_all_event_records():
    c = load()
    source_ids = {s["id"] for s in c["sources"]}
    assert {e["source_id"] for e in c["direct_named_events"]} <= source_ids
