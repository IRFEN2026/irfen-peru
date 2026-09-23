import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_jequetepeque.json"
SOURCES = ROOT / "site/data/phase2/sources/lalibertad_jequetepeque_official_evidence_v0_1.json"

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


def test_jequetepeque_identity_and_scientific_guards_are_frozen():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    ident = p["hydrologic_identity"]
    assert ident["ana_unit_code"] == "13774"
    assert ident["ana_unit_name"] == "Cuenca Jequetepeque"
    assert ident["chepen_is_hydrologic_unit"] is False
    assert any("Chaman 137752" in x for x in ident["must_not_merge_with"])
    assert s["qa"]["chaman_official_unit_code"] == "137752"
    assert s["qa"]["chaman_merged_into_jequetepeque"] is False
    assert s["qa"]["chepen_materialized_as_river"] is False


def test_geometry_is_exact_ana_query_pending_and_not_fabricated():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["status"] == "MISSING_PENDING_EXACT_ANA_QUERY"
    assert g["source_query"]["where"] == "CODIGO='13774'"
    assert g["source_query"]["out_sr"] == 4326
    assert g["source_query"]["format"] == "geojson"
    assert not (ROOT / g["path"]).exists()
    assert g["counts_as_operational_geometry"] is False
    assert g["counts_as_event_footprint"] is False
    assert p["map_policy"]["approximate_geometry_forbidden"] is True
    assert p["map_policy"]["event_footprint_from_basin_geometry_forbidden"] is True
    assert p["map_policy"]["risk_or_alert_layer"] is False


def test_event_ledger_is_reach_scoped_and_unknown_epochs_stay_unknown():
    p = load(PACKAGE)
    ledger = p["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["status"] == "POSITIVE_RIO_JEQUETEPEQUE_EVENT_EVIDENCE_REACH_SCOPED"
    assert ledger["2017"]["lower_valley_uniform_response"] is False
    assert ledger["2017"]["exact_event_footprint_available"] is False
    assert ledger["2023"]["status"] == "POSITIVE_RIVER_RESPONSE_AND_HYDROLOGIC_OBSERVATIONS"
    assert ledger["2023"]["event_footprint_available"] is False
    assert ledger["2023"]["provider_alert_bands_used_as_irfen_thresholds"] is False
    assert ledger["recent_2025_2026"]["event_label_assigned"] is False


def test_regulated_system_is_not_collapsed_into_natural_response_or_capacity():
    p = load(PACKAGE)
    s = load(SOURCES)
    h = p["assets"]["hydraulic_context"]
    assert h["capacity_values"] is None
    assert h["works_are_historical_capacity"] is False
    assert h["reservoir_operation_is_natural_response"] is False
    assert p["mechanism_policy"]["reservoir_regulation"] == "SEPARATE_CONTEXT_NOT_NATURAL_RESPONSE"
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert s["qa"]["gallito_ciego_operation_treated_as_natural_response"] is False
    assert s["qa"]["works_are_historical_capacity"] is False
    assert s["qa"]["absence_of_report_is_negative"] is False
    assert s["qa"]["provider_bands_are_irfen_thresholds"] is False


def test_observations_are_locators_not_thresholds_or_complete_event_series():
    p = load(PACKAGE)
    o = p["assets"]["observations"]
    names = {x["name"] for x in o["station_or_system_locators"]}
    assert {"Yonan GORE", "Yonan", "Las Paltas"}.issubset(names)
    assert all(x["event_paired_values_frozen"] is False for x in o["station_or_system_locators"])
    assert o["missing_series_is_low_risk"] is False
    assert o["provider_bands_are_irfen_thresholds"] is False
