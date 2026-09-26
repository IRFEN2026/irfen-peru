import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INV=ROOT/"config/phase2_north_coast_discovery_inventory_v0_1.json"
PKG=ROOT/"site/data/validation/phase2_discovery_packages/piura_colan_bajo_chira_local_ravines.json"

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

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_colan_registered_as_territorial_compound_system():
    inv=load(INV)
    u=next(x for x in inv["discovery_units"] if x["discovery_id"]=="piura_colan_bajo_chira_local_ravines")
    assert "TERRITORIAL_GROUPER" in u["entity_role"]
    assert "Rio Chira lower reach / left-bank Colán exposure" in u["hydrologic_components"]
    assert "Quebrada Cahuide" in u["hydrologic_components"]

def test_package_fails_closed_and_forbids_synthetic_colan_basin():
    p=load(PKG)
    for k,v in SAFE.items():
        assert p[k]==v
    assert p["territorial_identity"]["territorial_reference_is_basin"] is False
    assert p["territorial_identity"]["synthetic_colan_basin_allowed"] is False
    assert p["assets"]["geometry"]["path"] is None
    assert p["map_policy"]["parent_polygon_forbidden"] is True

def test_river_ravine_and_marine_mechanisms_are_separate():
    p=load(PKG)
    m=p["mechanism_policy"]
    assert m["lower_chira_river_flood_separate"] is True
    assert m["local_ravines_separate_by_child"] is True
    assert m["marine_oleaje_tsunami_separate_nonhydrologic"] is True
    assert m["dike_breach_is_not_natural_channel_capacity"] is True

def test_vulnerability_inventory_is_not_promoted_to_event_truth():
    p=load(PKG)
    assert p["vulnerability_evidence"]["named_ravines_officially_identified"] is True
    assert "not an event ledger" in p["vulnerability_evidence"]["warning"]
    assert p["hydrologic_components"]["local_ravines"]["event_attribution_rule"]=="VULNERABILITY_INVENTORY_DOES_NOT_EQUAL_CONFIRMED_ACTIVATION_EVENT"


def test_ana_2016_colan_identity_refinement():
    p=load(PKG)
    names=p["hydrologic_components"]["local_ravines"]["named"]
    assert "9 de Diciembre" in names
    assert "Bolognesi" in names and "Grau" in names
    assert p["vulnerability_evidence"]["official_named_ravine_count"]==10
    assert p["vulnerability_evidence"]["identity_resolution"]["source_points_are_channel_or_outlet_geometry"] is False
