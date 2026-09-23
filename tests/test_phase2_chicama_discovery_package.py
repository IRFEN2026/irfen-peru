import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_chicama.json"
SOURCES = ROOT / "site/data/phase2/sources/lalibertad_chicama_official_evidence_v0_1.json"

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


def test_chicama_identity_and_guards_are_frozen():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    ident = p["hydrologic_identity"]
    assert ident["ana_unit_code"] == "13772"
    assert ident["ana_unit_name"] == "Cuenca Chicama"
    assert ident["territorial_reference_is_basin"] is False
    assert "Cuenca Jequetepeque" in ident["must_not_merge_with"]
    assert "Cuenca Moche" in ident["must_not_merge_with"]
    assert s["qa"]["official_chicama_unit_code"] == "13772"


def test_geometry_and_ravines_fail_closed_until_reproducible():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["status"] == "MISSING_PENDING_EXACT_ANA_QUERY"
    assert g["source_query"]["where"] == "CODIGO='13772'"
    assert not (ROOT / g["path"]).exists()
    assert g["counts_as_operational_geometry"] is False
    assert g["counts_as_event_footprint"] is False
    assert p["map_policy"]["approximate_geometry_forbidden"] is True
    assert p["map_policy"]["named_ravines_require_separate_reproducible_geometry"] is True
    assert p["hydrologic_identity"]["named_ravines_requiring_independent_geometry"]


def test_2017_flow_is_observation_context_not_threshold_and_unknowns_remain_unknown():
    p = load(PACKAGE)
    ledger = p["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["source_reported_max_flow_m3s"] == 333.0
    assert ledger["2017"]["source_reported_value_is_irfen_threshold"] is False
    assert ledger["2017"]["exact_event_footprint_available"] is False
    assert ledger["2017"]["named_ravine_attribution_resolved"] is False
    assert ledger["2023"]["provider_alert_bands_used_as_irfen_thresholds"] is False
    assert ledger["recent_2026"]["event_label_assigned"] is False


def test_hydraulic_study_critical_points_and_observations_do_not_promote_maturity():
    p = load(PACKAGE)
    s = load(SOURCES)
    h = p["assets"]["hydraulic_context"]
    assert h["capacity_values"] is None
    assert h["native_model_files_verified"] is False
    assert h["study_design_values_are_irfen_thresholds"] is False
    assert h["works_are_historical_capacity"] is False
    assert p["mechanism_policy"]["critical_point_is_event"] is False
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert s["qa"]["hydraulic_study_used_as_capacity"] is False
    assert s["qa"]["critical_points_used_as_events"] is False
    assert s["qa"]["provider_bands_are_irfen_thresholds"] is False
    obs = p["assets"]["observations"]
    assert {x["name"] for x in obs["station_or_system_locators"]} == {"Salinar", "El Tambo"}
    assert all(x["event_paired_values_frozen"] is False for x in obs["station_or_system_locators"])
    assert obs["missing_series_is_low_risk"] is False
