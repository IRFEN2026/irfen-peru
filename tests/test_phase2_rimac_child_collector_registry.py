import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "config/phase2_rimac_child_collector_registry_v0_1.json"

def load():
    return json.loads(REG.read_text(encoding="utf-8"))

def rows(doc):
    keys = doc["fields"]
    return {r[0]: dict(zip(keys, r)) for r in doc["children"]}

def test_registry_stays_fail_closed():
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
    x=d["invariant_defaults"]
    assert x["q_i_t"] is None and x["travel_time_tau"] is None
    assert x["capacity_status"]=="UNKNOWN"
    assert x["receiver_overflow_inference_allowed"] is False

def test_priority_children_are_explicit_and_separate():
    r=rows(load())
    assert set(r)=={"cashahuacra","shingolay","quirio","pedregal_san_antonio","huaycoloro","rio_seco","canto_grande_upper_branch","media_luna","jicamarca_named_channel"}
    assert r["cashahuacra"]["immediate_receiver"]=="santa_eulalia_mainstem_context"
    assert r["shingolay"]["immediate_receiver"]=="santa_eulalia_mainstem_context"
    assert r["quirio"]["immediate_receiver"]=="rimac_mainstem_receiver"
    assert r["pedregal_san_antonio"]["immediate_receiver"]=="rimac_mainstem_receiver"
    assert r["media_luna"]["immediate_receiver"]=="canto_grande_local_receiver"

def test_connectivity_does_not_promote_exact_confluence_or_receiver_response():
    d=load(); r=rows(d)
    for child in ("cashahuacra","shingolay","quirio","pedregal_san_antonio"):
        assert r[child]["collector_effect_state"]=="HYDROLOGICALLY_CONNECTED"
    assert "NOT_OFFICIAL_SURFACE_CONFLUENCE" in r["quirio"]["outlet_status"]
    assert "NOT_OFFICIAL_SURFACE_CONFLUENCE" in r["pedregal_san_antonio"]["outlet_status"]
    assert d["invariant_defaults"]["exact_receiver_confluence_resolved"] is False
    assert d["map_policy"]["registry_creates_new_geometry"] is False
    assert d["map_policy"]["risk_colors_forbidden"] is True
    assert d["map_policy"]["alerts_forbidden"] is True

def test_jicamarca_unresolved_units_remain_unresolved():
    r=rows(load())
    for child in ("huaycoloro","rio_seco","canto_grande_upper_branch","media_luna","jicamarca_named_channel"):
        assert r[child]["collector_effect_state"]=="NO_EVIDENCE"
    assert r["rio_seco"]["geometry_status"]=="MISSING_INDEPENDENT_GEOMETRY"
    assert r["jicamarca_named_channel"]["geometry_status"]=="IDENTITY_UNRESOLVED"
