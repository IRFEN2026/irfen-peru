import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "site/data/phase2/sources/tumbes_zorritos_gore_pprrd_additional_ravines_v0_1.json"


def load():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_additional_ravines_are_identity_only():
    x = load()
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    assert {r["component_id"] for r in x["named_candidates"]} == {
        "sechurita", "los_pozos", "nueva_esperanza", "mal_paso_01", "mal_paso_02"
    }
    for row in x["named_candidates"]:
        assert row["geometry_status"] == "UNRESOLVED"
        assert row["outlet_status"] == "UNRESOLVED"
        assert row["event_status"] == "UNRESOLVED"


def test_territorial_references_are_not_promoted_to_children():
    x = load()
    assert set(x["excluded_territorial_only_references"]) == {
        "El Milagro 2", "Los Pinos Sur", "AA.HH. Cruz de Motupe", "Barrio 25 de Noviembre"
    }
    g = x["scientific_guards"]
    assert g["identity_context_is_geometry"] is False
    assert g["identity_context_is_event"] is False
    assert g["prevention_project_is_historical_event"] is False
    assert g["territorial_reference_is_hydrologic_child"] is False
    assert g["absence_is_negative"] is False
    assert g["map_publishable"] is False
