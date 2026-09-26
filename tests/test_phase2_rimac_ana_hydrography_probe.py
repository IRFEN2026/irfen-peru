import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/probe_phase2_rimac_ana_hydrography_service.py"
SPEC=importlib.util.spec_from_file_location("rimac_ana_probe",SCRIPT)
MOD=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)

def test_probe_helper_is_fail_closed_after_literal_intersection():
    data={"type":"FeatureCollection","features":[
      {"type":"Feature","properties":{"NOMBRE_CA":"Quebrada Quirio","OBJECTID_1":1},"geometry":{"type":"LineString","coordinates":[[0,0],[2,2]]}},
      {"type":"Feature","properties":{"NOMBRE_CA":"Rimac","OBJECTID_1":2},"geometry":{"type":"LineString","coordinates":[[0,2],[2,0]]}},
    ]}
    doc=MOD.build(data)
    assert len(doc["literal_intersection_candidates"])==1
    assert doc["adjudication"]["literal_line_intersection_confirms_official_confluence"] is False
    assert doc["adjudication"]["exact_surface_confluence_resolved"] is False
    assert doc["adjudication"]["routing_enabled"] is False
    assert doc["adjudication"]["travel_time_enabled"] is False
    assert doc["adjudication"]["map_publish_enabled"] is False
