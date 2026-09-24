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
