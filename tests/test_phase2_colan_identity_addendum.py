import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"
ADD = ROOT / "site/data/phase2/sources/piura_colan_identity_addendum_v0_1.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_colan_nine_december_is_registered_as_named_child_only():
    inv = load(INV)
    u = next(x for x in inv["discovery_units"] if x["discovery_id"] == "piura_colan_bajo_chira_local_ravines")
    assert "Quebrada 9 de Diciembre" in u["hydrologic_components"]
    add = load(ADD)
    assert add["qa"]["identity_only"] is True
    assert add["qa"]["geometry_promotion"] is False
    assert add["qa"]["event_promotion"] is False

def test_colan_bolognesi_grau_alias_does_not_auto_merge_children():
    add = load(ADD)
    src = next(x for x in add["sources"] if x["source_id"] == "ANA-COLAN-BLOGRAU-EVAC-2015")
    assert src["auto_merge_bolognesi_grau"] is False

def test_colan_guardrails_remain_fail_closed():
    add = load(ADD)
    assert add["status"] == "RESEARCH_ONLY"
    assert add["test_mode"] == "TEST_ONLY"
    assert add["production_use"] is False
    assert add["production_ready"] is False
    assert add["operational_alerting_enabled"] is False
    assert add["activation_gate"] == "BLOCKED"
    assert add["decision_thresholds"] is None
    assert add["hydraulic_factors"] is None
