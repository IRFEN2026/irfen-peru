import json
from pathlib import Path

CFG = Path("config/phase2_mirave_collector_topology_v0_1.json")

def load():
    return json.loads(CFG.read_text(encoding="utf-8"))

def test_mirave_collector_topology_is_fail_closed():
    cfg = load()
    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None

def test_mirave_receiver_is_bound_to_medio_locumba_not_sama():
    cfg = load()
    identity = cfg["identity"]
    assert identity["parent_basin"]["official_unit_code"] == "1316"
    receiver = identity["receiver"]
    assert receiver["name"] == "río Salado"
    assert receiver["receiving_hydrographic_unit"]["official_unit_code"] == "13165"
    assert receiver["receiving_hydrographic_unit"]["name"] == "Medio Locumba"
    assert receiver["exact_outlet_coordinate"] is None
    guard = cfg["homonym_guard"]
    assert guard["exact_parent_uh_match_required"] is True
    assert "Sama" in guard["distinct_context"]

def test_receiver_margin_and_event_evidence_are_not_promoted():
    cfg = load()
    assert cfg["map_policy"]["child_map_publishable"] is False
    assert cfg["map_policy"]["receiver_map_publishable"] is False
    assert cfg["map_policy"]["synthetic_connector_forbidden"] is True
    assert cfg["map_policy"]["faja_margin_is_not_event_footprint"] is True
    binding = cfg["event_binding"]
    assert binding["events_do_not_define_geometry"] is True
    assert binding["events_do_not_define_threshold"] is True
    assert binding["child_activation_does_not_imply_receiver_overflow"] is True
    assert binding["receiver_overflow_requires_independent_evidence"] is True

def test_sources_are_official_and_hashes_are_not_invented():
    cfg = load()
    assert {x["source_id"] for x in cfg["sources"]} == {
        "INGEMMET-A6705-MIRAVE",
        "ANA-RD-0928-2022-SALADO-MIRAVE-OCONCHAY",
        "ANA-PGRH-CAPLINA-LOCUMBA",
    }
    for src in cfg["sources"]:
        assert src["official"] is True
        assert src["url"].startswith("https://")
        assert src["content_sha256"] is None
        assert "NOT_ARCHIVED" in src["provenance_status"]
