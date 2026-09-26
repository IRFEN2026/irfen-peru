import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_senamhi2020_pedregal_microbasin_receiver_context_v0_1.json"

SAFE={
    "deployment_status":"RESEARCH_ONLY",
    "test_mode":"TEST_ONLY",
    "production_use":False,
    "production_ready":False,
    "operational_alerting_enabled":False,
    "activation_gate":"BLOCKED",
    "missing_data_rule":"UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds":None,
    "hydraulic_factors":None,
}

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_official_study_freezes_receiver_and_morphometry_only():
    d=load()
    for key,value in SAFE.items():
        assert d[key]==value
    s=d["source"]
    assert s["institution"].startswith("Servicio Nacional")
    assert s["document_id"]=="01401SENA-89"
    assert s["publication_date"]=="2020-05"
    u=d["local_unit"]
    assert u["local_unit_id"]=="pedregal_san_antonio"
    assert u["documentary_receiver"]=="Rio Rimac"
    assert u["documentary_receiver_relation_confirmed"] is True
    assert u["point_of_interest_description"]=="desembocadura en el rio Rimac"
    assert u["exact_surface_confluence_coordinate"] is None
    assert u["exact_surface_confluence_confirmed"] is False
    assert u["official_channel_axis_geometry"] is None
    assert u["official_microbasin_polygon_geometry"] is None
    assert u["reproducible_map_geometry_recovered"] is False

def test_source_reported_morphometry_is_not_promoted_to_routing():
    d=load()
    m=d["source_reported_morphometry"]
    assert m["area_km2"]==10.28
    assert m["perimeter_km"]==18.53
    assert m["main_channel_length_km"]==5.66
    assert m["mean_main_channel_slope_pct"]==14.74
    assert m["source_topography"]=="ALOS World 3D - 30m (AW3D30)"
    assert m["role"]=="SOURCE_REPORTED_MICROBASIN_MORPHOMETRY_NOT_IRFEN_ROUTING_PARAMETERS"
    c=d["coupling"]
    assert c["immediate_receiver"]=="rimac_mainstem_receiver"
    assert c["receiver_identity_supported"] is True
    assert c["exact_outlet_or_confluence_geometry_resolved"] is False
    for key in ("q_i_t","travel_time_tau","routing_method","attenuation_or_storage","receiver_response"):
        assert c[key] is None
    assert c["receiver_capacity"]=="UNKNOWN"
    assert c["overflow_inferred"] is False

def test_study_models_and_station_context_remain_non_operational():
    d=load()
    o=d["study_observation_context"]
    assert o["representative_precipitation_station"]=="Chosica"
    assert o["source_reported_period"]=="1990-2019"
    assert o["current_realtime_observation"] is False
    assert o["may_be_used_as_local_activation_observation_without_event_time_alignment"] is False
    m=d["modelling_context"]
    assert m["hydrologic_model"]=="TREX"
    assert m["debris_flow_model"]=="FLO-2D"
    assert m["modeled_potential_affected_zones_are_observed_event_footprints"] is False
    assert m["source_model_thresholds_are_irfen_decision_thresholds"] is False
    assert m["source_model_discharge_is_observed_receiver_response"] is False
    assert m["may_calibrate_irfen_child_to_receiver_transfer_automatically"] is False

def test_no_geometry_timing_capacity_threshold_or_overflow_promotion():
    d=load()
    a=d["adjudication"]
    assert a["strengthens_pedregal_microbasin_identity"] is True
    assert a["strengthens_documentary_receiver_relation_to_rimac"] is True
    assert a["freezes_source_reported_morphometry"] is True
    for key in (
        "resolves_exact_surface_confluence","resolves_official_channel_axis",
        "resolves_reproducible_microbasin_geometry","creates_map_geometry",
        "enables_child_routing","enables_travel_time_estimation",
        "establishes_receiver_capacity","establishes_receiver_overflow",
        "creates_irfen_decision_threshold",
    ):
        assert a[key] is False
    assert d["map_updates"]=={"new_geometries_published":0,"new_nodes_published":0}
