import json
from pathlib import Path

CFG=Path('config/phase2_arequipa_official_ravine_identities_v0_1.json')

def load():
    return json.loads(CFG.read_text(encoding='utf-8'))

def test_fail_closed():
    c=load()
    assert c['deployment_status']=='RESEARCH_ONLY'
    assert c['test_mode']=='TEST_ONLY'
    assert c['production_use'] is False
    assert c['production_ready'] is False
    assert c['operational_alerting_enabled'] is False
    assert c['activation_gate']=='BLOCKED'
    assert c['missing_data_rule']=='UNKNOWN_NOT_LOW_RISK'
    assert c['decision_thresholds'] is None
    assert c['hydraulic_factors'] is None
    assert c['summary']['geometry_assets_published']==0
    assert c['summary']['new_operational_zones']==0

def test_identified_channels_stay_unmapped():
    c=load()
    rows={x['child_id']:x for x in c['channel_identity_additions']}
    assert set(rows)=={'arequipa_la_huaylla','arequipa_pichu_pichu','arequipa_churumayo','arequipa_rio_chalca_de_mina','arequipa_santo_domingo_lluta'}
    assert all(x['geometry_asset'] is None for x in rows.values())
    assert all(x['map_publishable'] is False for x in rows.values())
    assert rows['arequipa_rio_chalca_de_mina']['parent_basin_id']=='arequipa_camana_majes_colca'
    assert rows['arequipa_la_huaylla']['parent_basin_id'] is None
