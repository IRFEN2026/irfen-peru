import json
from pathlib import Path

CFG = Path("config/phase2_south_coast_rio_seco_homonym_v0_1.json")


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def test_guardrails_remain_fail_closed():
    c = load()
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["test_mode"] == "TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"] == "BLOCKED"
    assert c["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    assert c["summary"]["geometry_assets_published"] == 0
    assert c["summary"]["new_operational_zones"] == 0


def test_rio_seco_homonyms_are_separate():
    c = load()
    rows = {x["child_id"]: x for x in c["channel_identities"]}
    assert set(rows) == {"ica_rio_seco_salas", "arequipa_rio_seco_cerro_colorado"}

    ica = rows["ica_rio_seco_salas"]
    aqp = rows["arequipa_rio_seco_cerro_colorado"]

    assert ica["expected_parent_uh_code"] == "13751"
    assert ica["official_course_code"] == "137516"
    assert aqp["expected_parent_uh_code"] == "13254"
    assert aqp["ancestor_uh_codes"] == ["132", "1325", "13254"]

    guard = c["homonym_guard"]
    pairs = {(x["child_id"], x["parent_uh_code"], x["region"]) for x in guard["distinct_units"]}
    assert pairs == {
        ("ica_rio_seco_salas", "13751", "Ica"),
        ("arequipa_rio_seco_cerro_colorado", "13254", "Arequipa"),
    }


def test_no_geometry_or_outlet_is_promoted():
    c = load()
    for row in c["channel_identities"]:
        assert row["geometry_asset"] is None
        assert row["outlet"] is None
        assert row["map_publishable"] is False
        assert row["event_state_transferred"] is False

    assert c["rules"]["faja_marginal_is_not_channel_axis"] is True
    assert c["rules"]["faja_marginal_is_not_event_footprint"] is True
    assert c["rules"]["design_discharge_is_not_historical_capacity"] is True


def test_sources_have_bounded_use_and_no_fake_hashes():
    c = load()
    assert len(c["sources"]) == 3
    for s in c["sources"]:
        assert s["official"] is True
        assert s["source_content_sha256"] is None
        assert s["forbidden_use"]
        assert s["supports"]


def test_next_geometry_actions_require_parent_match():
    c = load()
    actions = {x["child_id"]: x["action"] for x in c["next_geometry_actions"]}
    assert "137516" in actions["ica_rio_seco_salas"]
    assert "13751" in actions["ica_rio_seco_salas"]
    assert "13254" in actions["arequipa_rio_seco_cerro_colorado"]
