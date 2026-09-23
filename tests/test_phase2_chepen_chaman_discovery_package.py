import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_chepen_chaman_morana_avispero.json"
SOURCES = ROOT / "site/data/phase2/sources/lalibertad_chepen_chaman_official_evidence_v0_1.json"

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


def test_chepen_is_not_materialized_as_a_river_or_basin():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    assert p["territorial_identity"]["chepen_role"] == "TERRITORIAL_EXPOSURE_CORRIDOR_NOT_HYDROLOGIC_UNIT"
    assert p["territorial_identity"]["synthetic_rio_chepen_allowed"] is False
    assert p["map_policy"]["parent_chepen_geometry_allowed"] is False
    assert p["map_policy"]["composite_polygon_forbidden"] is True
    assert s["qa"]["synthetic_rio_chepen_created"] is False


def test_chaman_identity_is_resolved_but_geometry_stays_fail_closed():
    p = load(PACKAGE)
    c = p["hydrologic_components"]["rio_chaman"]
    assert c["ana_unit_code"] == "137752"
    assert c["ana_unit_name"] == "Cuenca Chaman"
    assert c["geometry_status"] == "MISSING_PENDING_EXACT_ANA_QUERY"
    assert c["source_query"]["where"] == "CODIGO='137752'"
    assert not (ROOT / c["geometry_path"]).exists()
    assert p["map_policy"]["approximate_geometry_forbidden"] is True
    assert p["map_policy"]["publish_chaman_only_after_exact_ana_geometry_replay"] is True


def test_morana_avispero_and_jequetepeque_remain_separate():
    p = load(PACKAGE)
    components = p["hydrologic_components"]
    assert components["rio_la_morana"]["identity_status"].endswith("HYDROLOGIC_ASSIGNMENT_UNRESOLVED")
    assert components["quebrada_avispero"]["identity_status"].endswith("HYDROLOGIC_ASSIGNMENT_UNRESOLVED")
    assert components["rio_la_morana"]["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
    assert components["quebrada_avispero"]["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
    assert components["rio_jequetepeque"]["reference_discovery_id"] == "lalibertad_jequetepeque"
    assert components["rio_jequetepeque"]["merge_into_chaman_forbidden"] is True
    assert p["map_policy"]["publish_morana_or_avispero_only_after_independent_reproducible_geometry"] is True


def test_event_and_prevention_context_do_not_create_thresholds_negatives_or_capacity():
    p = load(PACKAGE)
    s = load(SOURCES)
    ledger = p["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["status"].startswith("UNKNOWN_NOT_NEGATIVE")
    assert ledger["2023"]["event_label_assigned"] is False
    assert ledger["recent_2026_chaman"]["transfer_to_other_components"] is False
    assert ledger["recent_2026_chaman"]["exact_event_footprint_available"] is False
    assert ledger["recent_2026_chaman"]["operational_threshold_inferred"] is False
    assert p["assets"]["hydraulic_context"]["capacity_values"] is None
    assert p["assets"]["hydraulic_context"]["works_are_historical_capacity"] is False
    assert p["mechanism_policy"]["critical_point_is_event"] is False
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    assert s["qa"]["critical_points_used_as_events"] is False
    assert s["qa"]["works_are_historical_capacity"] is False
    assert s["qa"]["absence_of_report_is_negative"] is False
