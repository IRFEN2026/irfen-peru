import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_ana2015_quirio_pedregal_faja_context_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_contract_is_research_only_and_fail_closed():
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

def test_primary_ana_resolutions_confirm_documentary_relation_only():
    d=load()
    rows={x["local_unit_id"]:x for x in d["units"]}
    assert set(rows)=={"quirio","pedregal_san_antonio"}
    assert rows["quirio"]["documentary_receiver"]=="Rio Rimac"
    assert rows["pedregal_san_antonio"]["documentary_receiver"]=="Rio Rimac"
    assert rows["quirio"]["documentary_receiver_relation_confirmed"] is True
    assert rows["pedregal_san_antonio"]["documentary_receiver_relation_confirmed"] is True
    assert rows["quirio"]["faja_vertex_count"]==32
    assert rows["pedregal_san_antonio"]["faja_vertex_count"]==41

def test_regulatory_context_never_becomes_channel_outlet_or_event_geometry():
    d=load()
    for row in d["units"]:
        assert row["coordinate_material_role"]=="REGULATORY_CONTEXT_ONLY"
        assert row["official_channel_axis_geometry"] is None
        assert row["official_surface_confluence_confirmed"] is False
        assert row["exact_surface_confluence_coordinate"] is None
        assert row["regulatory_point_may_be_used_as_outlet_or_confluence"] is False
        assert row["faja_is_event_footprint"] is False
        assert row["q_i_t"] is None
        assert row["travel_time_tau"] is None
        assert row["receiver_response"] is None
        assert row["capacity"]=="UNKNOWN"

def test_no_map_routing_or_hydraulic_promotion():
    d=load()
    a=d["adjudication"]
    assert a["strengthens_named_unit_identity"] is True
    assert a["strengthens_documentary_tributary_to_rimac_relation"] is True
    for key in (
        "resolves_exact_surface_confluence",
        "resolves_channel_axis",
        "replaces_existing_d8_nodes",
        "creates_map_geometry",
        "enables_routing",
        "enables_travel_time_estimation",
        "establishes_receiver_capacity",
        "establishes_receiver_overflow",
    ):
        assert a[key] is False
    assert d["map_updates"]=={"new_geometries_published":0,"new_nodes_published":0}
