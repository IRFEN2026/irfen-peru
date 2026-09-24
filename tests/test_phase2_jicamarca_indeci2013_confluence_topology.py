import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_indeci2013_confluence_topology_v0_1.json"

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
    assert doc["status"] == "FROZEN_BOUNDED_DOCUMENTARY_TOPOLOGY_NO_COORDINATE_OR_ROUTING_PROMOTION"


def test_source_role_is_documentary_and_hash_not_fabricated():
    source = load()["source"]
    assert source["institution"] == "Instituto Nacional de Defensa Civil"
    assert source["publication_host"] == "CENEPRED SIGRID"
    assert source["publication_year"] == 2013
    assert source["source_role"] == "OFFICIAL_DOCUMENTARY_HYDROLOGIC_TOPOLOGY_CONTEXT_NOT_VECTOR_HYDROGRAPHY"
    assert source["binary_frozen_in_repo"] is False
    assert source["document_sha256"] is None


def test_huaycoloro_rio_seco_convergence_stays_documentary_only():
    finding = load()["bounded_topology_findings"]
    assert finding["huaycoloro_and_rio_seco_are_distinct_local_children"] is True
    assert finding["documentary_convergence_of_huaycoloro_and_rio_seco"] is True
    assert finding["downstream_named_reach_after_convergence"] == "jicamarca_named_channel"
    assert finding["scientific_effect"] == "STRENGTHENS_IMMEDIATE_DOWNSTREAM_TOPOLOGY_ONLY"
    assert finding["may_create_synthetic_quebrada_jicamarca_unit"] is False
    assert finding["may_union_huaycoloro_and_rio_seco_geometries"] is False
    assert finding["may_promote_parent_activation"] is False
    assert finding["may_infer_rimac_overflow"] is False


def test_spatial_resolution_remains_fail_closed():
    gate = load()["spatial_resolution_gate"]
    assert gate["exact_huaycoloro_rio_seco_confluence_coordinate_resolved"] is False
    assert gate["rio_seco_natural_channel_geometry_resolved"] is False
    assert gate["rio_seco_catchment_geometry_resolved"] is False
    assert gate["rio_seco_outlet_resolved"] is False
    assert gate["jicamarca_named_reach_geometry_resolved"] is False
    assert gate["jicamarca_to_rimac_connection_resolved"] is False
    assert gate["report_map_or_figure_is_reproducible_vector_geometry"] is False
    assert gate["digitization_of_report_figure_allowed_as_final_geometry"] is False
    assert gate["approximate_point_allowed"] is False
    assert gate["map_publication_from_this_source"] is False


def test_collector_coupling_is_unparameterized():
    coupling = load()["collector_coupling"]
    assert coupling["local_children"] == ["huaycoloro", "rio_seco"]
    assert coupling["immediate_downstream_context"] == "jicamarca_named_channel_after_huaycoloro_rio_seco_confluence"
    assert coupling["ultimate_receiver_context"] == "rimac_mainstem"
    assert coupling["ultimate_receiver_relation_status"] == "UNRESOLVED_BY_THIS_SOURCE"
    assert coupling["exact_confluence"] is None
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["receiver_stage_or_discharge_response"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["quality"] == "UNKNOWN"
    assert coupling["routing_enabled"] is False
    assert coupling["tributary_activation_implies_receiver_overflow"] is False


def test_no_event_negative_threshold_or_map_promotion():
    doc = load()
    policy = doc["event_and_threshold_policy"]
    assert all(value is False for value in policy.values())
    map_effect = doc["map_effect"]
    assert map_effect["new_geometry_created"] is False
    assert map_effect["parent_polygon_created"] is False
    assert map_effect["child_polygon_created"] is False
    assert map_effect["confluence_point_created"] is False
    assert map_effect["event_footprint_created"] is False
    assert map_effect["risk_or_alert_symbology_allowed"] is False

    forbidden = set(doc["forbidden"])
    assert "use A6680 as geometry calibration target" in forbidden
    assert "create negative controls from absence of reports" in forbidden
