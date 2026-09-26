import json
from pathlib import Path

BASE = Path("config/phase2_south_coast_ica_arequipa_discovery_v0_1.json")
OVERLAY = Path("config/phase2_ica_historical_events_v0_1.json")

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_overlay_inherits_fail_closed_base():
    base = load(BASE)
    d = load(OVERLAY)
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["base_dependency"]["guardrails_inherited"] is True
    assert base["production_use"] is False
    assert base["production_ready"] is False
    assert base["operational_alerting_enabled"] is False
    assert base["activation_gate"] == "BLOCKED"
    assert base["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert base["decision_thresholds"] is None
    assert base["hydraulic_factors"] is None

def test_historical_records_do_not_publish_geometry():
    d = load(OVERLAY)
    assert len(d["historical_records"]) == 4
    assert all(x["time_precision"] == "YEAR_ONLY" for x in d["historical_records"])
    assert all(x["map_publishable"] is False for x in d["historical_records"])
    assert all(len(x["record_sha256"]) == 64 for x in d["historical_records"])
    assert d["summary"]["geometry_assets_published"] == 0

def test_vista_alegre_name_link_stays_unresolved():
    d = load(OVERLAY)
    record = next(x for x in d["historical_records"] if x["id"] == "ica_vista_alegre_2012")
    assert record["child_id"] is None
    assert d["nomenclature_guard"]["mapped_candidate_id"] == "ica_nuevo_vista_alegre_nasca"
    assert d["nomenclature_guard"]["status"] == "UNRESOLVED"

def test_ayapana_is_named_but_unmapped():
    d = load(OVERLAY)
    item = next(x for x in d["identity_updates"] if x["candidate_id"] == "ica_la_ayapana")
    assert item["identity_status"] == "OFFICIAL_ANA_HISTORICAL_NAME_CONFIRMED"
    assert item["parent_assignment"] == "PENDING_REPRODUCIBLE_HYDROGRAPHIC_ADJUDICATION"
    assert item["geometry_status"] == "NOT_FROZEN"
    assert item["map_publishable"] is False
