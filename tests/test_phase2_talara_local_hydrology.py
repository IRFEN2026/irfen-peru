import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_talara_parinas_local_ravines.json"
SRC = ROOT / "site/data/phase2/sources/piura_talara_official_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_talara_package_is_fail_closed():
    p = load(PKG)
    assert p["deployment_status"] == "RESEARCH_ONLY"
    assert p["test_mode"] == "TEST_ONLY"
    assert p["production_use"] is False
    assert p["production_ready"] is False
    assert p["operational_alerting_enabled"] is False
    assert p["activation_gate"] == "BLOCKED"
    assert p["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None
    assert p["territorial_identity"]["parent_activation_synthesis_forbidden"] is True


def test_named_local_channels_remain_independent_and_unmapped():
    p = load(PKG)
    required = {
        "quebrada_parinas",
        "quebrada_acholado",
        "quebrada_debora",
        "quebrada_santa_rita",
        "quebrada_politecnico",
        "quebrada_yale",
        "quebrada_mangle",
        "quebrada_de_la_pena",
    }
    assert required.issubset(p["hydrologic_components"])
    for key in required:
        child = p["hydrologic_components"][key]
        assert child["geometry_status"].startswith("MISSING_")
        assert child["map_materialization_allowed"] is False
    assert p["map_policy"]["synthetic_union_forbidden"] is True


def test_critical_points_are_context_not_events_or_outlets():
    p = load(PKG)
    assert len(p["context_nodes"]) >= 3
    for node in p["context_nodes"]:
        assert node["is_observed_event"] is False
        assert node["is_outlet"] is False
        assert node["map_materialization_allowed"] is False
        assert "CRITICAL_POINT" in node["role"] or "CRITICAL_POINT" in node["role"].upper()


def test_historical_windows_do_not_fabricate_negatives_or_child_attribution():
    p = load(PKG)
    for key in ("1982_1983", "1997_1998"):
        event = p["event_ledger"][key]
        assert event["status"] == "UNKNOWN_NOT_NEGATIVE_CHILD_LEVEL_SOURCE_GAP"
        assert event["local_child_activation_assigned"] is False
        assert event["absence_of_local_report_is_negative"] is False
        assert event["source_ids"] == []

    for key in ("2017", "2023"):
        event = p["event_ledger"][key]
        assert event["direct_flow_evidence"] is False
        assert event["exact_child_event_footprint_available"] is False
        assert event["other_ravines_activation_assigned"] is False
        assert event["operational_threshold_inferred"] is False


def test_collector_coupling_stays_blocked_without_geometry_and_observations():
    p = load(PKG)
    c = p["collector_coupling"]
    assert c["status"].startswith("BLOCKED_")
    assert c["q_i_t_allowed"] is False
    assert c["travel_time_allowed"] is False
    assert c["attenuation_allowed"] is False
    assert c["synthetic_receiver_assignment_forbidden"] is True


def test_official_source_registry_has_explicit_forbidden_inferences():
    s = load(SRC)
    assert s["deployment_status"] == "RESEARCH_ONLY"
    assert s["test_mode"] == "TEST_ONLY"
    assert s["production_use"] is False
    assert s["production_ready"] is False
    assert s["operational_alerting_enabled"] is False
    assert s["activation_gate"] == "BLOCKED"
    assert s["decision_thresholds"] is None
    assert s["hydraulic_factors"] is None
    ids = {x["source_id"] for x in s["sources"]}
    assert {
        "INDECI-PNUD-TALARA-2010",
        "CENEPRED-TALARA-PPRRD-2019-2022",
        "CENEPRED-TALARA-EVAR-2017",
        "CONTRALORIA-TALARA-ACHOLADO-2023",
        "OEFA-TALARA-ACHOLADO-2025",
    }.issubset(ids)
    for source in s["sources"]:
        assert source["admissible_claims"]
        assert source["forbidden_inferences"]


def test_source_semantics_do_not_promote_context_to_activation_or_capacity():
    s = load(SRC)
    qa = s["qa"]
    assert qa["territorial_corridor_is_basin"] is False
    assert qa["named_channels_auto_merged"] is False
    assert qa["critical_points_used_as_events"] is False
    assert qa["critical_points_used_as_outlets"] is False
    assert qa["generic_el_nino_context_used_as_dated_child_activation"] is False
    assert qa["absence_of_report_is_negative"] is False
    assert qa["provider_or_report_hazard_classes_are_irfen_thresholds"] is False
    assert qa["works_or_infrastructure_used_as_hydraulic_capacity"] is False
