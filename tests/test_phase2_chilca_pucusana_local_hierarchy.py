import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_chilca_pucusana.json"
SOURCES = ROOT / "site/data/phase2/sources/lima_sur_chilca_pucusana_official_evidence_v0_1.json"
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


def test_contract_and_sources_keep_universal_fail_closed_guards():
    c = load(CONTRACT)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert c[key] == expected
        assert s[key] == expected
    assert c["contract_status"] == "DRAFT"
    assert c["alerting_enabled"] is False
    assert ARCH.is_file()
    assert COLLECTOR.is_file()


def test_parent_corridor_and_pucusana_are_not_activation_basins():
    c = load(CONTRACT)
    assert c["identity"]["corridor_is_hydrologic_activation_unit"] is False
    assert c["identity"]["pucusana_is_separate_basin"] is False
    h = c["hierarchy_binding"]
    assert h["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert h["parent_activation_state"] is None
    assert h["child_evidence_promotes_parent_activation"] is False
    assert h["synthetic_union_geometry_allowed"] is False


def test_north_and_south_arms_are_separate_local_units_with_no_geometry_invention():
    c = load(CONTRACT)
    units = {row["component_id"]: row for row in c["local_units"]}
    assert set(units) == {
        "rio_chilca_upstream_context",
        "chilca_brazo_sur",
        "chilca_brazo_norte",
        "pucusana_mouth_exposure_node",
    }
    for cid in ("chilca_brazo_sur", "chilca_brazo_norte"):
        row = units[cid]
        assert row["role"] == "LOWER_LOCAL_CHANNEL_CHILD"
        assert row["channel_geometry_status"].startswith("MISSING_")
        assert row["catchment_geometry_status"].startswith("MISSING_")
        assert row["outlet_status"].startswith("MISSING_")
        assert row["regulatory_faja_is_event_footprint"] is False
        assert row["activation_state"] is None
        assert row["map_publishable"] is False
    assert units["pucusana_mouth_exposure_node"]["role"] == "TERRITORIAL_EXPOSURE_AND_MOUTH_CONTEXT_NOT_BASIN"
    assert units["pucusana_mouth_exposure_node"]["geometry_status"] == "MISSING_NO_APPROXIMATE_POINT_ALLOWED"


def test_regulatory_fajas_do_not_become_event_footprints_capacity_or_channels():
    c = load(CONTRACT)
    s = load(SOURCES)
    geom = c["assets"]["geometry"]
    assert geom["faja_marginal_may_substitute_channel_or_catchment"] is False
    assert geom["approximate_points_allowed"] is False
    assert geom["synthetic_union_allowed"] is False
    hyd = c["assets"]["hydraulic_context"]
    assert hyd["capacity_values"] is None
    assert hyd["regulatory_faja_is_historical_capacity"] is False
    assert hyd["obstruction_or_planned_works_are_historical_capacity"] is False
    assert c["map_policy"]["faja_marginal_is_event_footprint"] is False
    assert s["qa"]["faja_is_event_footprint"] is False
    assert s["qa"]["works_or_obstruction_context_is_capacity"] is False


def test_bifurcation_documentation_does_not_enable_routing_or_cross_arm_activation():
    c = load(CONTRACT)
    coupling = c["collector_coupling"]
    assert coupling["exact_bifurcation_node"] is None
    assert coupling["exact_north_mouth_node"] is None
    assert coupling["exact_south_mouth_node"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["routing_enabled"] is False
    assert coupling["south_arm_activation_implies_north_arm_activation"] is False
    assert coupling["north_arm_activation_implies_south_arm_activation"] is False
    assert coupling["either_arm_activation_implies_pucusana_impact"] is False
    topology = load(SOURCES)["topology"]
    assert topology["lower_bifurcation_supported"] is True
    assert topology["exact_bifurcation_coordinate"] is None
    assert topology["exact_bifurcation_geometry_resolved"] is False
    assert topology["routing_enabled"] is False


def test_historical_silence_is_not_negative_and_coarse_forecast_cannot_select_arm():
    c = load(CONTRACT)
    hist = c["assets"]["historical_events"]
    assert hist["none_days_require_positive_verification"] is True
    assert hist["absence_of_report_may_define_none_day"] is False
    assert hist["corridor_event_may_be_assigned_to_both_arms_without_attribution"] is False
    assert c["assets"]["forecast"]["coarse_precipitation_may_select_active_arm"] is False
    assert load(SOURCES)["qa"]["absence_of_report_is_negative"] is False


def test_map_remains_research_context_only_without_approximate_or_composite_geometry():
    policy = load(CONTRACT)["map_policy"]
    assert policy["parent_corridor_polygon_allowed"] is False
    assert policy["publish_child_only_after_reproducible_channel_or_local_polygon_geometry"] is True
    assert policy["publish_faja_only_as_regulatory_context_if_normalized_with_provenance"] is True
    assert policy["pucusana_administrative_geometry_may_substitute_mouth_node"] is False
    assert policy["approximate_geometry_forbidden"] is True
    assert policy["composite_arm_polygon_forbidden"] is True
    assert policy["risk_or_alert_coloring"] is False
