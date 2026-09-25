import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_south_coast_moquegua_tacna_discovery_v0_1.json"
EVID=ROOT/"site/data/validation/phase2_research_evidence/south_coast_moquegua_tacna_discovery_evidence_20260925.json"

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def test_fail_closed_and_map_hold():
    c=load(CFG); e=load(EVID)
    for o in (c,e):
        assert o["deployment_status"]=="RESEARCH_ONLY"
        assert o["test_mode"]=="TEST_ONLY"
        assert o["production_use"] is False
        assert o["production_ready"] is False
        assert o["operational_alerting_enabled"] is False
        assert o["activation_gate"]=="BLOCKED"
        assert o["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
        assert o["decision_thresholds"] is None
        assert o["hydraulic_factors"] is None
    assert c["map_publish_enabled"] is False
    assert e["qa"]["map_changed"] is False

def test_official_parent_units_remain_separate():
    c=load(CFG)
    got={x["discovery_id"]:x["official_unit_code"] for x in c["official_hydrographic_context"]}
    expected={
        "south_tambo_1318":"1318",
        "moquegua_ilo_moquegua_1317":"1317",
        "tacna_locumba_1316":"1316",
        "tacna_sama_13158":"13158",
        "tacna_caplina_13156":"13156",
        "tacna_uchusuma_0148":"0148",
    }
    for k,v in expected.items():
        assert got[k]==v

def test_named_and_territorial_evidence_stay_separate():
    c=load(CFG)
    systems={x["discovery_id"]:x for x in c["local_discovery_systems"]}
    ilo=systems["moquegua_ilo_pacocha_local_ravines"]
    assert all(x["named_child"] is None for x in ilo["territorial_events"])
    assert any("Zaparo" in x["do_not_infer"] for x in ilo["territorial_events"])
    ilabaya=systems["tacna_ilabaya_mirave_locumba_local_system"]
    assert all(x["named_child"] is None for x in ilabaya["territorial_events"])
    assert any("conflate" in x["do_not_infer"] for x in ilabaya["territorial_events"])
    pachia=systems["tacna_caplina_pachia_local_system"]
    assert all(x["named_child"] is None for x in pachia["territorial_events"])

def test_geometry_probe_stays_fail_closed():
    p=load(CFG)["geometry_probe_plan"]
    assert p["require_exact_code_match"] is True
    assert p["require_single_feature_for_direct_publish"] is True
    assert p["multiple_features_must_not_be_dissolved"] is True
    assert p["require_geometry_hash"] is True
    assert p["require_topology_and_parent_review"] is True
    assert p["publish_to_map"] is False

def test_source_provenance_hashes_are_present():
    c=load(CFG)
    assert len(c["sources"])>=20
    for s in c["sources"]:
        assert s["bounded_claims"]
        assert re.fullmatch(r"[0-9a-f]{64}",s["capture_sha256"])
        assert s["original_bytes_frozen"] is False

def test_evidence_has_no_map_or_operational_leakage():
    e=load(EVID)
    assert all(x["map_eligible"] is False for x in e["findings"])
    assert e["qa"]["threshold_created"] is False
    assert e["qa"]["capacity_inferred"] is False
    assert e["qa"]["absence_used_as_negative"] is False
    assert e["qa"]["territorial_event_promoted_to_child"] is False
    assert e["qa"]["parent_activated_from_child"] is False
