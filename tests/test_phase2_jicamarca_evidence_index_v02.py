import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_2.json"
ASSESSMENT = "config/phase2_jicamarca_canto_grande_media_luna_assessment_v0_2.json"
MONITORING_TOPOLOGY = "config/phase2_jicamarca_rio_seco_huaycoloro_monitoring_topology_v0_1.json"

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
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_index_v02_preserves_fail_closed_guards_and_versions_v01():
    index = load()
    for key, expected in SAFE.items():
        assert index[key] == expected
    assert index["extends"] == "config/phase2_jicamarca_evidence_index_v0_1.json"
    assert index["status"] == "RESEARCH_ONLY_EVIDENCE_INDEX_CHILD_CHANNEL_GEOMETRY_FROZEN"


def test_index_promotes_only_official_child_channel_context_not_outlets_or_catchments():
    index = load()
    package = next(row for row in index["packages"] if row["path"] == ASSESSMENT)
    assert package["role"] == "OFFICIAL_IGP_CHILD_CHANNEL_GEOMETRY_AND_FAIL_CLOSED_OUTLET_GATE"
    assert package["may_define_channel_geometry"] is True
    assert package["may_define_catchment_geometry"] is False
    assert package["may_define_outlet"] is False
    assert package["may_use_channel_endpoint_as_outlet"] is False
    assert package["may_use_event_outcome_to_fit_geometry"] is False
    assert package["may_promote_parent_activation"] is False
    assert package["may_promote_rimac_overflow"] is False
    assert (ROOT / ASSESSMENT).is_file()


def test_index_keeps_rio_seco_colca_semantic_quarantine_and_collector_blocked():
    index = load()
    assert "QDA_COLCA_FROZEN_FAJA_DO_NOT_USE_AS_RIO_SECO" in index["semantic_quarantine_effect"]
    assert "CANTO_GRANDE_AND_MEDIA_LUNA_OFFICIAL_CHANNEL_LINES_ARE_SEPARATE_LOCAL_CHILD_CONTEXTS_AND_MUST_NOT_BE_UNIONED" in index["semantic_quarantine_effect"]
    assert index["collector_effect"] == "NO_OUTLET_PROMOTION_NO_Q_TRAVEL_TIME_ATTENUATION_PEAK_COINCIDENCE_OR_RECEIVER_RESPONSE_PROMOTION"


def test_index_map_effect_is_channel_context_only():
    effect = load()["map_effect"]
    assert effect.startswith("OFFICIAL_CANTO_GRANDE_AND_MEDIA_LUNA_CHILD_CHANNEL_LINES_MAY_BE_PUBLISHED_AS_RESEARCH_CONTEXT_ONLY")
    assert "CATCHMENT_POLYGONS_OUTLETS_EVENT_FOOTPRINTS_AND_PARENT_ACTIVATION_REMAIN_WITHHELD" in effect


def test_monitoring_topology_is_indexed_without_promoting_geometry_or_routing():
    index = load()
    package = next(row for row in index["packages"] if row["path"] == MONITORING_TOPOLOGY)
    assert (ROOT / MONITORING_TOPOLOGY).is_file()
    assert package["role"] == "IGP_DOCUMENTARY_LOCAL_CONVERGENCE_EXACT_NODE_GEOMETRY_UNRESOLVED"
    assert package["documents_distinct_rio_seco_huaycoloro_convergence"] is True
    for key in (
        "may_define_exact_confluence",
        "may_define_outlet",
        "may_define_Q_i_t",
        "may_define_travel_time",
        "may_define_attenuation",
        "may_infer_rimac_connection",
        "may_promote_receiver_overflow",
        "may_create_map_geometry",
    ):
        assert package[key] is False


def test_monitoring_topology_package_itself_remains_fail_closed():
    package = json.loads((ROOT / MONITORING_TOPOLOGY).read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        assert package[key] == expected
    adjudication = package["cross_source_adjudication"]
    assert adjudication["rio_seco_and_huaycoloro_are_distinct_local_children"] is True
    assert adjudication["exact_confluence_coordinate"] is None
    assert adjudication["exact_confluence_geometry_resolved"] is False
    assert adjudication["downstream_receiver_identity_resolved_by_this_package"] is False
    assert adjudication["rimac_connection_resolved_by_this_package"] is False
    assert adjudication["map_geometry_created"] is False
    assert adjudication["receiver_overflow_inferred"] is False
