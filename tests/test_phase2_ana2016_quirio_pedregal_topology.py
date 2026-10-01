import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_ana2016_quirio_pedregal_topology_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_fail_closed_contract():
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

def test_ana_documentary_context_does_not_create_exact_confluence():
    d=load()
    units={x["local_unit_id"]:x for x in d["units"]}
    assert set(units)=={"quirio","pedregal_san_antonio"}
    for row in units.values():
        assert row["documentary_surface_topology"] is True
        assert row["official_surface_confluence_confirmed"] is False
        assert row["exact_surface_confluence_coordinate"] is None
        assert row["official_channel_axis_geometry"] is None
        assert row["exposure_point_may_be_used_as_confluence"] is False
        assert row["referential_zone_is_event_footprint"] is False

def test_no_hydraulic_or_operational_promotion():
    d=load()
    for row in d["units"]:
        assert row["q_i_t"] is None
        assert row["travel_time_tau"] is None
        assert row["receiver_response"] is None
        assert row["capacity"]=="UNKNOWN"
    a=d["adjudication"]
    assert a["resolves_exact_surface_confluence"] is False
    assert a["replaces_existing_d8_nodes"] is False
    assert a["creates_map_geometry"] is False
    assert a["enables_routing"] is False
    assert a["enables_travel_time_estimation"] is False
    assert a["establishes_receiver_capacity"] is False
    assert a["establishes_receiver_overflow"] is False
    assert d["map_updates"]=={"new_geometries_published":0,"new_nodes_published":0}

def test_source_roles_are_context_only():
    d=load()
    refs={x["source_id"]:x for x in d["source_refs"]}
    assert refs["ANA_2016_QUIRIO_MAP_89"]["mapped_zone_role"]=="REFERENTIAL_INUNDATION_CONTEXT_ONLY"
    assert refs["ANA_2016_PEDREGAL_MAP_33"]["mapped_zone_role"]=="REFERENTIAL_INUNDATION_CONTEXT_ONLY"
    assert refs["ANA_2016_2017_NATIONAL_INVENTORY"]["role"]=="IDENTITY_CONTEXT_ONLY"
