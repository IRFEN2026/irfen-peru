import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT = ROOT / "config/phase2_jicamarca_rio_seco_ign_hydrography_probe_closeout_v0_1.json"
RESULT = ROOT / "site/data/phase2/sources/jicamarca_rio_seco_ign/probe_result_v0_1.json"
PROBE = ROOT / "config/phase2_jicamarca_rio_seco_ign_hydrography_probe_v0_1.json"

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


def test_closeout_binds_exact_probe_and_frozen_result():
    doc = load(CLOSEOUT)
    result = load(RESULT)
    assert PROBE.exists()
    assert doc["probe_contract"] == "config/phase2_jicamarca_rio_seco_ign_hydrography_probe_v0_1.json"
    assert doc["frozen_probe_result"] == "site/data/phase2/sources/jicamarca_rio_seco_ign/probe_result_v0_1.json"
    assert doc["source_result"]["candidate_count"] == 0
    assert result["candidate_count"] == 0
    assert result["candidates"] == []
    assert doc["source_result"]["metadata_response_sha256"] == result["source"]["metadata_response_sha256"]
    assert doc["source_result"]["query_response_sha256"] == result["source"]["query_response_sha256"]
    assert doc["source_result"]["result_interpretation"] == "NO_NAMED_SECO_CANDIDATE_RETURNED_BY_THIS_BOUNDED_QUERY_ONLY"


def test_closeout_and_frozen_result_keep_all_scientific_guards():
    doc = load(CLOSEOUT)
    result = load(RESULT)
    for key, expected in SAFE.items():
        assert doc[key] == expected
        assert result[key] == expected


def test_zero_candidates_is_not_absence_or_negative_evidence():
    disposition = load(CLOSEOUT)["scientific_disposition"]
    assert disposition["rio_seco_natural_channel_resolved"] is False
    assert disposition["rio_seco_catchment_resolved"] is False
    assert disposition["rio_seco_outlet_resolved"] is False
    assert disposition["huaycoloro_rio_seco_exact_confluence_resolved"] is False
    assert disposition["jicamarca_named_reach_resolved"] is False
    assert disposition["jicamarca_to_rimac_relation_resolved"] is False
    assert disposition["zero_candidates_is_evidence_rio_seco_does_not_exist"] is False
    assert disposition["zero_candidates_is_negative_event_evidence"] is False
    assert disposition["zero_candidates_may_be_used_as_negative_control"] is False
    assert disposition["zero_candidates_may_relax_missing_data_rule"] is False


def test_no_fallback_to_contaminating_or_invented_geometry():
    disposition = load(CLOSEOUT)["scientific_disposition"]
    assert disposition["fallback_to_quarantined_qda_colca_allowed"] is False
    assert disposition["fallback_to_rejected_same_name_igp_feature_allowed"] is False
    assert disposition["approximate_or_manual_digitized_geometry_allowed"] is False
    assert disposition["event_outcome_fitted_geometry_allowed"] is False
    assert disposition["A6680_geometry_calibration_allowed"] is False


def test_collector_and_map_remain_unresolved_and_non_operational():
    doc = load(CLOSEOUT)
    coupling = doc["collector_coupling"]
    assert coupling["receiver"] == "rimac_mainstem"
    assert coupling["connectivity"] == "UNRESOLVED_NOT_ASSUMED"
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["routing_enabled"] is False
    assert coupling["peak_coincidence"] is None
    assert coupling["receiver_stage_or_discharge_response"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
    effect = doc["map_effect"]
    assert effect["new_geometry_created"] is False
    assert effect["new_map_layer_created"] is False
    assert effect["parent_geometry_created"] is False
    assert effect["outlet_or_confluence_created"] is False
    assert effect["event_footprint_created"] is False
    assert effect["risk_or_alert_symbology_allowed"] is False
