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
    assert p["territorial_identity"]["paita_city_is_single_hydrologic_unit"] is False
    assert p["territorial_identity"]["colan_is_separate"] is True
    assert p["territorial_identity"]["parent_activation_synthesis_forbidden"] is True


def test_named_paita_children_remain_independent_and_unmapped():
    p = load(PKG)
    required = {"el_zanjon", "nueva_esperanza", "la_piscina", "la_catarata", "villa_naval"}
    assert required.issubset(p["hydrologic_components"])
    for key in required:
        child = p["hydrologic_components"][key]
        assert child["geometry_status"].startswith("MISSING_")
        assert child["map_materialization_allowed"] is False
    blind = p["hydrologic_components"]["paita_alta_blind_basins"]
    assert blind["is_natural_ravine"] is False
    assert blind["map_materialization_allowed"] is False
    assert p["map_policy"]["synthetic_union_forbidden"] is True


def test_1983_evidence_is_bounded_to_el_zanjon():
    p = load(PKG)
    event = p["event_ledger"]["1982_1983"]
    assert event["evidence_state"] == "IMPACT_CONFIRMED"
    assert event["attributed_component_ids"] == ["el_zanjon"]
    assert event["direct_flow_evidence"] is False
    assert event["exact_event_footprint_available"] is False
    assert event["transfer_to_other_components_forbidden"] is True
    assert event["operational_threshold_inferred"] is False


def test_1997_1998_remains_unknown_not_negative():
    p = load(PKG)
    event = p["event_ledger"]["1997_1998"]
    assert event["status"] == "UNKNOWN_NOT_NEGATIVE_CHILD_LEVEL_SOURCE_GAP"
    assert event["source_ids"] == []
    assert event["local_child_activation_assigned"] is False
    assert event["absence_of_local_report_is_negative"] is False
    assert event["operational_threshold_inferred"] is False


def test_2017_fluid_mechanisms_stay_separate_without_hydrograph_or_footprint():
    p = load(PKG)
    event = p["event_ledger"]["2017"]
    assert set(event["mechanisms"]) == {"el_zanjon", "paita_alta_blind_basins"}
    assert event["mechanisms"]["el_zanjon"]["evidence_state"] == "IMPACT_CONFIRMED"
    assert event["mechanisms"]["el_zanjon"]["direct_flow_evidence"] is False
    assert event["mechanisms"]["el_zanjon"]["exact_event_footprint_available"] is False
    assert event["mechanisms"]["paita_alta_blind_basins"]["evidence_state"] == "IMPACT_CONFIRMED"
    assert event["mechanisms"]["paita_alta_blind_basins"]["individual_depression_geometry_resolved"] is False
    assert event["other_named_ravines_activation_assigned"] is False
    assert event["transfer_between_mechanisms_forbidden"] is True
    assert event["operational_threshold_inferred"] is False


def test_documentary_drainage_relations_do_not_enable_routing():
    p = load(PKG)
    c = p["collector_coupling"]
    assert c["status"].startswith("BLOCKED_")
    assert c["river_collector_confirmed"] is False
    assert c["q_i_t_allowed"] is False
    assert c["travel_time_allowed"] is False
    assert c["attenuation_allowed"] is False
    assert c["peak_coincidence_inference_allowed"] is False
    assert c["synthetic_receiver_assignment_forbidden"] is True


def test_official_source_registry_is_guarded():
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
        "MP-PAITA-PPRRD-2019-2021",
        "IGP-PAITA-ZONIFICACION-2019",
        "IGP-PAITA-GEODINAMICA-2021",
        "MP-PAITA-EVAR-ZANJON-2021",
    }.issubset(ids)
    for source in s["sources"]:
        assert source["admissible_claims"]
        assert source["forbidden_inferences"]


def test_paita_source_semantics_fail_closed():
    s = load(SRC)
    qa = s["qa"]
    assert qa["paita_city_is_basin"] is False
    assert qa["colan_merged_with_paita"] is False
    assert qa["named_channels_auto_merged"] is False
    assert qa["blind_basins_treated_as_named_natural_ravines"] is False
    assert qa["historical_impact_transferred_between_children"] is False
    assert qa["district_emergency_reports_used_as_child_activation"] is False
    assert qa["absence_of_report_is_negative"] is False
    assert qa["hazard_classes_are_irfen_thresholds"] is False
    assert qa["works_or_design_used_as_historical_capacity"] is False
    assert qa["approximate_geometry_used_for_map"] is False
