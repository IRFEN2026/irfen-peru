import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_zorritos_bocapan_coastal_ravines.json"
SOURCES = ROOT / "site/data/phase2/sources/tumbes_zorritos_bocapan_official_evidence_v0_1.json"

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


def test_parent_is_territorial_only_and_named_ravines_remain_separate():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    t = p["territorial_identity"]
    assert t["zorritos_bocapan_role"] == "TERRITORIAL_GROUPER_NOT_SINGLE_SURFACE_CATCHMENT"
    assert t["district_or_city_defines_basin"] is False
    assert t["rio_tumbes_is_part_of_this_group"] is False
    assert t["zarumilla_is_part_of_this_group"] is False
    components = p["hydrologic_components"]
    expected = {
        "bocapan_casitas", "el_grillo", "san_andres", "la_paja", "marinero",
        "el_rubio", "san_pedro", "pena_negra", "el_tiburon", "nuevo_paraiso",
    }
    assert set(components) == expected
    assert components["bocapan_casitas"]["identity_status"] == "OFFICIAL_HYDROLOGIC_IDENTITY_SUPPORTED_BY_ANA"
    assert components["pena_negra"]["identity_status"] == "OFFICIAL_NAME_SUPPORTED_BY_MVCS_PREVENTION_SOURCE"
    assert components["el_tiburon"]["identity_status"] == "OFFICIAL_NAME_SUPPORTED_BY_MP_FN_INFRASTRUCTURE_SOURCE"
    assert components["nuevo_paraiso"]["identity_status"] == "OFFICIAL_NAME_SUPPORTED_BY_MVCS_PREVENTION_SOURCE_HYDROLOGIC_GEOMETRY_PENDING"
    for component in components.values():
        assert component["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
        assert component["map_publishable"] is False


def test_el_grillo_has_component_specific_2023_evidence_without_geometry_or_threshold_promotion():
    p = load(PACKAGE)
    s = load(SOURCES)
    component = p["hydrologic_components"]["el_grillo"]
    assert component["identity_status"] == "OFFICIAL_NAME_AND_2023_YAKU_COMPONENT_EVENT_SUPPORTED_BY_CENEPRED_EVAR"
    assert component["activation_verified"] is True
    assert component["activation_source_ids"] == ["CENEPRED-EVAR-ZORRITOS-EL-GRILLO-2026"]
    event = p["assets"]["event_ledger"]["2023"]["component_outcomes"]["el_grillo"]
    assert event["status"] == "POSITIVE_COMPONENT_EVENT"
    assert event["exact_event_footprint_frozen"] is False
    assert event["threshold_inferred"] is False
    assert event["hydraulic_capacity_inferred"] is False
    assert p["assets"]["event_ledger"]["2023"]["outcome_transfer_to_other_children_allowed"] is False
    assert s["qa"]["el_grillo_direct_source_frozen"] is True
    assert s["qa"]["el_grillo_2023_component_event_positive"] is True


def test_secondary_2017_context_does_not_become_primary_child_event_adjudication():
    p = load(PACKAGE)
    s = load(SOURCES)
    ledger = p["assets"]["event_ledger"]["2017"]
    assert ledger["regional_or_provincial_impact_confirmed"] is True
    assert ledger["secondary_named_infrastructure_context"] == ["san_andres", "la_paja", "marinero"]
    assert ledger["secondary_context_is_direct_primary_event_adjudication"] is False
    assert ledger["specific_ravine_activation_adjudicated"] is False
    assert ledger["absence_of_child_mention_is_negative"] is False
    for component_id in ("san_andres", "la_paja", "marinero"):
        component = p["hydrologic_components"][component_id]
        assert "PRIMARY_SOURCE_FREEZE_PENDING" in component["identity_status"]
        assert component["activation_verified"] is False
    assert s["qa"]["san_andres_direct_source_frozen"] is False
    assert s["qa"]["la_paja_direct_source_frozen"] is False
    assert s["qa"]["marinero_direct_source_frozen"] is False
    assert s["qa"]["san_andres_la_paja_marinero_secondary_official_context_frozen"] is True


def test_direct_name_support_is_not_silently_promoted_to_event_evidence():
    p = load(PACKAGE)
    s = load(SOURCES)
    for component_id, qa_key in (
        ("el_tiburon", "el_tiburon_direct_source_frozen"),
        ("nuevo_paraiso", "nuevo_paraiso_direct_hydrologic_source_frozen"),
    ):
        assert s["qa"][qa_key] is True
        assert p["hydrologic_components"][component_id]["activation_verified"] is False
    for component_id, qa_key in (
        ("el_rubio", "el_rubio_direct_source_frozen"),
        ("san_pedro", "san_pedro_direct_source_frozen"),
    ):
        assert "PENDING" in p["hydrologic_components"][component_id]["identity_status"]
        assert s["qa"][qa_key] is False


def test_no_composite_or_approximate_geometry_can_be_published():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["status"] == "NO_REPRODUCIBLE_CHILD_RAVINE_GEOMETRY_YET"
    assert g["parent_geometry"] is None
    assert g["component_geometries"] == []
    assert g["approximate_points_allowed"] is False
    assert g["invented_polygons_allowed"] is False
    assert g["composite_union_allowed"] is False
    assert g["district_boundary_counts_as_hydrologic_geometry"] is False
    assert g["critical_point_or_prevention_ambit_counts_as_basin_geometry"] is False
    m = p["map_policy"]
    assert m["parent_corridor_polygon_allowed"] is False
    assert m["composite_polygon_forbidden"] is True
    assert m["publish_child_only_after_reproducible_geometry"] is True
    assert m["publish_children_as_separate_layers"] is True
    assert m["risk_or_alert_layer"] is False


def test_event_ledger_keeps_unknown_epochs_unknown_and_prevention_non_event():
    p = load(PACKAGE)
    ledger = p["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2024_2026_recent"]["prevention_activity_is_event"] is False
    assert ledger["2024_2026_recent"]["specific_ravine_activation_adjudicated"] is False


def test_missing_observations_and_works_never_become_threshold_capacity_or_low_risk():
    p = load(PACKAGE)
    s = load(SOURCES)
    obs = p["assets"]["observations"]
    assert obs["event_paired_series"] == []
    assert obs["rio_tumbes_station_series_transfer_allowed"] is False
    assert obs["provider_alert_bands_are_irfen_thresholds"] is False
    assert obs["missing_series_is_low_risk"] is False
    h = p["assets"]["hydraulic_context"]
    assert h["capacity_values"] is None
    assert h["culvert_obstruction_event_is_capacity_test"] is False
    assert h["intervention_length_is_historical_capacity"] is False
    assert h["removed_material_volume_is_historical_capacity"] is False
    assert h["current_works_define_event_footprint"] is False
    assert h["cross_ravine_capacity_transfer_allowed"] is False
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert s["qa"]["rio_tumbes_evidence_transferred_to_zorritos_ravines"] is False
    assert s["qa"]["critical_or_prevention_work_used_as_event"] is False
    assert s["qa"]["works_are_historical_capacity"] is False
    assert s["qa"]["absence_of_report_is_negative"] is False
