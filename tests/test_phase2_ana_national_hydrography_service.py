import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_ana_national_hydrography_service_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_service_candidate_is_fail_closed():
    d=load()
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d["test_mode"]=="TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"]=="BLOCKED"
    assert d["status"]=="RESEARCH_ONLY_REPRODUCIBLE_VECTOR_SOURCE_CANDIDATE"

def test_source_is_queryable_vector_hydrography():
    d=load()
    s=d["source"]
    assert s["layer_id"]==0
    assert s["geometry_type"]=="esriGeometryPolyline"
    assert s["spatial_reference"]==4326
    assert "geoJSON" in s["supported_query_formats"]
    for field in ("CODIGO_CA","NOMBRE_CA","TIPO_CA","CODIGO_UH","NOMBRE_UH"):
        assert field in s["fields"]

def test_quirio_pedregal_probe_stays_unresolved_until_exact_query():
    d=load()
    p=d["quirio_pedregal_probe"]
    assert p["target_names"]==["Quirio","Pedregal"]
    assert p["exact_feature_query_completed"] is False
    assert p["matching_objectids"]==[]
    assert p["matching_feature_count"] is None
    assert p["exact_surface_confluence_resolved"] is False
    g=d["guards"]
    assert g["service_metadata_alone_confirms_local_feature"] is False
    assert g["name_match_alone_confirms_identity"] is False
    assert g["feature_endpoint_may_replace_d8_node_before_qa"] is False
    assert g["exact_surface_confluence_may_be_inferred_without_intersection_test"] is False
    assert g["map_publish_enabled"] is False
