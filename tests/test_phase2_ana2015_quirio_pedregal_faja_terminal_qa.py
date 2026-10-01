import json, math
from pathlib import Path
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_ana2015_quirio_pedregal_faja_terminal_qa_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])

def test_terminal_qa_is_reproducible_and_fail_closed():
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
    tr=Transformer.from_crs(d["analysis"]["source_crs"],d["analysis"]["analysis_crs"],always_xy=True)
    rows={x["local_unit_id"]:x for x in d["units"]}
    for unit_id,row in rows.items():
        xy=tr.transform(*row["frozen_d8_node_wgs84"])
        for source_key,range_key in (("Final","to_source_table_Final"),("H1_0+000_left_margin","to_H1_0+000_left_margin")):
            dist=distance(xy,row["source_table_coordinates_utm18s"][source_key])
            lo,hi=row["qa_distance_ranges_m"][range_key]
            assert lo <= dist <= hi, (unit_id,source_key,dist)
        assert row["official_surface_confluence_confirmed"] is False
        assert row["exact_surface_confluence_coordinate"] is None
        assert row["replace_existing_d8_node"] is False

def test_proximity_does_not_manufacture_confluence_routing_or_map_geometry():
    a=load()["adjudication"]
    assert a["strengthens_d8_spatial_consistency_with_official_lower_regulatory_references"] is True
    for key in (
      "regulatory_final_is_official_confluence","h1_margin_point_is_official_confluence",
      "average_of_margin_points_may_define_confluence","d8_node_becomes_official_confluence",
      "routing_enabled","travel_time_enabled","receiver_capacity_established",
      "receiver_overflow_established","map_geometry_created",
    ):
        assert a[key] is False
