import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTX = ROOT / "site/data/phase2/sources/piura_mancora_fernandez_topology_context_v0_1.json"

def test_mancora_fernandez_topology_is_fail_closed():
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

def test_fernandez_textual_receiver_does_not_create_geometry():
    f = json.loads(CTX.read_text(encoding="utf-8"))["quebrada_fernandez"]
    assert f["downstream_name"] == "Fernández"
    assert f["reported_final_receiver"] == "Océano Pacífico"
    assert f["exact_outlet_coordinate_status"] == "UNRESOLVED"
    assert f["reproducible_vector_geometry_available"] is False
    assert f["map_materialization_allowed"] is False
    assert f["topology_interpretation_status"] == "SOURCE_TEXT_PRESERVED_NO_SYNTHETIC_BRANCHING"

def test_la_capilla_remains_independent():
    p = json.loads(CTX.read_text(encoding="utf-8"))["la_capilla_policy"]
    assert p["keep_separate_from_fernandez"] is True
    assert p["topology_from_this_source"] == "NOT_ESTABLISHED"
    assert p["event_from_this_source"] is False
