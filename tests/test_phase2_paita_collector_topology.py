import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json"
SRC = ROOT / "site/data/phase2/sources/piura_paita_official_evidence_v0_1.json"
TOPO = ROOT / "config/phase2_paita_collector_topology_v0_1.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_paita_collector_topology_fails_closed():
    for obj in (load(SRC), load(TOPO)):
        assert obj["deployment_status"] == "RESEARCH_ONLY"
        assert obj["test_mode"] == "TEST_ONLY"
        assert obj["production_use"] is False
        assert obj["production_ready"] is False
        assert obj["operational_alerting_enabled"] is False
        assert obj["activation_gate"] == "BLOCKED"
        assert obj["decision_thresholds"] is None
        assert obj["hydraulic_factors"] is None

def test_supported_children_exist_and_remain_unmapped():
    pkg = load(PKG)
    topo = load(TOPO)
    mapping = {
        "Nueva Esperanza": "nueva_esperanza",
        "La Piscina": "la_piscina",
        "La Catarata": "la_catarata",
        "Villa Naval": "villa_naval",
    }
    for link in topo["links"]:
        if link["child"] in mapping:
            assert mapping[link["child"]] in pkg["hydrologic_components"]
            assert link["geometry_ready"] is False

def test_el_zanjon_collector_and_villa_naval_conflict():
    src = load(SRC)
    topo = load(TOPO)
    assert topo["collector"] == "El Zanjón"
    assert any(x["child"] == "El Zanjón" and x["receiver"] == "Pacific Ocean" for x in topo["links"])
    villa = next(x for x in topo["links"] if x["child"] == "Villa Naval")
    assert villa["receiver"] is None
    assert villa["status"] == "WITHHELD_OFFICIAL_SOURCE_CONFLICT"
    assert src["topology_adjudication"]["villa_naval"]["publish_collector_link"] is False
    assert src["qa"]["topology_conflict_preserved"] is True

def test_blind_basins_remain_separate():
    topo = load(TOPO)
    assert topo["separate_component"]["type"] == "URBAN_PLUVIAL_DEPRESSION_SYSTEM"
    assert topo["separate_component"]["merge_into_ravine_network"] is False
    assert topo["qa"]["map_ready"] is False
