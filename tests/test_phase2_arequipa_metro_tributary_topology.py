import json
from pathlib import Path

CFG = Path("config/phase2_arequipa_metro_tributary_topology_v0_1.json")

def test_arequipa_metro_overlay_stays_research_only():
    d = json.loads(CFG.read_text(encoding="utf-8"))
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None

def test_new_tributaries_are_not_mapped_or_event_labeled():
    d = json.loads(CFG.read_text(encoding="utf-8"))
    additions = {x["child_id"]: x for x in d["tributary_identity_additions"]}
    assert set(additions) == {"arequipa_huarangueros", "arequipa_pampa_blanca"}
    for child in additions.values():
        assert child["geometry_asset"] is None
        assert child["map_publishable"] is False
        assert child["event_state"] == "NO_INDEPENDENT_EVENT_ATTRIBUTION"
        assert child["event_state_transferred"] is False
        assert child["receiver_relationship"]["receiver_child_id"] == "arequipa_los_incas"
        assert child["receiver_relationship"]["exact_confluence_status"] == "NOT_FROZEN"

def test_event_evidence_does_not_transfer_to_tributaries():
    d = json.loads(CFG.read_text(encoding="utf-8"))
    e = d["dated_event_evidence"]
    assert e["event_window_start"] == "2026-02-19"
    assert e["no_tributary_event_transfer"] is True
    assert e["event_footprint_asset"] is None
    assert e["map_publishable_as_footprint"] is False

def test_source_hash_scope_is_explicit():
    d = json.loads(CFG.read_text(encoding="utf-8"))
    s = d["source_provenance"]
    assert s["official"] is True
    assert len(s["evidence_record_sha256"]) == 64
    assert s["source_content_sha256"] is None
