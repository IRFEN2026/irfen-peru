import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDE = ROOT / "site/data/validation/phase2_discovery_packages/piura_paita_static_collector_topology_v0_1.json"
SRC = ROOT / "site/data/phase2/sources/piura_paita_official_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_paita_static_topology_stays_fail_closed():
    p = load(SIDE)
    assert p["deployment_status"] == "RESEARCH_ONLY"
    assert p["test_mode"] == "TEST_ONLY"
    assert p["production_use"] is False
    assert p["production_ready"] is False
    assert p["operational_alerting_enabled"] is False
    assert p["activation_gate"] == "BLOCKED"
    assert p["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None


def test_named_children_point_to_static_collector_without_geometry():
    p = load(SIDE)
    assert p["topology"]["receiver"] == "el_zanjon"
    assert set(p["topology"]["tributaries"]) == {
        "nueva_esperanza", "la_piscina", "la_catarata", "villa_naval"
    }
    assert p["topology"]["exact_confluences_reproducible"] is False
    for key in p["topology"]["tributaries"]:
        assert p["component_status"][key]["geometry"] == "MISSING"
        assert p["component_status"][key]["map_publishable"] is False


def test_undated_catarata_context_is_not_event_label():
    p = load(SIDE)
    c = p["component_status"]["la_catarata"]
    assert c["dated_event"] == "UNKNOWN"
    assert "UNDATED" in c["field_context"]


def test_collector_metadata_does_not_promote_hydraulics():
    p = load(SIDE)
    gate = p["coupling_gate"]
    assert gate["static_topology_metadata_allowed"] is True
    for key in (
        "hydrologic_routing_allowed", "discharge_allowed", "travel_time_allowed",
        "attenuation_allowed", "capacity_allowed", "thresholds_allowed",
        "operational_use_allowed"
    ):
        assert gate[key] is False
    assert p["component_status"]["el_zanjon"]["hydraulic_capacity"] is None


def test_blind_basin_pluvial_mechanism_remains_separate():
    p = load(SIDE)
    b = p["component_status"]["paita_alta_blind_basins"]
    assert b["natural_ravine"] is False
    assert b["receiver"] is None


def test_official_source_registry_has_explicit_forbidden_inferences():
    s = load(SRC)
    assert s["deployment_status"] == "RESEARCH_ONLY"
    assert s["activation_gate"] == "BLOCKED"
    source = next(x for x in s["sources"] if x["source_id"] == "IGP-PAITA-GEODYNAMICS-2021")
    assert source["admissible_claims"]
    assert source["forbidden_inferences"]
    assert source["provenance"]["bytes_sha256"] is None
    assert s["qa"]["pdf_linework_used_as_reproducible_geometry"] is False
    assert s["qa"]["undated_activation_used_as_dated_event"] is False
    assert s["qa"]["rainfall_context_used_as_threshold"] is False
