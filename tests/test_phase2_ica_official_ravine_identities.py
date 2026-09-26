import json
from pathlib import Path

CFG=Path("config/phase2_ica_official_ravine_identities_v0_1.json")

def load():
    return json.loads(CFG.read_text(encoding="utf-8"))

def test_fail_closed():
    c=load()
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    assert c["summary"]["geometry_assets_published"]==0
    assert c["summary"]["new_operational_zones"]==0

def test_new_identities_stay_unmapped_and_parent_is_not_promoted():
    c=load()
    rows={x["child_id"]:x for x in c["channel_identity_additions"]}
    assert set(rows)=={"ica_la_ayapana","ica_el_molino_ingenio","ica_cabeza_de_cura","ica_cerro_blanco_nasca"}
    assert all(x["geometry_asset"] is None for x in rows.values())
    assert all(x["map_publishable"] is False for x in rows.values())
    assert all(x["parent_assignment_status"]=="PENDING_INDEPENDENT_HYDROGRAPHIC_MATCH" for x in rows.values())

def test_cansas_parent_is_confirmed_but_geometry_stays_blocked():
    c=load()
    row=c["parent_assignment_reinforcements"][0]
    assert row["child_id"]=="ica_cansas"
    assert row["parent_basin_id"]=="ica_ica"
    assert row["status"]=="OFFICIAL_ANA_2026_HYDROGRAPHIC_LOCATION_CONFIRMED"
    assert row["geometry_freeze"] is False
    assert c["rules"]["coordinate_anomaly_blocks_geometry_freeze"] is True
