import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_chepen_chaman_morana_avispero.json"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/lalibertad_chepen_chaman_morana_avispero.json"
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


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_chepen_is_not_materialized_as_a_river_or_basin():
    p = load(PACKAGE)
    c = load(CONTRACT)
    s = load(SOURCES)
    for obj in (p, c, s):
        for key, expected in SAFE.items():
            assert obj[key] == expected
    assert p["territorial_identity"]["chepen_role"] == "TERRITORIAL_EXPOSURE_CORRIDOR_NOT_HYDROLOGIC_UNIT"
    assert p["territorial_identity"]["synthetic_rio_chepen_allowed"] is False
    assert p["map_policy"]["parent_chepen_geometry_allowed"] is False
    assert p["map_policy"]["composite_polygon_forbidden"] is True
    assert c["component_policy"]["parent_is_map_polygon"] is False
    assert c["component_policy"]["composite_union_forbidden"] is True
    assert c["assets"]["geometry"]["path"] is None
    assert s["qa"]["synthetic_rio_chepen_created"] is False


def test_chaman_identity_exact_query_and_geometry_transition_are_fail_closed():
    p = load(PACKAGE)
    c = load(CONTRACT)
    ch = p["hydrologic_components"]["rio_chaman"]
    assert ch["ana_unit_code"] == "137752"
    assert ch["ana_unit_name"] == "Cuenca Chaman"
    assert ch["source_query"]["where"] == "CODIGO='137752'"
    comp = c["assets"]["geometry_components"]
    assert len(comp) == 1 and comp[0]["component_id"] == "chaman_basin_context"
    assert comp[0]["source_query"] == ch["source_query"]
    path = ROOT / ch["geometry_path"]
    if ch["geometry_status"] == "MISSING_PENDING_EXACT_ANA_QUERY":
        assert not path.exists()
    else:
        assert ch["geometry_status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
        g = ch["geometry"]
        assert path.is_file()
        assert g["path"] == ch["geometry_path"]
        assert g["representation"] == "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
        assert g["sha256"] == sha256(path)
        validation = ROOT / g["validation_path"]
        source = ROOT / g["source_path"]
        assert validation.is_file() and source.is_file()
        assert g["validation_sha256"] == sha256(validation)
        assert g["source_sha256"] == sha256(source)
        assert g["counts_as_operational_geometry"] is False
        assert g["counts_as_event_footprint"] is False
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
