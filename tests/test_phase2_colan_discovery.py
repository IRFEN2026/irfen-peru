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
    local=[v for k,v in p["hydrologic_components"].items() if k.startswith("quebrada_")]
    assert local
    assert all(v["activation_status"]=="UNKNOWN_NOT_NEGATIVE" for v in local)


def test_colan_named_ravines_are_independent_fail_closed_children():
    p=load(PKG)
    expected={
        "quebrada_centenario","quebrada_libertad","quebrada_arroyo_mio",
        "quebrada_9_de_diciembre","quebrada_salaverry","quebrada_cahuide",
        "quebrada_atahualpa","quebrada_bolognesi","quebrada_grau","quebrada_sucre",
    }
    assert expected.issubset(p["hydrologic_components"])
    for key in expected:
        child=p["hydrologic_components"][key]
        assert child["geometry_status"].startswith("MISSING_")
        assert child["outlet_status"]=="UNRESOLVED"
        assert child["activation_status"]=="UNKNOWN_NOT_NEGATIVE"
        assert child["map_materialization_allowed"] is False

def test_colan_bolognesi_grau_identity_remains_unmerged():
    p=load(PKG)
    b=p["hydrologic_components"]["quebrada_bolognesi"]
    g=p["hydrologic_components"]["quebrada_grau"]
    assert "UNRESOLVED" in b["identity_status"]
    assert "UNRESOLVED" in g["identity_status"]
    assert p["qa"]["bolognesi_grau_merge_forbidden_until_identity_resolved"] is True

def test_colan_collector_coupling_is_blocked_without_outlets():
    p=load(PKG)
    cc=p["collector_coupling"]
    assert cc["status"].startswith("BLOCKED_")
    assert cc["local_ravine_to_lower_chira_assignment_allowed"] is False
    assert cc["local_ravine_to_pacific_assignment_allowed"] is False
    assert cc["travel_time_allowed"] is False
    assert cc["attenuation_allowed"] is False
