import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_minam2020_huaycoloro_vector_source_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_contract_is_fail_closed():
    d=load()
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d["test_mode"]=="TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"]=="BLOCKED"
    assert d["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None

def test_source_is_independent_vector_candidate_not_local_proof():
    d=load()
    s=d["source"]
    assert s["layer_id"]==10
    assert s["layer_name"]=="Ríos y quebradas"
    assert s["geometry_type"]=="esriGeometryPolyline"
    assert s["spatial_reference"]==32718
    assert "geoJSON" in s["supported_query_formats"]
    assert s["attribution"]=="IMP/ANA"
    assert set(s["renderer_name_evidence"]["labels_observed"])=={"RIMAC","HUAYCOLORO"}
    assert s["renderer_name_evidence"]["semantic_limit"]=="RENDERER_OR_SERVICE_METADATA_NAME_EVIDENCE_ONLY"

def test_huaycoloro_rimac_local_geometry_and_topology_remain_unresolved():
    d=load()
    p=d["huaycoloro_rimac_probe"]
    assert p["target_names"]==["HUAYCOLORO","RIMAC"]
    assert p["exact_feature_query_completed"] is False
    assert p["matching_objectids"]==[]
    assert p["matching_feature_count"] is None
    assert p["local_feature_geometry_frozen"] is False
    assert p["exact_huaycoloro_rimac_confluence_resolved"] is False
    assert "FREEZE_PAYLOAD_HASH" in p["required_next_step"]

def test_metadata_cannot_promote_hydrology_or_operations():
    g=load()["guards"]
    assert g["service_metadata_alone_confirms_local_feature"] is False
    assert g["renderer_name_alone_confirms_local_feature"] is False
    assert g["name_match_alone_confirms_identity"] is False
    assert g["metadata_may_define_catchment_geometry"] is False
    assert g["metadata_may_define_outlet_or_confluence"] is False
    assert g["metadata_may_define_routing_or_travel_time"] is False
    assert g["metadata_may_define_flow_or_capacity"] is False
    assert g["metadata_may_define_event_footprint"] is False
    assert g["zero_query_result_may_be_inferred_as_hydrologic_absence"] is False
    assert g["map_publish_enabled"] is False
    assert g["routing_enabled"] is False
    assert g["overflow_inference_enabled"] is False
