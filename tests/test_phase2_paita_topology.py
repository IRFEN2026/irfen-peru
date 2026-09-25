import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/piura_paita_igp_source_v0_1.json"
TOPOLOGY = ROOT / "site/data/phase2/sources/piura_paita_topology_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_paita_igp_source_is_frozen():
    s = load(SOURCE)
    assert s["source_id"] == "IGP-PAITA-GEODYNAMICS-2021"
    assert s["institution"] == "Instituto Geofisico del Peru"
    assert s["publication_date"] == "2021-11"
    assert s["evidence_pages"] == [8, 9, 17, 20]


def test_paita_child_to_collector_topology_is_explicit():
    t = load(TOPOLOGY)
    assert t["discovery_id"] == "piura_paita_urban_local_ravines"
    assert t["principal_channel"] == "Quebrada El Zanjon"
    assert t["secondary_channels"] == [
        "Quebrada Nueva Esperanza",
        "Quebrada La Piscina",
        "Quebrada Catarata",
        "Quebrada Villa Naval",
    ]
    assert t["receiver"] == "Pacific Ocean"


def test_paita_topology_does_not_publish_unresolved_geometry():
    t = load(TOPOLOGY)
    assert t["exact_geometry_available"] is False
    assert t["exact_outlet_coordinate_available"] is False
    assert t["map_materialization_allowed"] is False
