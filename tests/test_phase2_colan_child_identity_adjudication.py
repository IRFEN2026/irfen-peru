import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "site/data/phase2/sources/piura_colan_child_identity_notes_v0_1.json"
REFS = ROOT / "site/data/phase2/sources/piura_colan_child_identity_source_refs_v0_1.json"
ADJ = ROOT / "site/data/phase2/source_assessments/piura_colan_child_alias_adjudication_v0_1.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_colan_child_identity_notes_fail_closed():
    n = load(NOTES)
    assert n["deployment_status"] == "RESEARCH_ONLY"
    assert n["test_mode"] == "TEST_ONLY"
    assert n["production_use"] is False
    assert n["production_ready"] is False
    assert n["operational_alerting_enabled"] is False
    assert n["activation_gate"] == "BLOCKED"
    assert n["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert n["decision_thresholds"] is None
    assert n["hydraulic_factors"] is None
    assert n["map_materialization_allowed"] is False
    assert n["geometry_status"].startswith("MISSING_")
    assert n["outlet_status"] == "UNRESOLVED"

def test_colan_ten_children_remain_distinct():
    n = load(NOTES)
    assert n["child_names"] == [
        "Centenario", "Libertad", "Arroyo Mío", "9 de Diciembre", "Salaverry",
        "Cahuide", "Atahualpa", "Bolognesi", "Grau", "Sucre"
    ]
    assert n["identity_rule"] == "KEEP_DISTINCT_PENDING_REPRODUCIBLE_CHANNEL_CROSSWALK"

def test_source_context_does_not_create_hydrologic_truth():
    r = load(REFS)
    assert set(r["source_ids"]) == {
        "ANA-COLAN-VULNERABILITY-2016-2017",
        "ANA-COLAN-EVACUATION-MAPS-2015",
        "ANA-DU015-COLAN-2023",
    }
    assert r["scientific_rule"] == "SOURCE_CONTEXT_DOES_NOT_CREATE_GEOMETRY_OUTLET_EVENT_OR_THRESHOLD"

def test_grouped_titles_and_chira_context_fail_closed():
    a = load(ADJ)
    assert a["status"] == "KEEP_DISTINCT_PENDING_REPRODUCIBLE_CHANNEL_CROSSWALK"
    assert a["grouped_title_is_merge_proof"] is False
    assert a["chira_basin_context_children"] == ["9 de Diciembre", "Atahualpa"]
    assert a["chira_basin_context_is_direct_receiver_proof"] is False
