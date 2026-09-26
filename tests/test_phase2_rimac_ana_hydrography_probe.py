import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/probe_phase2_rimac_ana_hydrography_service.py"
SPEC=importlib.util.spec_from_file_location("rimac_ana_probe",SCRIPT)
MOD=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)


def test_probe_query_is_bounded_and_reproducible():
    q=parse_qs(urlparse(MOD.query_url()).query)
    assert q["where"]==["1=1"]
    assert q["geometry"]==[",".join(str(x) for x in MOD.BBOX)]
    assert q["geometryType"]==["esriGeometryEnvelope"]
    assert q["spatialRel"]==["esriSpatialRelIntersects"]
    assert q["inSR"]==["4326"]
    assert q["outSR"]==["4326"]
    assert q["returnGeometry"]==["true"]
    assert q["f"]==["geojson"]


def test_probe_helper_is_fail_closed_after_literal_intersection():
    data={"type":"FeatureCollection","features":[
      {"type":"Feature","properties":{"NOMBRE_CA":"Quebrada Quirio","OBJECTID_1":1},"geometry":{"type":"LineString","coordinates":[[0,0],[2,2]]}},
      {"type":"Feature","properties":{"NOMBRE_CA":"Rimac","OBJECTID_1":2},"geometry":{"type":"LineString","coordinates":[[0,2],[2,0]]}},
    ]}
    doc=MOD.build(data)
    assert doc["query_completed"] is True
    assert len(doc["literal_intersection_candidates"])==1
    assert doc["adjudication"]["literal_line_intersection_confirms_official_confluence"] is False
    assert doc["adjudication"]["exact_surface_confluence_resolved"] is False
    assert doc["adjudication"]["routing_enabled"] is False
    assert doc["adjudication"]["travel_time_enabled"] is False
    assert doc["adjudication"]["map_publish_enabled"] is False


def test_source_access_failure_is_unknown_not_zero_candidates():
    doc=MOD.build_unavailable(TimeoutError("timed out"))
    assert doc["status"]=="SOURCE_ACCESS_UNAVAILABLE"
    assert doc["query_completed"] is False
    assert set(doc["candidate_counts"])=={"quirio","pedregal","rimac"}
    assert all(v is None for v in doc["candidate_counts"].values())
    assert doc["candidates"] is None
    assert doc["literal_intersection_candidates"] is None
    assert doc["access"]["zero_candidates_inferred"] is False
    assert doc["access"]["hydrologic_absence_inferred"] is False
    assert doc["adjudication"]["exact_surface_confluence_resolved"] is False
    assert doc["adjudication"]["replace_existing_d8_nodes"] is False
    assert doc["adjudication"]["routing_enabled"] is False
    assert doc["adjudication"]["travel_time_enabled"] is False
    assert doc["adjudication"]["map_publish_enabled"] is False
