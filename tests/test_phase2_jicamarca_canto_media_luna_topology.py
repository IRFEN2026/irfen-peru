import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_canto_grande_media_luna_assessment_v0_1.json"

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


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def test_topology_update_preserves_phase2_fail_closed_guards():
    c = load()
    for key, expected in SAFE.items():
        assert c[key] == expected
    assert c["status"] == "OFFICIAL_LOCAL_TOPOLOGY_DOCUMENTED_GEOMETRY_AND_OUTLETS_UNRESOLVED"


def test_media_luna_is_a_separate_local_child_inside_canto_grande_system():
    c = load()
    ident = c["bounded_identity_evidence"]
    topo = c["topology_model"]
    assert ident["media_luna_named_as_separate_ravine"] is True
    assert ident["upper_canto_grande_divides_into_named_canto_grande_and_media_luna_branches"] is True
    assert ident["media_luna_is_part_of_canto_grande_local_system"] is True
    assert topo["local_children"] == ["canto_grande_upper_branch", "media_luna"]
    assert topo["direct_media_luna_to_rimac_connection_assumed"] is False
    assert topo["synthetic_canto_media_luna_union_geometry_allowed"] is False


def test_documentary_topology_does_not_promote_geometry_or_outlets():
    c = load()
    ident = c["bounded_identity_evidence"]
    topo = c["topology_model"]
    policy = c["local_unit_policy"]
    assert ident["media_luna_geometry_reproducible_from_sources"] is False
    assert ident["canto_grande_geometry_reproducible_from_sources"] is False
    assert topo["media_luna_exact_junction_coordinate"] is None
    assert topo["canto_grande_exact_outlet_coordinate"] is None
    assert topo["topology_may_be_used_for_routing_before_geometry_and_outlets"] is False
    assert policy["municipal_descriptive_text_may_define_geometry"] is False
    assert policy["documented_topology_may_replace_missing_outlet_coordinates"] is False


def test_2002_media_luna_impact_stays_local_and_does_not_promote_receiver():
    ev = load()["bounded_event_evidence"]
    assert ev["event_year"] == 2002
    assert ev["component_id"] == "media_luna"
    assert ev["research_state"] == "IMPACT_CONFIRMED"
    assert ev["event_footprint_geometry_available"] is False
    assert ev["event_footprint_may_be_digitized_from_report_image"] is False
    assert ev["promotes_canto_grande_parent_activation"] is False
    assert ev["promotes_rimac_overflow"] is False


def test_collector_coupling_remains_unparameterized():
    cc = load()["collector_coupling"]
    assert cc["routing_status"].startswith("BLOCKED_")
    for child_id in ("media_luna", "canto_grande_upper_branch"):
        child = cc[child_id]
        assert child["outlet_or_confluence"] is None
        assert child["Q_i_t"] is None
        assert child["travel_time"] is None
        assert child["attenuation"] is None
        assert child["quality"] == "UNKNOWN"
    assert cc["collector_stage_or_discharge_response"] is None
    assert cc["peak_coincidence"] is None
    assert cc["hydraulic_capacity"] is None
    assert cc["child_activation_implies_canto_grande_parent_activation"] is False
    assert cc["child_activation_implies_rimac_overflow"] is False


def test_map_publication_remains_blocked_without_reproducible_geometry():
    mp = load()["map_policy"]
    assert mp["publish_parent_context_now"] is False
    assert mp["publish_media_luna_child_now"] is False
    assert mp["publish_canto_grande_child_now"] is False
    assert mp["publish_topology_as_risk_or_alert"] is False
    assert mp["publish_only_after_independent_reproducible_geometry"] is True
