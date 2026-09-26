import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json"
SRC = ROOT / "site/data/phase2/sources/piura_paita_official_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_paita_global_guards_remain_fail_closed():
    for doc in (load(PKG), load(SRC)):
        assert doc["deployment_status"] == "RESEARCH_ONLY"
        assert doc["test_mode"] == "TEST_ONLY"
        assert doc["production_use"] is False
        assert doc["production_ready"] is False
        assert doc["operational_alerting_enabled"] is False
        assert doc["activation_gate"] == "BLOCKED"
        assert doc["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
        assert doc["decision_thresholds"] is None
        assert doc["hydraulic_factors"] is None


def test_paita_official_routing_is_partial_and_geometry_free():
    pkg = load(PKG)
    coupling = pkg["collector_coupling"]
    edges = {(x["from"], x["to"]) for x in coupling["supported_edges"]}
    assert ("nueva_esperanza", "el_zanjon") in edges
    assert ("la_piscina", "el_zanjon") in edges
    assert ("la_catarata", "el_zanjon") in edges
    assert ("el_zanjon", "pacific_ocean") in edges
    assert all(x["geometry_frozen"] is False for x in coupling["supported_edges"])
    assert coupling["q_i_t_allowed"] is False
    assert coupling["travel_time_allowed"] is False
    assert coupling["attenuation_allowed"] is False


def test_villa_naval_receiver_conflict_fails_closed():
    pkg = load(PKG)
    villa = pkg["hydrologic_components"]["villa_naval"]
    assert villa["receiver_status"] == "SOURCE_CONFLICT_FAIL_CLOSED"
    assert villa["outlet_status"] == "UNRESOLVED_CONFLICT_NO_SYNTHETIC_EDGE_ALLOWED"
    assert villa["map_materialization_allowed"] is False
    assert {x["receiver"] for x in villa["receiver_candidates"]} == {"EL_ZANJON", "RADA_COMPLEJO_PESQUERO"}
    assert any(x["from"] == "villa_naval" and x["synthetic_resolution_forbidden"] for x in pkg["collector_coupling"]["unresolved_edges"])


def test_blind_basins_and_historic_event_do_not_promote_children():
    pkg = load(PKG)
    blind = pkg["hydrologic_components"]["paita_alta_blind_basins"]
    assert blind["synthetic_connection_to_el_zanjon_forbidden"] is True
    assert blind["map_materialization_allowed"] is False
    assert pkg["qa"]["historical_window_attribution_is_child_bounded"] is True
    assert pkg["qa"]["unknown_child_outcome_is_not_negative_control"] is True
    assert pkg["qa"]["collector_flow_not_inferred"] is True


def test_paita_source_registry_keeps_text_geometry_and_capacity_distinct():
    src = load(SRC)
    assert src["qa"]["child_routing_from_official_text_only"] is True
    assert src["qa"]["generalized_and_specific_source_conflicts_fail_closed"] is True
    assert src["qa"]["missing_geometry_drawn"] is False
    assert src["qa"]["works_or_channel_description_is_current_capacity"] is False
