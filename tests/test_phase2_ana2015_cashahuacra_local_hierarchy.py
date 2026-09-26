import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_ana2015_cashahuacra_local_hierarchy_v0_1.json"

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

def test_cashahuacra_alta_is_documentary_child_only():
    d=load()
    child=d["child_unit"]
    assert child["local_unit_id"]=="cashahuacra_alta"
    assert child["documentary_parent_unit_id"]=="cashahuacra"
    assert child["documentary_parent_relation_confirmed"] is True
    assert child["source_progressive_reference"]=="0+950"
    assert child["progressive_reference_is_exact_surface_confluence"] is False
    assert child["official_channel_axis_geometry"] is None
    assert child["exact_surface_confluence_coordinate"] is None
    assert child["q_i_t"] is None
    assert child["travel_time_tau"] is None
    assert child["receiver_response"] is None
    assert child["capacity"]=="UNKNOWN"

def test_hierarchy_does_not_create_routing_or_map_geometry():
    d=load()
    a=d["adjudication"]
    assert a["creates_distinct_child_identity"] is True
    assert a["resolves_documentary_parent_relation"] is True
    assert a["resolves_exact_surface_confluence"] is False
    assert a["creates_map_geometry"] is False
    assert a["enables_routing"] is False
    assert a["enables_travel_time_estimation"] is False
    assert a["establishes_parent_or_receiver_overflow"] is False
    assert d["map_updates"]=={"new_geometries_published":0,"new_nodes_published":0}
