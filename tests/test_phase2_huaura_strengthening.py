import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_registered_unit_packages/lima_norte_huaura_huacho_sayan_strengthening_v0_1.json"
SOURCES = ROOT / "site/data/phase2/sources/lima_norte_huaura_huacho_sayan_official_evidence_v0_1.json"
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


def test_registered_huaura_unit_is_strengthened_without_duplicate():
    package = load(PACKAGE)
    sources = load(SOURCES)
    inv = load(INVENTORY)
    north = load(NORTH)
    for key, expected in SAFE.items():
        assert package[key] == expected
        assert sources[key] == expected
    ids = [row["candidate_id"] for row in inv["candidates"]]
    assert ids.count("lima_norte_huaura_huacho_sayan") == 1
    strengthened = [row for row in north["registered_units_to_strengthen"] if row["candidate_id"] == "lima_norte_huaura_huacho_sayan"]
    assert len(strengthened) == 1
    assert package["qa"]["duplicate_candidate_created"] is False
    assert package["qa"]["registered_unit_strengthened_in_place"] is True


def test_official_huaura_basin_geometry_is_reused_exactly_as_context_only():
    package = load(PACKAGE)
    sources = load(SOURCES)
    identity = package["hydrologic_identity"]
    path = ROOT / identity["geometry_path"]
    assert identity["ana_unit_code"] == "13756"
    assert identity["ana_unit_name"] == "Cuenca Huaura"
    assert identity["official_basin_geometry_status"] == "REPRODUCIBLE_OFFICIAL_GEOMETRY"
    assert path.exists()
    assert sha256(path) == identity["geometry_sha256"] == sources["qa"]["basin_geometry_sha256"]
    assert identity["geometry_counts_as_complete_candidate_geometry"] is False
    assert identity["basin_polygon_is_event_footprint"] is False
    assert identity["huacho_is_basin"] is False
    assert identity["sayan_is_basin"] is False
    assert package["map_policy"]["basin_geometry_is_event_footprint"] is False


def test_2023_river_rise_impact_is_positive_without_event_polygon_or_ravine_inference():
    package = load(PACKAGE)
    sources = load(SOURCES)
    event = package["event_ledger"]["2023"]
    assert event["rio_huaura_rise_reported"] is True
    assert event["humaya_intake_or_canal_impact_positive"] is True
    assert event["vilcahuaura_intake_or_canal_impact_positive"] is True
    assert event["irrigation_service_interruption_reported"] is True
    assert event["exact_event_footprint_reproducible"] is False
    assert event["basin_polygon_used_as_event_footprint"] is False
    assert event["local_ravine_activation_inferred"] is False
    assert sources["qa"]["2023_positive_river_rise_impact_retained"] is True
    assert sources["qa"]["humaya_vilcahuaura_geometry_resolved"] is False


def test_alco_sayan_station_is_observation_path_not_threshold_or_child_proxy():
    package = load(PACKAGE)
    obs = package["observations"]
    assert obs["station"]["name"] == "Alco"
    assert obs["station"]["district"] == "Sayán"
    assert obs["station"]["watercourse_context"] == "Rio Huaura"
    assert obs["event_paired_rainfall"] == []
    assert obs["event_paired_stage"] == []
    assert obs["event_paired_discharge"] == []
    assert obs["event_paired_series_frozen"] is False
    assert obs["station_to_local_ravine_transfer_allowed_without_routing_qa"] is False
    assert obs["provider_monitoring_objectives_are_irfen_thresholds"] is False
    assert obs["missing_observations_are_low_risk"] is False


def test_faja_and_current_works_do_not_become_footprint_capacity_or_threshold():
    package = load(PACKAGE)
    sources = load(SOURCES)
    hydraulic = package["hydraulic_context"]
    assert hydraulic["historical_capacity_values"] is None
    assert hydraulic["faja_length_context_km"] == 7
    assert hydraulic["faja_is_event_footprint"] is False
    assert hydraulic["faja_defines_hydraulic_capacity"] is False
    assert hydraulic["current_project_progress_is_model_parameter"] is False
    assert hydraulic["current_works_define_historical_capacity"] is False
    assert hydraulic["current_works_define_irfen_threshold"] is False
    assert sources["qa"]["faja_used_as_event_footprint"] is False
    assert sources["qa"]["faja_used_as_historical_capacity"] is False
    assert sources["qa"]["current_works_used_as_historical_capacity"] is False


def test_unresolved_historical_windows_remain_unknown_not_negative():
    package = load(PACKAGE)
    for period in ("1982_1983", "1997_1998", "2017"):
        event = package["event_ledger"][period]
        assert "UNKNOWN_NOT_NEGATIVE" in event["status"]
        assert event["absence_of_report_is_negative"] is False
    assert package["qa"]["2017_positive_event_invented"] is False
    assert package["qa"]["absence_of_report_is_negative"] is False
    assert package["qa"]["thresholds_inferred"] is False
    assert package["qa"]["hydraulic_capacity_inferred"] is False
    assert package["qa"]["approximate_child_geometry_created"] is False
