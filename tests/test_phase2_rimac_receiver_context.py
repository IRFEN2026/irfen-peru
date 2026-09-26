import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "config/phase2_rimac_receiver_context_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_receiver_project_scope_remains_context_only():
    d = load()
    for key, value in SAFE.items():
        assert d[key] == value
    r = d["rimac_receiver_project_context"]
    assert r["official_project_reach_count"] == 10
    assert r["approx_total_project_length_km"] == 63.5
    assert r["individual_reach_ids"] == []
    assert r["individual_reach_geometries"] == []
    assert r["channel_axis_status"] == "MISSING_NOT_INFERRED_FROM_PROJECT_SCOPE"
    assert r["exact_reach_boundaries_status"] == "MISSING_NOT_INFERRED_FROM_PROJECT_SCOPE"
    assert r["capacity_status"] == "UNKNOWN"
    assert r["historical_overflow_evidence"] == []
    assert r["receiver_response"] is None
    assert r["map_eligible"] is False

def test_named_quebradas_are_identity_context_not_new_hydrologic_units():
    d = load()
    c = d["institutional_named_quebrada_context"]
    assert c["adjudicated_local_units_added_to_coupling_registry"] == 0
    by_source = {x["source_id"]: x for x in c["sources"]}
    assert len(by_source["MUNI_LURIGANCHO_2026_07_20_TEN_PRIORITY_QUEBRADAS"]["names"]) == 10
    assert "Rayito del Sol" in by_source["ANIN_2026_07_14_SIX_QUEBRADAS_MARKET_SCOPE"]["names"]
    assert by_source["ANA_2017_04_11_DYNAMIC_BARRIERS_CONTEXT"]["event_attribution_requires_separate_event_registry"] is True
    rec = {tuple(x["labels"]): x["status"] for x in c["name_reconciliation"]}
    assert rec[("Corrales","Rayito del Sol","Rayo de Sol–Corrales")] == "CROSS_SOURCE_RELATIONSHIP_UNRESOLVED_NOT_MERGED"

def test_no_map_or_capacity_promotion():
    d = load()
    assert d["map_updates"] == {
        "new_geometries_published": 0,
        "new_receiver_reaches_published": 0,
        "new_local_units_published": 0,
    }
    text = " ".join(d["forbidden"]).lower()
    assert "synthetic equal reaches" in text
    assert "project scope as channel axis" in text
    assert "historical hydraulic capacity" in text
    assert "receiver response" in text
    assert "rímac overflow" in text
