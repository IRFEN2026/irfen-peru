import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json'

def test_paita_topology_contract():
    p=json.loads(PKG.read_text(encoding='utf-8'))
    assert p['schema_version']=='0.2'
    assert p['collector_coupling']['main_local_collector']=='el_zanjon'
    assert p['hydrologic_components']['villa_naval']['routing_status']=='SOURCE_DISAGREEMENT_PRESERVED'
    assert p['map_policy']['child_only_after_reproducible_geometry'] is True
