import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT = ROOT / "config/phase2_jicamarca_rio_seco_minam_hydrography_probe_closeout_v0_1.json"
FROZEN = ROOT / "site/data/phase2/sources/jicamarca_rio_seco_minam/probe_result_v0_1.json"
PRIOR = ROOT / "config/phase2_jicamarca_rio_seco_ign_hydrography_probe_closeout_v0_1.json"

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


def test_closeout_and_frozen_result_exist_and_are_fail_closed():
    closeout = load(CLOSEOUT)
    frozen = load(FROZEN)
    assert PRIOR.exists()
    for key, expected in SAFE.items():
        assert closeout[key] == expected
        assert frozen[key] == expected
    assert closeout["status"] == "FROZEN_NO_NAMED_CANDIDATE_SOURCE_GAP"
    assert frozen["status"] == "PASS_BOUNDED_MINAM_RIO_SECO_HYDROGRAPHY_CANDIDATE_PROBE"


def test_frozen_source_hashes_match_closeout_exactly():
    closeout = load(CLOSEOUT)
    frozen = load(FROZEN)
    source = closeout["source_result"]
    assert source["candidate_count"] == frozen["candidate_count"] == 0
    assert source["metadata_response_sha256"] == frozen["source"]["metadata_response_sha256"]
    assert source["query_response_sha256"] == frozen["source"]["query_response_sha256"]
    assert frozen["candidates"] == []


def test_zero_candidates_do_not_become_absence_negative_or_relaxed_missing_data():
    disposition = load(CLOSEOUT)["scientific_disposition"]
    for key in (
        "rio_seco_natural_channel_resolved",
        "rio_seco_catchment_resolved",
        "rio_seco_outlet_resolved",
        "huaycoloro_rio_seco_exact_confluence_resolved",
        "jicamarca_named_reach_resolved",
        "jicamarca_to_rimac_relation_resolved",
        "zero_candidates_is_evidence_rio_seco_does_not_exist",
        "zero_candidates_is_negative_event_evidence",
        "zero_candidates_may_be_used_as_negative_control",
        "zero_candidates_may_relax_missing_data_rule",
        "agreement_with_prior_ign_zero_candidate_result_is_evidence_of_absence",
        "fallback_to_quarantined_qda_colca_allowed",
        "fallback_to_unrelated_same_name_rio_seco_allowed",
        "approximate_or_manual_digitized_geometry_allowed",
        "event_outcome_fitted_geometry_allowed",
        "A6680_geometry_calibration_allowed",
    ):
        assert disposition[key] is False


def test_collector_and_map_remain_unresolved_and_non_operational():
    closeout = load(CLOSEOUT)
    coupling = closeout["collector_coupling"]
    assert coupling["receiver"] == "rimac_mainstem"
    assert coupling["connectivity"] == "UNRESOLVED_NOT_ASSUMED"
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["quality"] == "UNKNOWN"
    assert coupling["routing_enabled"] is False
    assert coupling["peak_coincidence"] is None
    assert coupling["receiver_stage_or_discharge_response"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
    effect = closeout["map_effect"]
    assert effect["new_geometry_created"] is False
    assert effect["new_map_layer_created"] is False
    assert effect["parent_geometry_created"] is False
    assert effect["outlet_or_confluence_created"] is False
    assert effect["event_footprint_created"] is False
    assert effect["risk_or_alert_symbology_allowed"] is False
