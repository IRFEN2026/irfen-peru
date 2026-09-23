import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/ancash_huarmey_culebras.json"
SOURCES = ROOT / "site/data/phase2/sources/ancash_huarmey_culebras_official_evidence_v0_1.json"
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_safe_guards_and_component_separation():
    package = load(PACKAGE)
    sources = load(SOURCES)
    for key, expected in SAFE.items():
        assert package[key] == expected
        assert sources[key] == expected
    policy = package["component_policy"]
    assert policy["parent_is_hydrologic_basin"] is False
    assert policy["parent_is_map_polygon"] is False
    assert policy["components_must_remain_separate"] is True
    assert policy["composite_union_forbidden"] is True
    assert package["qa"]["components_merged"] is False
    assert package["map_policy"]["publish_parent_composite"] is False


def test_exact_huarmey_and_culebras_geometry_hashes_are_separate_context():
    package = load(PACKAGE)
    expected = {
        "huarmey": ("137594", "Cuenca Huarmey", "48a83102ecaa95baf6ebd153e61c35992e657ebc61ca40062354d394d95b3dc4"),
        "culebras": ("1375952", "Cuenca Culebras", "95e22ba1e1a33db10ce9391a5041712c60cdec003a1af238d7044dafbb5d6370"),
    }
    for key, (code, name, digest) in expected.items():
        comp = package["components"][key]
        assert comp["ana_unit_code"] == code
        assert comp["ana_unit_name"] == name
        assert comp["geometry_sha256"] == digest
        assert sha(ROOT / comp["geometry_path"]) == digest
        assert comp["geometry_is_event_footprint"] is False
    assert package["map_policy"]["basin_geometries_are_event_footprints"] is False


def test_huarmey_2017_is_positive_without_inventing_event_polygon():
    package = load(PACKAGE)
    event = package["components"]["huarmey"]["event_ledger"]["2017"]
    assert event["event_date"] == "2017-03-15"
    assert "POSITIVE_RIO_HUARMEY_OVERFLOW" in event["status"]
    assert event["reported_city_inundation_percent_lower_bound"] == 80
    assert event["reported_percentage_used_as_geometry"] is False
    assert event["exact_event_footprint_reproducible"] is False
    assert event["all_provincial_impacts_assigned_to_main_channel"] is False
    assert package["qa"]["huarmey_2017_positive_event_retained"] is True


def test_culebras_remains_unknown_and_does_not_inherit_huarmey_outcomes():
    package = load(PACKAGE)
    ledger = package["components"]["culebras"]["event_ledger"]
    for period in ("1982_1983", "1997_1998", "2017", "2023", "recent"):
        assert "UNKNOWN_NOT_NEGATIVE" in ledger[period]["status"]
        assert ledger[period]["absence_of_report_is_negative"] is False
    assert package["qa"]["culebras_event_invented"] is False
    assert package["observations"]["cross_component_transfer_allowed"] is False


def test_current_works_and_critical_points_do_not_become_capacity_or_thresholds():
    package = load(PACKAGE)
    hydraulic = package["hydraulic_context"]
    assert hydraulic["historical_capacity_values"] is None
    assert hydraulic["current_project_progress_is_model_parameter"] is False
    assert hydraulic["current_critical_points_are_historical_events"] is False
    assert hydraulic["current_works_define_historical_capacity"] is False
    assert hydraulic["current_works_define_irfen_threshold"] is False
    assert package["qa"]["negative_controls_inferred"] is False
    assert package["qa"]["thresholds_inferred"] is False
    assert package["qa"]["hydraulic_capacity_inferred"] is False


def test_missing_observations_are_not_low_risk_and_no_approximate_geometry_created():
    package = load(PACKAGE)
    obs = package["observations"]
    assert obs["huarmey"] == {"rainfall": [], "stage": [], "discharge": []}
    assert obs["culebras"] == {"rainfall": [], "stage": [], "discharge": []}
    assert obs["missing_observations_are_low_risk"] is False
    assert package["qa"]["absence_of_report_is_negative"] is False
    assert package["qa"]["approximate_geometry_created"] is False
