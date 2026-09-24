import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_lampian_ravines.json"
SOURCES = ROOT / "site/data/phase2/sources/lima_norte_lampian_official_evidence_v0_1.json"
ARCH = ROOT / "config/phase2_local_activation_hierarchy_v0_1.json"
COLLECTOR = ROOT / "config/phase2_collector_coupling_architecture_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_lampian_contract_and_source_registry_are_fail_closed():
    c = load(CONTRACT)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert c[key] == expected
        assert s[key] == expected
    assert c["alerting_enabled"] is False
    assert ARCH.is_file()
    assert COLLECTOR.is_file()


def test_parent_is_context_only_and_named_children_are_separate():
    c = load(CONTRACT)
    h = c["hierarchy_binding"]
    assert h["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert h["parent_activation_state"] is None
    assert h["child_evidence_promotes_parent_activation"] is False
    assert h["synthetic_union_geometry_allowed"] is False
    ids = {row["component_id"] for row in c["local_children"]}
    assert ids == {
        "quebrada_lampian",
        "quebrada_callantama",
        "quebrada_muyopunco_muyucunto",
        "quebrada_carnay",
        "quebrada_lomo_largo",
    }
    for child in c["local_children"]:
        assert child["geometry_status"].startswith("MISSING_")
        assert child["outlet_status"].startswith("MISSING_")
        assert child["activation_state"] is None
        assert child["map_publishable"] is False


def test_marcayjo_conflict_is_quarantined_not_promoted():
    c = load(CONTRACT)
    q = c["nomenclature_quarantine"]["marcayjo"]
    assert q["status"] == "INTERNAL_SOURCE_NOMENCLATURE_CONFLICT_DO_NOT_PROMOTE_AS_CHILD"
    assert q["standalone_child_allowed_now"] is False
    assert q["geometry_allowed_now"] is False
    assert all(row["component_id"] != "quebrada_marcayjo" for row in c["local_children"])
    s = load(SOURCES)
    sq = s["nomenclature_quarantine"][0]
    assert sq["label"] == "Marcayjo"
    assert sq["standalone_child_allowed_now"] is False
    assert sq["negative_control_allowed"] is False


def test_critical_points_and_works_do_not_become_events_capacity_or_geometry():
    c = load(CONTRACT)
    assert c["assets"]["exposure"]["critical_point_is_event"] is False
    assert c["assets"]["hydraulic_context"]["works_are_historical_capacity"] is False
    assert c["assets"]["hydraulic_context"]["capacity_values"] is None
    assert c["map_policy"]["critical_point_coordinate_may_substitute_child_geometry"] is False
    assert c["map_policy"]["synthetic_union_forbidden"] is True
    s = load(SOURCES)
    assert s["qa"]["critical_point_is_event"] is False
    assert s["qa"]["works_define_historical_capacity"] is False
    assert s["qa"]["approximate_geometry_allowed"] is False


def test_no_negative_controls_from_silence_and_coarse_forecast_cannot_select_child():
    c = load(CONTRACT)
    hist = c["assets"]["historical_events"]
    assert hist["none_days_require_positive_verification"] is True
    assert hist["absence_of_report_may_define_none_day"] is False
    assert c["assets"]["forecast"]["coarse_precipitation_may_select_local_child"] is False
    assert load(SOURCES)["qa"]["absence_of_report_is_negative"] is False


def test_carnay_lampian_documentary_meeting_does_not_enable_routing():
    c = load(CONTRACT)
    coupling = c["collector_coupling"]
    assert coupling["documentary_carnay_lampian_meeting_context"] is True
    assert coupling["exact_carnay_lampian_confluence"] is None
    assert coupling["receiver_system"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["child_activation_implies_receiver_overflow"] is False
    topology = load(SOURCES)["topology_context"]
    assert topology["exact_confluence_coordinate"] is None
    assert topology["exact_confluence_geometry_resolved"] is False
    assert topology["routing_enabled"] is False
