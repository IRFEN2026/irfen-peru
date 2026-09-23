import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_registered_unit_packages/lima_norte_chancay_huaral_strengthening_v0_1.json"
SOURCES = ROOT / "site/data/phase2/sources/lima_norte_chancay_huaral_official_evidence_v0_1.json"
INVENTORY = ROOT / "config/phase2_candidate_inventory_v0_2.json"
NORTH = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"

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


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_registered_unit_is_strengthened_without_duplicate_candidate():
    package = load(PACKAGE)
    sources = load(SOURCES)
    inv = load(INVENTORY)
    north = load(NORTH)
    for key, expected in SAFE.items():
        assert package[key] == expected
        assert sources[key] == expected
    ids = [row["candidate_id"] for row in inv["candidates"]]
    assert ids.count("lima_norte_chancay_huaral") == 1
    strengthened = [row for row in north["registered_units_to_strengthen"] if row["candidate_id"] == "lima_norte_chancay_huaral"]
    assert len(strengthened) == 1
    assert package["qa"]["duplicate_candidate_created"] is False
    assert package["qa"]["registered_unit_strengthened_in_place"] is True


def test_existing_official_basin_geometry_is_reused_exactly_and_not_event_footprint():
    package = load(PACKAGE)
    sources = load(SOURCES)
    identity = package["hydrologic_identity"]
    path = ROOT / identity["geometry_path"]
    assert identity["ana_unit_code"] == "137558"
    assert identity["ana_unit_name"] == "Cuenca Chancay - Huaral"
    assert identity["official_basin_geometry_status"] == "REPRODUCIBLE_OFFICIAL_GEOMETRY"
    assert path.exists()
    assert sha256(path) == identity["geometry_sha256"] == sources["qa"]["basin_geometry_sha256"]
    assert identity["geometry_counts_as_complete_candidate_geometry"] is False
    assert identity["basin_polygon_is_event_footprint"] is False
    assert package["map_policy"]["basin_geometry_is_event_footprint"] is False
    assert sources["qa"]["basin_geometry_is_event_footprint"] is False


def test_2017_event_keeps_named_huerequeque_positive_without_invented_geometry():
    package = load(PACKAGE)
    event = package["event_ledger"]["2017"]
    child = package["hydrologic_identity"]["named_children"]["quebrada_huerequeque"]
    assert event["basin_emergency_positive"] is True
    assert event["huayan_flood_impact_positive"] is True
    assert event["quebrada_huerequeque_activation_positive"] is True
    assert event["huerequeque_geometry_resolved"] is False
    assert event["exact_event_footprint_reproducible"] is False
    assert event["reported_affected_area_ha"] == 921.92
    assert event["reported_affected_area_used_as_geometry"] is False
    assert child["geometry_status"] == "UNRESOLVED_NO_GEOMETRY_DRAWN"
    assert package["map_policy"]["draw_huerequeque_before_reproducible_geometry"] is False
    assert package["map_policy"]["use_921_92_ha_as_polygon"] is False


def test_santo_domingo_discharge_discrepancy_is_preserved_and_not_thresholded():
    package = load(PACKAGE)
    sources = load(SOURCES)
    obs = package["observations"]
    assert obs["source_reported_2017_discharge_values_m3s"] == [270, 277]
    assert obs["source_reported_277_date"] == "2017-03-15"
    assert obs["discrepancy_status"] == "RETAINED_NOT_SILENTLY_RECONCILED"
    assert obs["provider_context_normal_value_m3s"] == 80
    assert obs["provider_context_normal_value_is_irfen_threshold"] is False
    assert obs["irfen_decision_threshold"] is None
    assert obs["event_paired_series_frozen"] is False
    assert obs["station_to_tributary_transfer_allowed_without_routing_qa"] is False
    assert sources["qa"]["source_reported_discharge_discrepancy_retained"] is True
    assert sources["qa"]["provider_normal_value_m3s_is_irfen_threshold"] is False


def test_current_critical_points_and_works_remain_context_only():
    package = load(PACKAGE)
    recent = package["event_ledger"]["2024_2026_recent"]
    hydraulic = package["hydraulic_context"]
    assert recent["identified_critical_point_fichas"] == 38
    assert recent["critical_point_presence_is_event"] is False
    assert hydraulic["historical_capacity_values"] is None
    assert hydraulic["2016_encauzamiento_descolmatacion_reported"] is True
    assert hydraulic["works_define_historical_capacity"] is False
    assert hydraulic["current_critical_points_define_event_footprints"] is False
    assert hydraulic["current_critical_points_define_thresholds"] is False
    assert package["qa"]["current_critical_points_used_as_2017_event_truth"] is False
    assert package["qa"]["hydraulic_capacity_inferred"] is False


def test_missing_historical_windows_stay_unknown_not_negative():
    package = load(PACKAGE)
    for period in ("1982_1983", "1997_1998", "2023"):
        event = package["event_ledger"][period]
        assert "UNKNOWN_NOT_NEGATIVE" in event["status"]
        assert event["absence_of_report_is_negative"] is False
    assert package["qa"]["absence_of_report_is_negative"] is False
    assert package["qa"]["thresholds_inferred"] is False
    assert package["qa"]["approximate_child_geometry_created"] is False
