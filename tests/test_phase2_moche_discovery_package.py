import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_moche.json"
SOURCES = ROOT / "site/data/phase2/sources/lalibertad_moche_official_evidence_v0_1.json"

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


def test_moche_identity_and_nonoperational_guards_are_frozen():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    ident = p["hydrologic_identity"]
    assert ident["ana_unit_code"] == "137716"
    assert ident["ana_unit_name"] == "Cuenca Moche"
    assert ident["territorial_reference_is_basin"] is False
    assert any("San Ildefonso" in x for x in ident["must_not_merge_with"])
    assert any("San Carlos" in x for x in ident["must_not_merge_with"])


def test_geometry_is_exact_ana_query_only_and_not_fabricated():
    p = load(PACKAGE)
    g = p["assets"]["geometry"]
    assert g["source_query"]["where"] == "CODIGO='137716'"
    assert g["source_query"]["out_sr"] == 4326
    assert g["source_query"]["format"] == "geojson"
    path = ROOT / g["path"]
    if g["status"] == "MISSING_PENDING_EXACT_ANA_QUERY":
        assert not path.exists()
    else:
        assert g["status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
        assert g["representation"] == "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
        assert path.is_file()
        assert g["source_path"].endswith("ana_lalibertad_moche_137716.geojson")
        assert g["validation_path"].endswith("lalibertad_moche_geometry_validation.json")
    assert g["counts_as_operational_geometry"] is False
    assert g["counts_as_event_footprint"] is False
    assert p["map_policy"]["approximate_geometry_forbidden"] is True
    assert p["map_policy"]["event_footprint_from_basin_geometry_forbidden"] is True


def test_event_ledger_preserves_mixed_mechanisms_and_unknown_epochs():
    p = load(PACKAGE)
    ledger = p["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["exact_rio_moche_attribution_resolved"] is False
    assert ledger["2017"]["exact_event_footprint_available"] is False
    assert ledger["2023"]["status"] == "POSITIVE_RIO_MOCHE_OVERFLOW_PLUS_OTHER_MECHANISMS"
    assert ledger["2023"]["mixed_mechanisms_preserved"] is True
    assert ledger["recent_2025"]["status"] == "POSITIVE_RIO_MOCHE_OVERFLOW_EVENT_EVIDENCE"
    assert ledger["recent_2025"]["basinwide_uniform_response"] is False


def test_no_missing_data_capacity_or_local_ravine_shortcuts():
    p = load(PACKAGE)
    s = load(SOURCES)
    assert p["assets"]["observations"]["event_paired_series"] == []
    assert p["assets"]["observations"]["missing_series_is_low_risk"] is False
    assert p["assets"]["hydraulic_context"]["capacity_values"] is None
    assert p["assets"]["hydraulic_context"]["works_are_historical_capacity"] is False
    assert p["mechanism_policy"]["san_ildefonso_or_san_carlos_auto_merge_forbidden"] is True
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert s["qa"]["san_ildefonso_or_san_carlos_auto_merged"] is False
    assert s["qa"]["mixed_mechanisms_collapsed_to_river_overflow"] is False
