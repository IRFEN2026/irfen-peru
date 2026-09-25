import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INV=ROOT/"config/phase2_north_coast_discovery_inventory_v0_1.json"
PKG=ROOT/"site/data/validation/phase2_discovery_packages/piura_colan_bajo_chira_local_ravines.json"
SRC=ROOT/"site/data/phase2/sources/piura_colan_official_evidence_v0_1.json"

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


def test_nine_de_diciembre_is_retained_and_paired_labels_fail_closed():
    p=load(PKG)
    ravines=p["hydrologic_components"]["local_ravines"]
    assert "9 de Diciembre" in ravines["named"]
    reviews=ravines["identity_adjudication"]
    for key in ("9_de_diciembre_salaverry","libertad_centenario","bolognesi_grau"):
        assert reviews[key]["merge_status"]=="DO_NOT_MERGE_PENDING_REPRODUCIBLE_GEOMETRY_AND_NAMING_CROSSWALK"
    assert p["map_policy"]["paired_label_merge_without_crosswalk_forbidden"] is True


def test_colan_source_registry_is_explicit_and_fail_closed():
    p=load(PKG)
    s=load(SRC)
    assert p["source_registry_path"]=="site/data/phase2/sources/piura_colan_official_evidence_v0_1.json"
    ids={x["source_id"] for x in s["sources"]}
    assert "ANA-SIGRID-COLAN-9-DICIEMBRE-2015" in ids
    nine=next(x for x in s["sources"] if x["source_id"]=="ANA-SIGRID-COLAN-9-DICIEMBRE-2015")
    assert any("same hydrologic child" in x for x in nine["forbidden_inferences"])
    assert s["qa"]["paired_source_labels_auto_merged"] is False
    assert s["qa"]["evacuation_map_used_as_event"] is False
    assert s["qa"]["evacuation_ambit_used_as_catchment_geometry"] is False
