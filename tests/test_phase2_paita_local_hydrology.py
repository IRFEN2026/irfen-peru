import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json"
SRC = ROOT / "site/data/phase2/sources/piura_paita_official_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_paita_package_is_fail_closed():
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
    assert p["territorial_identity"]["parent_activation_synthesis_forbidden"] is True
    assert p["territorial_identity"]["colan_is_separate"] is True


def test_paita_local_units_are_independent_and_unmapped():
    p = load(PKG)
    required = {
        "el_zanjon",
        "nueva_esperanza",
        "la_piscina",
        "la_catarata",
        "villa_naval",
        "paita_alta_blind_basins",
    }
    assert required == set(p["hydrologic_components"])
    for key in required:
        child = p["hydrologic_components"][key]
        assert child["map_materialization_allowed"] is False
        assert "geometry_status" in child
    assert p["map_policy"]["parent_polygon_forbidden"] is True
    assert p["map_policy"]["synthetic_union_forbidden"] is True


def test_documentary_drainage_network_never_becomes_exact_routing():
    p = load(PKG)
    relations = p["documentary_network_relationships"]
    assert relations
    for rel in relations:
        assert rel["routing_parameterization_allowed"] is False
        assert rel.get("exact_confluence_available", rel.get("exact_outlet_available")) is False
    assert p["qa"]["documentary_network_relation_is_not_exact_geometry"] is True
    assert p["qa"]["urban_modification_requires_current_connectivity_resolution"] is True


def test_1983_evidence_is_child_bounded_to_el_zanjon():
    p = load(PKG)
    event = p["event_ledger"]["1982_1983"]
    assert set(event["child_evidence"]) == {"el_zanjon"}
    assert "DIRECT_FLOW_EVIDENCE" in event["child_evidence"]["el_zanjon"]
    assert event["other_children_activation_assigned"] is False
    assert event["exact_event_footprint_available"] is False
    assert event["hydrograph_available"] is False
    assert event["operational_threshold_inferred"] is False


def test_1998_context_does_not_create_child_outcomes_or_negatives():
    p = load(PKG)
    event = p["event_ledger"]["1997_1998"]
    assert "CONTEXT_ONLY" in event["status"]
    assert event["local_child_activation_assigned"] is False
    assert event["absence_of_local_report_is_negative"] is False
    assert event["provider_rainfall_used_as_irfen_threshold"] is False


def test_2017_evidence_keeps_zanjon_and_pluvial_mechanism_separate():
    p = load(PKG)
    event = p["event_ledger"]["2017"]
    assert set(event["child_evidence"]) == {"el_zanjon", "paita_alta_blind_basins"}
    assert "DIRECT_FLOW_EVIDENCE" in event["child_evidence"]["el_zanjon"]
    assert "PLUVIAL" in event["child_evidence"]["paita_alta_blind_basins"]
    assert event["other_named_ravines_activation_assigned"] is False
    assert p["qa"]["urban_pluvial_and_ravine_overflow_mechanisms_remain_separate"] is True


def test_paita_collector_coupling_stays_blocked():
    p = load(PKG)
    c = p["collector_coupling"]
    assert c["status"].startswith("BLOCKED_")
    assert c["q_i_t_allowed"] is False
    assert c["travel_time_allowed"] is False
    assert c["attenuation_allowed"] is False
    assert c["synthetic_receiver_assignment_forbidden"] is True


def test_paita_official_registry_has_explicit_admissibility_and_forbidden_inferences():
    s = load(SRC)
    assert s["deployment_status"] == "RESEARCH_ONLY"
    assert s["test_mode"] == "TEST_ONLY"
    assert s["production_use"] is False
    assert s["production_ready"] is False
    assert s["operational_alerting_enabled"] is False
    assert s["activation_gate"] == "BLOCKED"
    assert s["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert s["decision_thresholds"] is None
    assert s["hydraulic_factors"] is None

    ids = {x["source_id"] for x in s["sources"]}
    assert {
        "INDECI-BVPAD-PAITA-URBAN-DRAINAGE",
        "PPRRD-PAITA-2019-2021",
        "IGP-PAITA-ZONIFICACION-2019",
        "CENEPRED-PAITA-EVAR-2017",
    }.issubset(ids)

    for source in s["sources"]:
        assert source["admissible_claims"]
        assert source["forbidden_inferences"]


def test_paita_source_semantics_fail_closed():
    qa = load(SRC)["qa"]
    assert qa["paita_city_is_basin"] is False
    assert qa["colan_merged_with_paita"] is False
    assert qa["named_channels_auto_merged"] is False
    assert qa["documentary_receiver_relation_used_as_exact_outlet"] is False
    assert qa["urban_pluvial_and_ravine_mechanisms_merged"] is False
    assert qa["1998_province_context_used_as_child_activation"] is False
    assert qa["absence_of_report_is_negative"] is False
    assert qa["provider_rainfall_or_hazard_values_are_irfen_thresholds"] is False
    assert qa["works_or_walls_used_as_hydraulic_capacity"] is False
