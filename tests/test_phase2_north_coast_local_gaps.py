import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INV=ROOT/"config/phase2_north_coast_discovery_inventory_v0_1.json"
MAN=ROOT/"site/data/validation/phase2_discovery_packages/piura_mancora_los_organos_coastal_ravines.json"
CHI=ROOT/"site/data/validation/phase2_discovery_packages/lalibertad_chicama.json"
PAI=ROOT/"site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json"
TAL=ROOT/"site/data/validation/phase2_discovery_packages/piura_talara_parinas_local_ravines.json"

def load(p): return json.loads(p.read_text(encoding="utf-8"))

def test_new_piura_units_are_fail_closed():
    inv=load(INV)
    ids={x["discovery_id"] for x in inv["discovery_units"]}
    assert "piura_paita_urban_local_ravines" in ids
    assert "piura_talara_parinas_local_ravines" in ids
    for p in (load(PAI),load(TAL)):
        assert p["deployment_status"]=="RESEARCH_ONLY"
        assert p["test_mode"]=="TEST_ONLY"
        assert p["production_use"] is False
        assert p["production_ready"] is False
        assert p["operational_alerting_enabled"] is False
        assert p["activation_gate"]=="BLOCKED"
        assert p["decision_thresholds"] is None
        assert p["hydraulic_factors"] is None
        assert p["map_policy"]["parent_polygon_forbidden"] is True

def test_vichayito_is_explicit_but_not_promoted():
    p=load(MAN)
    v=p["hydrologic_components"]["quebrada_vichayito"]
    assert v["identity_status"]=="OFFICIAL_PROVINCIAL_PPRRD_NAME_CONFIRMED"
    assert v["activation_verified"] is False
    assert v["geometry_status"]=="MISSING_NO_APPROXIMATION_ALLOWED"

def test_cartavio_santiago_are_exposure_nodes_not_basins():
    p=load(CHI)
    nodes={x["node_id"]:x for x in p["assets"]["exposure_connectivity"]["territorial_nodes"]}
    assert nodes["cartavio"]["is_hydrologic_basin"] is False
    assert nodes["santiago_de_cao"]["is_hydrologic_basin"] is False

def test_paita_is_separate_from_colan_and_separates_mechanisms():
    p=load(PAI)
    assert p["territorial_identity"]["colan_is_separate"] is True
    assert p["hydrologic_components"]["paita_alta_blind_basins"]["is_natural_ravine"] is False
    assert p["event_ledger"]["2017"]["transfer_to_other_ravines_forbidden"] is True


def test_paita_historical_windows_do_not_overassign_children():
    p=load(PAI)
    e83=p["event_ledger"]["1982_1983"]
    assert e83["status"]=="POSITIVE_EL_ZANJON_TERRITORIAL_OVERFLOW_CONTEXT"
    assert e83["transfer_to_other_ravines_forbidden"] is True
    assert e83["exact_event_footprint_available"] is False
    assert e83["operational_threshold_inferred"] is False

    e98=p["event_ledger"]["1997_1998"]
    assert e98["status"]=="UNKNOWN_NOT_NEGATIVE_CHILD_LEVEL_SOURCE_GAP"
    assert e98["local_child_activation_assigned"] is False
    assert e98["absence_of_local_report_is_negative"] is False
    assert e98["source_ids"]==[]

def test_mancora_fernandez_receiver_and_2023_event_are_bounded():
    p=load(MAN)
    f=p["hydrologic_components"]["quebrada_fernandez"]
    assert f["receiver_status"]=="PACIFIC_OCEAN_CONFIRMED"
    assert f["outlet_status"]=="SEA_RECEIVER_CONFIRMED_EXACT_MOUTH_GEOMETRY_PENDING"
    assert f["exact_outlet_coordinate"] is None
    assert f["map_publishable"] is False

    e=p["assets"]["event_ledger"]["2023_03_09_coer_cutoff"]
    assert e["natural_component"]=="quebrada_fernandez"
    assert e["natural_component_response"]=="ACTIVE_HIGH_FLOW_REPORTED"
    assert e["event_onset_time_local"] is None
    assert e["discharge_value_available"] is False
    assert e["operational_threshold_inferred"] is False
    assert e["transfer_to_la_capilla_vichayito_or_los_organos_forbidden"] is True


def test_mancora_ana_channel_control_point_is_not_promoted_to_outlet():
    p=load(MAN)
    pts=p["assets"]["geometry"]["official_channel_control_points"]
    assert len(pts)==1
    pt=pts[0]
    assert pt["crs"]=="WGS84_UTM_ZONE_17S"
    assert pt["easting_m"]==503489
    assert pt["northing_m"]==9538848
    assert pt["is_outlet"] is False
    assert pt["defines_channel_geometry"] is False
    assert pt["map_materialization_allowed"] is False

