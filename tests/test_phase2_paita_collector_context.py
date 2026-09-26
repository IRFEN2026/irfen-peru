import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTX = ROOT / "site/data/phase2/sources/piura_paita_collector_context_v0_1.json"

def test_paita_collector_context_fails_closed():
    x = json.loads(CTX.read_text(encoding="utf-8"))
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None

def test_paita_named_contributors_route_to_zanjon_context_only():
    x = json.loads(CTX.read_text(encoding="utf-8"))
    c = x["collector_context"]
    assert c["main_channel"] == "El Zanjón"
    assert c["contributors"] == ["Nueva Esperanza", "La Piscina", "La Catarata", "Villa Naval"]
    assert c["reported_final_receiver"] == "Océano Pacífico"
    assert c["reproducible_vector_geometry_available"] is False
    assert c["synthetic_outlet_allowed"] is False
    assert c["travel_time_allowed"] is False
    assert c["flow_routing_allowed"] is False

def test_paita_mechanisms_and_events_are_not_conflated():
    x = json.loads(CTX.read_text(encoding="utf-8"))
    m = x["mechanism_separation"]
    assert m["paita_alta_blind_basin_pluvial_system_separate"] is True
    assert m["tributary_activation_is_not_collector_overflow"] is True
    assert m["collector_overflow_is_not_ocean_coastal_hazard"] is True
    e = x["event_policy"]
    assert e["dated_child_event_from_2021_report"] is False
    assert e["historical_rainfall_transfer_to_child_forbidden"] is True
