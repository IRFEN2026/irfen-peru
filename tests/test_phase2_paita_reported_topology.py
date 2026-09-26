import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json"
SRC = ROOT / "site/data/phase2/sources/piura_paita_official_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_paita_topology_package_remains_fail_closed():
    p = load(PKG)
    assert p["deployment_status"] == "RESEARCH_ONLY"
    assert p["test_mode"] == "TEST_ONLY"
    assert p["production_use"] is False
    assert p["production_ready"] is False
    assert p["operational_alerting_enabled"] is False
    assert p["activation_gate"] == "BLOCKED"
    assert p["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None


def test_official_reported_topology_is_explicit_but_not_geometry():
    p = load(PKG)
    c = p["collector_coupling"]
    assert c["principal_local_collector"] == "el_zanjon"
    assert c["terminal_receiver"] == "PACIFIC_OCEAN"
    assert set(c["tributaries"]) == {
        "nueva_esperanza",
        "la_piscina",
        "la_catarata",
        "villa_naval",
    }
    assert c["exact_child_confluences_available"] is False
    assert c["exact_terminal_outlet_available"] is False
    assert c["engineered_current_routing_resolved"] is False
    assert c["q_i_t_allowed"] is False
    assert c["travel_time_allowed"] is False
    assert c["attenuation_allowed"] is False
    assert c["synthetic_receiver_assignment_forbidden"] is True
    assert p["map_policy"]["materialize_topology_as_synthetic_lines"] is False


def test_each_named_tributary_stays_independent_and_unmapped():
    p = load(PKG)
    for key in ("nueva_esperanza", "la_piscina", "la_catarata", "villa_naval"):
        child = p["hydrologic_components"][key]
        assert child["component_type"] == "NATURAL_RAVINE_TRIBUTARY"
        assert child["reported_receiver"] == "el_zanjon"
        assert child["outlet_status"] == "EXACT_CHILD_CONFLUENCE_UNRESOLVED"
        assert child["geometry_status"].startswith("MISSING_")
        assert child["map_materialization_allowed"] is False


def test_blind_basins_are_not_falsely_connected_to_zanjon():
    p = load(PKG)
    b = p["hydrologic_components"]["paita_alta_blind_basins"]
    assert b["is_natural_ravine"] is False
    assert b["receiver_status"] == "NO_SYNTHETIC_CONNECTION_TO_EL_ZANJON_WITHOUT_TOPOGRAPHIC_ROUTING"
    assert p["collector_coupling"]["blind_basin_connection_inferred"] is False


def test_catarata_field_activation_context_is_not_promoted_to_dated_event():
    p = load(PKG)
    a = p["hydrologic_components"]["la_catarata"]["activation_context"]
    assert a["status"] == "POSITIVE_UNDATED_FIELD_BASED_ACTIVATION_CONTEXT_NOT_EVENT_LEDGER"
    assert a["exact_event_date"] is None
    assert a["exact_event_footprint_available"] is False
    assert a["operational_threshold_inferred"] is False


def test_paita_source_registry_constrains_inference():
    s = load(SRC)
    assert s["deployment_status"] == "RESEARCH_ONLY"
    assert s["test_mode"] == "TEST_ONLY"
    assert s["production_use"] is False
    assert s["production_ready"] is False
    assert s["operational_alerting_enabled"] is False
    assert s["activation_gate"] == "BLOCKED"
    assert s["decision_thresholds"] is None
    assert s["hydraulic_factors"] is None
    ids = {x["source_id"] for x in s["sources"]}
    assert {
        "IGP-PAITA-GEODYNAMICS-2021",
        "IGP-PAITA-ZONIFICACION-2019",
        "MP-PAITA-EVAR-ZANJON-2021",
    }.issubset(ids)
    for source in s["sources"]:
        assert source["admissible_claims"]
        assert source["forbidden_inferences"]


def test_paita_qa_forbids_topology_overreach():
    p = load(PKG)
    q = p["qa"]
    assert q["official_reported_topology_is_not_geometry"] is True
    assert q["exact_confluences_are_unresolved"] is True
    assert q["exact_terminal_outlet_is_unresolved"] is True
    assert q["rainy_period_activation_is_not_dated_event"] is True
    assert q["narrative_capacity_is_not_numeric_capacity"] is True
    assert q["blind_basins_are_not_auto_connected_to_el_zanjon"] is True
