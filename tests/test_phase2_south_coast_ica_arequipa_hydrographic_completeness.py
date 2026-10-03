import json
from pathlib import Path

CFG = Path("config/phase2_south_coast_ica_arequipa_hydrographic_completeness_v0_1.json")

EXPECTED_PARENTS = {
    "arequipa_choclon": "137152",
    "arequipa_honda": "137158",
}

EXPECTED_INTERCUENCAS = {
    "ica_intercuenca_1373": "1373",
    "ica_intercuenca_13751": "13751",
    "ica_intercuenca_137531": "137531",
    "ica_intercuenca_137533": "137533",
    "arequipa_intercuenca_135": "135",
    "arequipa_intercuenca_13711": "13711",
    "arequipa_intercuenca_13713": "13713",
    "arequipa_intercuenca_137151": "137151",
    "arequipa_intercuenca_137153": "137153",
    "arequipa_intercuenca_137155": "137155",
    "arequipa_intercuenca_137157": "137157",
    "arequipa_intercuenca_137159": "137159",
    "arequipa_intercuenca_13717": "13717",
    "arequipa_intercuenca_13719": "13719",
}


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def test_hydrographic_completeness_package_is_fail_closed():
    cfg = load()
    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
    assert cfg["summary"]["geometry_assets_published"] == 0
    assert cfg["summary"]["new_operational_zones"] == 0


def test_choclon_and_honda_are_official_context_only_parents():
    cfg = load()
    rows = {x["discovery_id"]: x for x in cfg["official_parent_additions"]}
    assert set(rows) == set(EXPECTED_PARENTS)
    for row_id, code in EXPECTED_PARENTS.items():
        row = rows[row_id]
        assert row["official_unit_code"] == code
        assert row["entity_role"] == "OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
        assert row["identity_status"] == "OFFICIAL_ANA_UNIT_CONFIRMED"
        assert row["geometry_asset"] is None
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None

    honda = rows["arequipa_honda"]
    assert "Quequeña" in honda["homonym_guard"]
    assert "parent-UH match" in honda["homonym_guard"]


def test_official_intercuencas_are_preserved_as_independent_contexts():
    cfg = load()
    rows = {x["discovery_id"]: x for x in cfg["official_intercuenca_contexts"]}
    assert set(rows) == set(EXPECTED_INTERCUENCAS)
    assert cfg["summary"]["canonical_intercuenca_contexts_required"] == len(EXPECTED_INTERCUENCAS)
    for row_id, code in EXPECTED_INTERCUENCAS.items():
        row = rows[row_id]
        assert row["official_unit_code"] == code
        assert row["entity_role"] == "OFFICIAL_INTERCUENCA_CONTEXT_NON_ACTIVATABLE"
        assert row["geometry_asset"] is None
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None


def test_completeness_guards_prevent_false_assignment_and_event_transfer():
    cfg = load()
    rules = cfg["global_rules"]
    assert rules["official_parent_or_intercuenca_is_context_only"] is True
    assert rules["no_geometry_without_reproducible_source"] is True
    assert rules["intercuenca_must_not_be_absorbed_into_neighboring_named_basin"] is True
    assert rules["same_name_local_channel_must_not_be_conflated_with_official_basin"] is True
    assert rules["event_state_transfer_forbidden"] is True
    assert rules["critical_point_is_not_event"] is True
    assert rules["marginal_strip_is_not_event_footprint"] is True
    assert rules["work_or_design_is_not_historical_capacity"] is True
    assert rules["absence_of_report_is_not_negative_control"] is True


def test_sources_are_official_and_unarchived_hashes_are_not_faked():
    cfg = load()
    assert len(cfg["sources"]) == 2
    for src in cfg["sources"]:
        assert src["official"] is True
        assert src["url"].startswith("https://")
        assert src["content_sha256"] is None
        assert "NOT_ARCHIVED" in src["provenance_status"]
        assert src["forbidden_use"]
