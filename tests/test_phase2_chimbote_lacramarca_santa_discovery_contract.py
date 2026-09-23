import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_packages/ancash_chimbote_lacramarca_santa_bajo.json"
SOURCES = ROOT / "site/data/phase2/sources/ancash_chimbote_lacramarca_santa_bajo_official_evidence_v0_1.json"

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


def test_parent_is_territorial_grouper_not_synthetic_basin():
    c = load(CONTRACT)
    for key, expected in SAFE.items():
        assert c[key] == expected
    assert c["discovery_id"] == "ancash_chimbote_lacramarca_santa_bajo"
    assert c["hydrologic_identity"]["territorial_reference_is_basin"] is False
    p = c["component_policy"]
    assert p["parent_is_hydrologic_basin"] is False
    assert p["parent_is_map_polygon"] is False
    assert p["components_must_remain_separate"] is True
    assert p["composite_union_forbidden"] is True
    assert p["nepena_must_remain_separate"] is True
    assert p["urban_drainage_must_remain_separate"] is True
    g = c["assets"]["geometry"]
    assert g["path"] is None
    assert g["status"].startswith("MISSING_PARENT_GROUPER")


def test_lacramarca_and_lower_santa_are_not_geometry_substitutes():
    c = load(CONTRACT)
    components = {x["component_id"]: x for x in c["assets"]["geometry_components"]}
    assert set(components) == {"rio_lacramarca", "rio_santa_lower_reach", "urban_drainage_chimbote"}
    lac = components["rio_lacramarca"]
    assert lac["hydrologic_identity"]["ana_unit_code"] == "1375992"
    assert lac["hydrologic_identity"]["ana_unit_name"] == "Cuenca Lacramarca"
    assert lac["source_query"]["where"] == "CODIGO='1375992'"
    assert lac["geometry"]["status"] == "MISSING_PENDING_EXACT_ANA_QUERY"
    assert not (ROOT / lac["geometry"]["path"]).exists()
    santa = components["rio_santa_lower_reach"]
    ident = santa["hydrologic_identity"]
    assert ident["ana_parent_unit_code"] == "1376"
    assert ident["ana_parent_unit_name"] == "Cuenca Santa"
    assert ident["exact_lower_reach_unit_code"] is None
    assert ident["whole_basin_may_substitute_lower_reach_geometry"] is False
    assert santa["geometry"]["path"] is None
    assert santa["geometry"]["whole_basin_context_counts_as_lower_reach"] is False
    urban = components["urban_drainage_chimbote"]
    assert urban["hydrologic_identity"]["official_hydrographic_unit_code"] is None
    assert urban["hydrologic_identity"]["may_merge_with_lacramarca"] is False
    assert urban["hydrologic_identity"]["may_merge_with_santa"] is False


def test_event_ledger_preserves_component_and_mechanism_separation():
    c = load(CONTRACT)
    ledger = c["assets"]["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["status"] == "POSITIVE_TERRITORIAL_MULTI_MECHANISM_EVIDENCE"
    assert ledger["2023"]["status"] == "POSITIVE_COMPONENT_SPECIFIC_EVIDENCE"
    notes = ledger["2023"]["component_notes"]
    assert "Rio Lacramarca overflow" in notes["rio_lacramarca"]
    assert "Rio Santa rise/overflow" in notes["rio_santa_lower_reach"]
    assert "drainage-system obstruction" in notes["urban_drainage_chimbote"]
    p = c["mechanism_policy"]
    assert p["lacramarca_and_santa_must_remain_separate"] is True
    assert p["nepena_must_remain_separate"] is True
    assert p["urban_drainage_must_remain_separate"] is True
    assert p["debris_flow_and_river_overflow_must_not_be_collapsed"] is True
    assert p["absence_of_report_is_negative"] is False


def test_missing_observations_do_not_create_low_risk_or_thresholds():
    c = load(CONTRACT)
    obs = c["assets"]["observations"]
    assert obs["status"] == "MISSING_EVENT_PAIRED_HYDROMETEOROLOGICAL_SERIES"
    assert obs["station_or_gauge_series"] == []
    assert obs["missing_series_is_low_risk"] is False
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    h = c["assets"]["hydraulic_context"]
    assert h["chinecas_canal_failure_is_river_capacity"] is False
    assert h["current_prevention_works_are_historical_capacity"] is False
    assert h["capacity_values"] is None


def test_source_registry_is_safe_and_does_not_merge_units():
    c = load(CONTRACT)
    registry = load(SOURCES)
    for key, expected in SAFE.items():
        assert registry[key] == expected
    ids = {x["source_id"] for x in registry["sources"]}
    assert ids == set(c["official_source_ids"])
    qa = registry["qa"]
    assert qa["chimbote_is_basin"] is False
    assert qa["lacramarca_and_santa_are_separate"] is True
    assert qa["nepena_is_separate"] is True
    assert qa["urban_drainage_is_river_event"] is False
    assert qa["works_are_historical_capacity"] is False
    assert qa["absence_of_report_is_negative"] is False
