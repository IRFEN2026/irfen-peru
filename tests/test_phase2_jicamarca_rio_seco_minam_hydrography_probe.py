import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/phase2_jicamarca_rio_seco_minam_hydrography_probe_v0_1.json"
DISCOVERY = ROOT / "config/phase2_jicamarca_discovery_v0_2.json"
EVIDENCE = ROOT / "config/phase2_jicamarca_evidence_index_v0_6.json"
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


def load(path=CONFIG):
    return json.loads(path.read_text(encoding="utf-8"))


def test_probe_is_bound_to_current_jicamarca_closed_state():
    doc = load()
    assert DISCOVERY.exists()
    assert EVIDENCE.exists()
    assert PRIOR.exists()
    assert doc["effective_discovery_contract"] == "config/phase2_jicamarca_discovery_v0_2.json"
    assert doc["evidence_index"] == "config/phase2_jicamarca_evidence_index_v0_6.json"
    assert doc["prior_probe_closeout"] == "config/phase2_jicamarca_rio_seco_ign_hydrography_probe_closeout_v0_1.json"
    assert doc["system_id"] == "lima_este_jicamarca_huaycoloro_rioseco_canto_grande"
    assert doc["component_id"] == "rio_seco"


def test_scientific_guards_are_exact_and_fail_closed():
    doc = load()
    for key, expected in SAFE.items():
        assert doc[key] == expected


def test_query_uses_independent_official_minam_hydrography_and_coarse_window_only():
    doc = load()
    source = doc["source"]
    assert source["institution"] == "Ministerio del Ambiente del Peru"
    assert source["publication_host"] == "Geoservidor MINAM"
    assert source["layer_id"] == 6
    assert source["expected_layer_name"] == "Hidrografía"
    assert source["expected_geometry_type"] == "esriGeometryPolyline"
    assert source["service_spatial_reference_wkid"] == 32718
    assert source["source_role"].startswith("OFFICIAL_PUBLIC_HYDROGRAPHY_CANDIDATE_SOURCE")
    window = doc["query_window"]
    assert window["basis"] == "INDECI_2013_JICAMARCA_SUBBASIN_DOCUMENTARY_BOUNDS"
    assert window["buffer_applied"] is False
    assert window["role"] == "COARSE_DOCUMENTARY_DISCOVERY_WINDOW_ONLY_NOT_CATCHMENT_GEOMETRY"
    assert doc["query"]["return_geometry"] is True
    assert doc["query"]["output_spatial_reference_wkid"] == 4326


def test_candidate_lines_cannot_be_promoted_by_name_or_intersection():
    policy = load()["candidate_policy"]
    for key in (
        "candidate_is_accepted_rio_seco_channel",
        "name_match_is_sufficient_identity",
        "documentary_window_is_catchment_geometry",
        "line_endpoint_is_outlet",
        "line_intersection_is_confluence_without_independent_topology_review",
        "line_length_may_define_travel_time",
        "candidate_may_define_Q_i_t",
        "candidate_may_define_attenuation",
        "candidate_may_define_hydraulic_capacity",
        "candidate_may_define_event_footprint",
        "candidate_may_enable_routing",
        "candidate_may_promote_parent_activation",
        "candidate_may_promote_rimac_overflow",
    ):
        assert policy[key] is False
    for key in (
        "selection_requires_separate_frozen_identity_and_topology_review",
        "selection_must_not_use_event_outcomes",
        "selection_must_not_use_A6680",
        "selection_must_not_use_quarantined_qda_colca_as_rio_seco_geometry",
        "same_name_feature_outside_jicamarca_window_must_not_be_rebound",
    ):
        assert policy[key] is True


def test_cross_source_identity_and_collector_rules_remain_strict():
    doc = load()
    cross = doc["cross_source_constraints"]
    assert cross["rio_seco_must_remain_distinct_from_colca"] is True
    assert cross["rio_seco_must_remain_distinct_from_huaycoloro"] is True
    assert cross["synthetic_quebrada_jicamarca_unit_allowed"] is False
    assert cross["candidate_must_be_compatible_with_documentary_huaycoloro_rio_seco_convergence_before_promotion"] is True
    assert cross["exact_confluence_coordinate_is_resolved_by_this_probe"] is False
    assert cross["jicamarca_named_reach_is_resolved_by_this_probe"] is False
    assert cross["jicamarca_to_rimac_receiver_relation_is_resolved_by_this_probe"] is False
    assert cross["prior_ign_zero_candidate_result_is_negative_evidence"] is False
    assert cross["minam_and_ign_linework_agreement_if_any_is_sufficient_identity"] is False
    coupling = doc["collector_coupling"]
    assert coupling["receiver"] == "rimac_mainstem"
    assert coupling["connectivity"] == "UNRESOLVED_NOT_ASSUMED"
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["quality"] == "UNKNOWN"
    assert coupling["routing_enabled"] is False
    assert coupling["tributary_activation_implies_receiver_overflow"] is False


def test_probe_has_no_map_or_operational_effect():
    effect = load()["map_effect"]
    assert effect["candidate_geometry_may_be_published"] is False
    assert effect["parent_geometry_created"] is False
    assert effect["event_footprint_created"] is False
    assert effect["risk_or_alert_symbology_allowed"] is False
