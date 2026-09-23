import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lima_norte_supe_caleta_vidal.json"
SOURCES = ROOT / "site/data/phase2/sources/lima_norte_supe_caleta_vidal_official_evidence_v0_1.json"
INVENTORY = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"

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


def test_supe_is_hydrologic_unit_and_caleta_vidal_only_exposure_node():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    identity = p["hydrologic_identity"]
    assert identity["ana_unit_code"] == "137572"
    assert identity["ana_unit_name"] == "Cuenca Supe"
    assert identity["caleta_vidal_is_hydrologic_basin"] is False
    assert identity["territorial_reference_is_basin"] is False
    assert "Cuenca Pativilca 13758" in identity["must_not_merge_with"]
    assert "Cuenca Fortaleza 137592" in identity["must_not_merge_with"]
    assert identity["internal_names_do_not_create_independent_children_without_geometry_and_connectivity_review"] is True
    assert s["qa"]["caleta_vidal_is_basin"] is False
    assert s["qa"]["supe_pativilca_fortaleza_merged"] is False


def test_2017_positive_territorial_evidence_does_not_force_mainstem_mechanism():
    p = load(PACKAGE)
    s = load(SOURCES)
    e = p["assets"]["event_ledger"]["2017"]
    assert e["territorial_positive_evidence"] is True
    assert e["caleta_vidal_impacted"] is True
    assert e["exact_hydrologic_mechanism_resolved"] is False
    assert e["rio_supe_mainstem_attribution_confirmed"] is False
    assert e["irrigation_or_drainage_network_contribution_resolved"] is False
    assert e["pluvial_accumulation_contribution_resolved"] is False
    assert e["compound_mechanism_resolved"] is False
    assert e["exact_event_footprint_available"] is False
    assert e["basin_geometry_is_event_footprint"] is False
    assert s["qa"]["2017_caleta_vidal_positive_territorial_evidence_retained"] is True
    assert s["qa"]["2017_exact_mechanism_resolved"] is False
    assert s["qa"]["2017_mainstem_rio_supe_attribution_assumed"] is False


def test_geometry_remains_fail_closed_or_is_exactly_frozen_ana_context():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["source_query"]["where"] == "CODIGO='137572'"
    assert g["counts_as_operational_geometry"] is False
    assert g["counts_as_event_footprint"] is False
    assert g["approximate_fallback_allowed"] is False
    assert g["caleta_vidal_point_or_district_polygon_allowed_as_basin_fallback"] is False
    if str(g["status"]).startswith("MISSING"):
        assert not (ROOT / g["path"]).exists()
    else:
        assert g["status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
        assert g["representation"] == "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
        assert (ROOT / g["path"]).is_file()
        assert isinstance(g["sha256"], str) and len(g["sha256"]) == 64
        assert isinstance(g["source_sha256"], str) and len(g["source_sha256"]) == 64
        assert isinstance(g["validation_sha256"], str) and len(g["validation_sha256"]) == 64
    m = p["map_policy"]
    assert m["approximate_geometry_forbidden"] is True
    assert m["publish_only_after_exact_ana_geometry_replay"] is True
    assert m["caleta_vidal_point_or_administrative_polygon_is_basin_geometry"] is False
    assert m["publish_faja_as_event_footprint"] is False
    assert m["risk_or_alert_layer"] is False


def test_fajas_are_context_not_event_footprint_or_capacity():
    p = load(PACKAGE)
    s = load(SOURCES)
    h = p["assets"]["hydraulic_context"]
    assert h["capacity_values"] is None
    assert h["faja_is_event_footprint"] is False
    assert h["faja_width_is_historical_flood_extent"] is False
    assert h["regulatory_or_management_reach_is_historical_capacity"] is False
    assert h["works_or_channel_maintenance_define_threshold"] is False
    assert s["qa"]["faja_used_as_event_footprint"] is False
    assert s["qa"]["faja_used_as_historical_capacity"] is False
    assert s["qa"]["thresholds_inferred"] is False


def test_missing_observations_and_historical_windows_do_not_become_low_risk_or_negatives():
    p = load(PACKAGE)
    obs = p["assets"]["observations"]
    assert obs["event_paired_rainfall"] == []
    assert obs["event_paired_stage"] == []
    assert obs["event_paired_discharge"] == []
    assert obs["water_quality_is_hydrometric_event_observation"] is False
    assert obs["missing_series_is_low_risk"] is False
    for period in ("1982_1983", "1997_1998", "2023"):
        event = p["assets"]["event_ledger"][period]
        assert "UNKNOWN_NOT_NEGATIVE" in event["status"]
        assert event["absence_of_report_is_negative"] is False
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert p["mechanism_policy"]["cross_basin_threshold_transfer_allowed"] is False


def test_inventory_alignment_preserves_non_operational_scope_before_or_after_registration():
    p = load(PACKAGE)
    inv = load(INVENTORY)
    ids = {row["discovery_id"] for row in inv.get("discovery_units", [])}
    a = p["inventory_alignment"]
    assert a["operational_candidate_count_change_allowed"] is False
    assert inv["relationship_to_phase2"]["registered_candidate_count_unchanged"] == 18
    assert inv["relationship_to_phase2"]["changes_registered_candidate_count"] is False
    assert inv["relationship_to_phase2"]["changes_operational_scope"] is False
    if "lima_norte_supe_caleta_vidal" in ids:
        assert a["registration_status"] == "REGISTERED_DISCOVERY_ONLY_NON_OPERATIONAL"
        rows = [row for row in inv["discovery_units"] if row["discovery_id"] == "lima_norte_supe_caleta_vidal"]
        assert len(rows) == 1
        assert inv["relationship_to_phase2"]["discovery_units_count"] == len(inv["discovery_units"])
    else:
        assert a["registration_status"].startswith("GAP_DETECTED_")
