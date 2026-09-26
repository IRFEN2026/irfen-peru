import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/tumbes_zorritos_pprrd_additional_discovery_v0_1.json"


def load():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_additional_candidates_are_independent_and_unmapped():
    x = load()
    expected = {"sechurita", "los_pozos", "nueva_esperanza", "mal_paso_01", "mal_paso_02"}
    assert set(x["discovery_candidates"]) == expected
    for row in x["discovery_candidates"].values():
        assert row["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
        assert row["outlet_status"] == "UNRESOLVED"
        assert row["activation_verified"] is False
        assert row["map_publishable"] is False


def test_nueva_esperanza_stays_ambiguous_until_adjudicated():
    row = load()["discovery_candidates"]["nueva_esperanza"]
    assert row["candidate_type"] == "NAMED_RAVINE_OR_SECTOR_CONTEXT"
    assert "REQUIRES_RAVINE_VS_SECTOR_ADJUDICATION" in row["identity_status"]


def test_territorial_projects_do_not_become_children():
    x = load()
    assert set(x["territorial_references_not_hydrologic_children"]) == {
        "El Milagro 2", "Los Pinos Sur", "AA.HH. Cruz de Motupe", "Barrio 25 de Noviembre"
    }
    g = x["guards"]
    assert g["project_reference_is_hydrologic_child"] is False
    assert g["territorial_reference_is_outlet"] is False


def test_fail_closed_research_guards():
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
    g = x["guards"]
    assert g["documentary_name_is_geometry"] is False
    assert g["prevention_activity_is_event"] is False
    assert g["works_define_historical_capacity"] is False
    assert g["child_event_transfer_allowed"] is False
    assert g["regional_activation_count_can_be_distributed_to_children"] is False
    assert g["approximate_geometry_allowed"] is False
