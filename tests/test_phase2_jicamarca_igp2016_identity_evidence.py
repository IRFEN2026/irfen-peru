import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_igp2016_local_identity_evidence_v0_1.json"

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


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def test_scientific_guards_fail_closed():
    doc = load()
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert doc["status"] == "FROZEN_BOUNDED_DOCUMENTARY_IDENTITY_EVIDENCE_NO_GEOMETRY_PROMOTION"


def test_source_is_bounded_and_no_pdf_hash_is_fabricated():
    source = load()["source"]
    assert source["institutional_repository"] == "Instituto Geofisico del Peru"
    assert source["year"] == 2016
    assert source["pdf_sha256"] is None
    assert source["binary_frozen_in_repo"] is False
    assert source["source_role"] == "INSTITUTIONAL_REPOSITORY_SCIENTIFIC_ARTICLE_NOT_HYDROGRAPHIC_AUTHORITY_VECTOR_LAYER"


def test_rio_seco_identity_is_strengthened_without_colca_rebinding():
    findings = load()["bounded_identity_findings"]
    parent = findings["jicamarca_parent_context"]
    assert parent["scientific_effect"] == "SUPPORTS_LOCAL_CHILD_DECOMPOSITION_ONLY"
    assert parent["may_create_synthetic_quebrada_jicamarca_unit"] is False
    assert parent["may_promote_parent_activation"] is False

    rio_seco = findings["rio_seco_distinct_local_identity"]
    assert rio_seco["scientific_effect"] == "STRENGTHENS_DISTINCT_CHILD_IDENTITY_BUT_DOES_NOT_RESOLVE_EXACT_GEOMETRY_OR_OUTLET"
    assert rio_seco["may_equate_rio_seco_with_colca"] is False
    assert rio_seco["may_rebind_colca_faja_to_rio_seco"] is False


def test_report_mapping_and_territorial_coordinates_cannot_promote_geometry():
    doc = load()
    findings = doc["bounded_identity_findings"]
    mapping = findings["local_scale_mapping_context"]
    assert mapping["report_figure_is_reproducible_vector_geometry"] is False
    assert mapping["report_figure_digitization_allowed_as_final_geometry"] is False

    monitoring = findings["monitoring_context"]
    assert monitoring["station_location_is_outlet"] is False
    assert monitoring["station_location_is_confluence"] is False
    assert monitoring["station_location_may_define_channel_geometry"] is False

    territorial = findings["cajamarquilla_territorial_coordinate"]
    assert territorial["may_use_as_rio_seco_outlet"] is False
    assert territorial["may_use_as_jicamarca_outlet"] is False
    assert territorial["may_use_as_receiver_confluence"] is False

    gate = doc["geometry_gate"]
    assert gate["rio_seco_channel_geometry_reproducible_from_this_source"] is False
    assert gate["rio_seco_catchment_geometry_reproducible_from_this_source"] is False
    assert gate["rio_seco_outlet_reproducible_from_this_source"] is False
    assert gate["rio_seco_receiver_confluence_reproducible_from_this_source"] is False
    assert gate["map_publishable_geometry_from_this_source"] is False
    assert gate["event_footprint_reproducible_from_this_source"] is False


def test_historical_context_cannot_become_controls_thresholds_or_routing():
    doc = load()
    hist = doc["bounded_historical_context"]
    assert hist["attribution_status"] == "PARENT_CONTEXT_ONLY_CHILD_ATTRIBUTION_NOT_RESOLVED_BY_THIS_SOURCE"
    assert hist["may_assign_all_events_to_rio_seco"] is False
    assert hist["may_assign_all_events_to_huaycoloro"] is False
    assert hist["may_create_negative_controls_from_unmentioned_years"] is False
    assert hist["may_fit_geometry_to_event_outcomes"] is False
    assert hist["may_calibrate_thresholds"] is False
    assert hist["1998_documentary_coupling_may_define_Q_i_t"] is False
    assert hist["1998_documentary_coupling_may_define_travel_time"] is False
    assert hist["1998_documentary_coupling_may_define_attenuation"] is False
    assert hist["1998_documentary_coupling_may_define_hydraulic_capacity"] is False
    assert hist["tributary_activation_implies_rimac_overflow"] is False

    coupling = doc["collector_coupling"]
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["quality"] == "UNKNOWN"
    assert coupling["receiver_stage_or_discharge_response"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["tributary_activation_implies_receiver_overflow"] is False


def test_no_map_effect_or_a6680_geometry_calibration():
    doc = load()
    assert doc["map_effect"] == "NONE_NEW_DOCUMENTARY_EVIDENCE_ONLY"
    forbidden = set(doc["geometry_gate"]["forbidden_shortcuts"])
    assert "use_A6680_as_geometry_calibration_target" in forbidden
    assert "union_distinct_children_into_synthetic_Jicamarca_activation_polygon" in forbidden
    assert "rebind_ANA_Qda_Colca_faja_to_Rio_Seco" in forbidden
