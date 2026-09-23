import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/ancash_chimbote_lacramarca_santa_bajo.json"
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


def test_strict_phase2_guards_and_child_separation_hold():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert p[key] == expected
        assert s[key] == expected
    policy = p["component_policy"]
    assert policy["parent_is_hydrologic_basin"] is False
    assert policy["parent_is_map_polygon"] is False
    assert policy["components_must_remain_separate"] is True
    assert policy["composite_union_forbidden"] is True
    assert policy["nepena_must_remain_separate"] is True
    assert policy["urban_drainage_must_remain_separate"] is True
    components = {x["component_id"]: x for x in p["assets"]["geometry_components"]}
    assert set(components) == {"rio_lacramarca", "rio_santa_lower_reach", "urban_drainage_chimbote"}
    assert components["rio_lacramarca"]["hydrologic_identity"]["ana_unit_code"] == "1375992"
    assert components["rio_santa_lower_reach"]["hydrologic_identity"]["whole_basin_may_substitute_lower_reach_geometry"] is False


def test_current_anin_context_is_not_event_capacity_or_threshold():
    p = load(PACKAGE)
    s = load(SOURCES)
    source_by_id = {x["source_id"]: x for x in s["sources"]}
    for source_id in ("ANIN-LACRAMARCA-DEFENSES-20251211", "ANIN-LACRAMARCA-PREVENTION-20260227"):
        assert source_id in source_by_id
        forbidden = " ".join(source_by_id[source_id]["forbidden_inferences"]).lower()
        assert "capacity" in forbidden
        assert "threshold" in forbidden
    recent = p["assets"]["event_ledger"]["recent"]
    assert recent["status"] == "CURRENT_PROTECTION_AND_HIGH_FLOW_CONTEXT_NO_EVENT_CLASSIFICATION"
    assert "ANIN-LACRAMARCA-DEFENSES-20251211" in recent["source_ids"]
    assert "ANIN-LACRAMARCA-PREVENTION-20260227" in recent["source_ids"]
    assert "not converted to an overflow/no-overflow outcome" in recent["component_notes"]["rio_lacramarca"]
    assert "No recent Lacramarca" in recent["component_notes"]["rio_santa_lower_reach"]


def test_reported_protection_population_is_context_not_observed_event_exposure():
    p = load(PACKAGE)
    exposure = p["assets"]["exposure_connectivity"]["current_project_context"]
    assert exposure["source_id"] == "ANIN-LACRAMARCA-DEFENSES-20251211"
    assert exposure["reported_intended_beneficiary_communities"] == 58
    assert exposure["reported_intended_beneficiary_population_lower_bound"] == 35000
    assert exposure["counts_as_observed_event_exposure"] is False
    assert exposure["counts_as_lower_santa_exposure"] is False


def test_hydraulic_and_missing_data_guards_remain_fail_closed():
    p = load(PACKAGE)
    h = p["assets"]["hydraulic_context"]
    assert h["capacity_values"] is None
    assert h["current_prevention_works_are_historical_capacity"] is False
    assert h["reported_project_progress_is_hydraulic_capacity"] is False
    assert h["local_bridge_intervention_dimensions_are_hydraulic_capacity"] is False
    obs = p["assets"]["observations"]
    assert obs["station_or_gauge_series"] == []
    assert obs["missing_series_is_low_risk"] is False
    assert p["mechanism_policy"]["absence_of_report_is_negative"] is False
    m = p["map_policy"]
    assert m["approximate_geometry_forbidden"] is True
    assert m["parent_composite_polygon_forbidden"] is True
    assert m["risk_or_alert_layer"] is False
