import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_colan_child_identity_v0_2.json"
SRC = ROOT / "site/data/phase2/sources/piura_colan_official_evidence_v0_1.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_colan_child_identity_refinement_fails_closed():
    p = load(PKG)
    assert p["deployment_status"] == "RESEARCH_ONLY"
    assert p["test_mode"] == "TEST_ONLY"
    assert p["production_use"] is False
    assert p["production_ready"] is False
    assert p["operational_alerting_enabled"] is False
    assert p["activation_gate"] == "BLOCKED"
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None
    assert p["map_materialization_allowed"] is False

def test_official_child_set_includes_nine_de_diciembre():
    p = load(PKG)
    assert set(p["children"]) == {
        "Centenario", "Libertad", "Arroyo Mio", "9 de Diciembre", "Salaverry",
        "Cahuide", "Atahualpa", "Bolognesi", "Grau", "Sucre"
    }

def test_parenthetical_names_do_not_trigger_alias_merge():
    p = load(PKG)
    pairs = {tuple(x["names"]): x for x in p["naming_ambiguities"]}
    assert pairs[("Libertad", "Centenario")]["merge_allowed"] is False
    assert pairs[("9 de Diciembre", "Salaverry")]["merge_allowed"] is False
    assert pairs[("Bolognesi", "Grau")]["merge_allowed"] is False

def test_context_sources_are_not_promoted_to_event_or_outlet_truth():
    p = load(PKG)
    g = p["scientific_guards"]
    assert g["vulnerability_inventory_is_event_ledger"] is False
    assert g["evacuation_zone_is_observed_event_footprint"] is False
    assert g["vulnerable_population_point_is_outlet"] is False
    assert g["parenthetical_map_title_authorizes_alias_merge"] is False
    assert g["absence_of_report_is_negative"] is False
    assert g["synthetic_colan_basin_allowed"] is False

def test_official_source_registry_keeps_explicit_forbidden_inferences():
    s = load(SRC)
    assert s["deployment_status"] == "RESEARCH_ONLY"
    assert s["activation_gate"] == "BLOCKED"
    ids = {x["source_id"] for x in s["sources"]}
    assert {
        "ANA-COLAN-VULNERABLE-REPORT-2015-2016",
        "ANA-COLAN-CENTENARIO-LIBERTAD-ARROYO-2016",
        "ANA-COLAN-9D-SALAVERRY-CAHUIDE-ATAHUALPA-2016",
        "ANA-COLAN-ROUTE-CENTENARIO-2015",
        "ANA-COLAN-ROUTE-LIBERTAD-CENTENARIO-2015",
        "ANA-COLAN-ROUTE-9D-SALAVERRY-2015",
        "ANA-COLAN-ROUTE-BOLOGNESI-GRAU-2015",
        "ANA-COLAN-ROUTE-SUCRE-2015",
    }.issubset(ids)
    for source in s["sources"]:
        assert source["admissible_claims"]
        assert source["forbidden_inferences"]
