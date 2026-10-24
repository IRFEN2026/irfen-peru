import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/piura_mancora_los_organos_coastal_ravines.json"
SOURCES = ROOT / "site/data/phase2/sources/piura_mancora_organos_official_evidence_v0_1.json"

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


def test_corridor_and_components_preserve_scientific_identity():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    assert p["territorial_identity"]["mancora_los_organos_role"] == "TERRITORIAL_CORRIDOR_NOT_SINGLE_SURFACE_CATCHMENT"
    assert p["territorial_identity"]["shared_water_supply_or_response_defines_surface_basin"] is False
    components = p["hydrologic_components"]
    assert components["quebrada_fernandez"]["activation_verified"] is True
    assert components["dren_primero_de_mayo"]["is_natural_ravine"] is False
    assert components["quebrada_la_capilla"]["activation_verified"] is False
    assert components["quebrada_la_capilla"]["promote_to_activable_unit"] is False
    assert components["los_organos_local_catchments"]["identity_status"] == "UNRESOLVED"
    assert s["qa"]["mancora_los_organos_corridor_is_basin"] is False


def test_no_geometry_is_invented_or_published_from_context_sources():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["status"] == "NO_REPRODUCIBLE_SURFACE_HYDROLOGIC_GEOMETRY_YET"
    assert g["parent_geometry"] is None
    assert g["component_geometries"] == []
    assert g["approximate_points_allowed"] is False
    assert g["invented_polygons_allowed"] is False
    assert g["critical_point_ambit_counts_as_basin_geometry"] is False
    assert g["groundwater_investigation_counts_as_surface_catchment"] is False
    assert p["map_policy"]["parent_corridor_polygon_allowed"] is False
    assert p["map_policy"]["composite_polygon_forbidden"] is True
    assert p["map_policy"]["risk_or_alert_layer"] is False


def test_2026_event_keeps_natural_ravine_drain_and_pluvial_mechanisms_separate():
    p = load(PACKAGE)
    ledger = p["assets"]["event_ledger"]
    for epoch in ("1982_1983", "1997_1998"):
        assert ledger[epoch]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["status"].startswith("UNKNOWN_NOT_NEGATIVE")
    assert ledger["2023"]["status"].startswith("UNKNOWN_NOT_NEGATIVE")
    e = ledger["2026_02_22"]
    assert e["status"] == "CONFIRMED_COMPOUND_EVENT_WITH_MECHANISMS_SEPARATED"
    assert e["natural_component"] == "quebrada_fernandez"
    assert e["natural_component_response"] == "ACTIVATED"
    assert e["anthropogenic_component"] == "dren_primero_de_mayo"
    assert e["anthropogenic_component_response"] == "OVERFLOW"
    assert e["concurrent_pluvial_accumulation"] is True
    assert e["cross_component_routing_resolved"] is False
    assert e["exact_event_footprint_available"] is False
    assert e["operational_threshold_inferred"] is False


def test_missing_observations_and_response_works_do_not_become_low_risk_or_capacity():
    p = load(PACKAGE)
    s = load(SOURCES)
    obs = p["assets"]["observations"]
    assert obs["event_paired_series"] == []
    assert obs["event_timestamp_is_observation_series"] is False
    assert obs["missing_series_is_low_risk"] is False
    h = p["assets"]["hydraulic_context"]
    assert h["capacity_values"] is None
    assert h["post_event_cleaning_is_historical_capacity"] is False
    assert h["natural_ravine_and_drain_capacity_transfer_allowed"] is False
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert s["qa"]["critical_point_used_as_event"] is False
    assert s["qa"]["works_are_historical_capacity"] is False
    assert s["qa"]["absence_of_report_is_negative"] is False


def test_fernandez_2023_report_is_child_bounded_and_not_a_hydrograph():
    p = load(PACKAGE)
    e = p["assets"]["event_ledger"]["2023"]
    assert e["status"] == "CONFIRMED_CHILD_LEVEL_ACTIVE_HIGH_FLOW_REPORTED_AS_OF_2023_03_26"
    assert e["natural_component"] == "quebrada_fernandez"
    assert e["natural_component_response"] == "ACTIVE_HIGH_FLOW_REPORTED"
    assert e["exact_event_start_time_available"] is False
    assert e["exact_event_footprint_available"] is False
    assert e["discharge_available"] is False
    assert e["transfer_to_other_components_forbidden"] is True
    assert e["operational_threshold_inferred"] is False

def test_fernandez_documentary_outlet_and_topology_are_not_map_geometry():
    p = load(PACKAGE)
    f = p["hydrologic_components"]["quebrada_fernandez"]
    assert f["outlet_status"] == "DOCUMENTARY_SEA_OUTLET_CONFIRMED_GEOMETRY_UNRESOLVED"
    topo = f["documentary_topology"]
    assert topo["flow_direction_context"] == "EAST_TO_WEST_TO_PACIFIC"
    assert topo["use_as_map_geometry"] is False
    assert topo["use_as_hydraulic_capacity"] is False
