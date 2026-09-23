import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_viru.json"
SOURCES = ROOT / "site/data/phase2/sources/lalibertad_viru_official_evidence_v0_1.json"

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


def test_viru_identity_is_official_and_not_territorial_substitution():
    p = load(PACKAGE)
    for key, expected in SAFE.items():
        assert p[key] == expected
    ident = p["hydrologic_identity"]
    assert ident["ana_unit_code"] == "137714"
    assert ident["ana_unit_name"] == "Cuenca Viru"
    assert ident["territorial_reference_is_basin"] is False
    assert "Cuenca Huamanzaña" in ident["must_not_merge_with"]
    assert "Cuenca Moche" in ident["must_not_merge_with"]


def test_geometry_is_exact_query_pending_and_not_fabricated():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["status"] == "MISSING_PENDING_EXACT_ANA_QUERY"
    assert g["source_query"]["where"] == "CODIGO='137714'"
    assert g["source_query"]["out_sr"] == 4326
    assert g["source_query"]["format"] == "geojson"
    assert g["path"].startswith("site/data/phase2/geometries/")
    assert not (ROOT / g["path"]).exists()
    assert g["counts_as_operational_geometry"] is False
    assert g["counts_as_event_footprint"] is False


def test_event_ledger_does_not_invent_unknown_epochs_or_tributaries():
    p = load(PACKAGE)
    ledger = p["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["status"] == "POSITIVE_RIO_VIRU_TERRITORIAL_EVENT_EVIDENCE"
    assert ledger["2017"]["uniform_tributary_activation"] is False
    assert ledger["2017"]["exact_event_footprint_available"] is False
    assert ledger["2023"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2023"]["prevention_context_is_event"] is False
    assert ledger["recent"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["recent"]["prevention_context_is_event"] is False


def test_missing_observations_and_works_never_become_thresholds_or_capacity():
    p = load(PACKAGE)
    obs = p["assets"]["observations"]
    assert obs["status"] == "MISSING_EVENT_PAIRED_HYDROMETEOROLOGICAL_SERIES"
    assert obs["station_or_gauge_series"] == []
    assert obs["missing_series_is_low_risk"] is False
    h = p["assets"]["hydraulic_context"]
    assert h["descolmatation_length_is_capacity"] is False
    assert h["works_are_historical_capacity"] is False
    assert h["capacity_values"] is None
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None


def test_source_roles_preserve_hydrologic_and_event_separation():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert s[key] == expected
    assert {row["source_id"] for row in s["sources"]} == set(p["official_source_ids"])
    qa = s["qa"]
    assert qa["district_or_city_is_basin"] is False
    assert qa["viru_is_separate_from_huamanzaña"] is True
    assert qa["viru_is_separate_from_moche"] is True
    assert qa["works_are_historical_capacity"] is False
    assert qa["prevention_sector_is_event_footprint"] is False
    assert qa["absence_of_report_is_negative"] is False
