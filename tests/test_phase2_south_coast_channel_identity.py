import json
from pathlib import Path

CFG = Path('config/phase2_south_coast_channel_identity_v0_1.json')

def load():
    return json.loads(CFG.read_text(encoding='utf-8'))

def test_safety_contract():
    c = load()
    assert c['deployment_status'] == 'RESEARCH_ONLY'
    assert c['test_mode'] == 'TEST_ONLY'
    assert c['production_use'] is False
    assert c['production_ready'] is False
    assert c['operational_alerting_enabled'] is False
    assert c['activation_gate'] == 'BLOCKED'
    assert c['missing_data_rule'] == 'UNKNOWN_NOT_LOW_RISK'
    assert c['decision_thresholds'] is None
    assert c['hydraulic_factors'] is None
    assert c['summary']['geometry_assets_published'] == 0
    assert c['summary']['new_operational_zones'] == 0

def test_channel_additions_are_fail_closed():
    c = load()
    rows = {x['child_id']: x for x in c['channel_identity_additions']}
    assert set(rows) == {'ica_huarangal_pisco','arequipa_estanquillo','arequipa_el_azufral'}
    assert rows['ica_huarangal_pisco']['expected_parent_uh_code'] == '13752'
    assert rows['arequipa_estanquillo']['official_course_code'] == '13254'
    for row in rows.values():
        assert row['geometry_asset'] is None
        assert row['outlet'] is None
        assert row['map_publishable'] is False
        assert row['event_state_transferred'] is False

def test_huarangal_homonym_guard():
    c = load()
    g = c['homonym_guards'][0]
    assert g['name'] == 'Quebrada Huarangal'
    pairs = {(x['child_id'], x['expected_parent_uh_code']) for x in g['units']}
    assert pairs == {('ica_huarangal_pisco','13752'),('arequipa_huarangal','132')}

def test_probes_and_sources():
    c = load()
    assert len(c['hydrography_probe_contracts']) == 3
    for p in c['hydrography_probe_contracts']:
        assert p['match_policy'] == 'EXACT_NAME_PLUS_PARENT_UH_REQUIRED_FOR_ACCEPTANCE'
        assert p['status'] == 'PLANNED_FAIL_CLOSED_NOT_EXECUTED'
        assert p['map_publishable'] is False
    for s in c['sources']:
        assert s['official'] is True
        assert s['content_sha256'] is None
        assert 'NOT_ARCHIVED' in s['provenance_status']

def test_base_inventory_dependency_is_explicit():
    c = load()
    d = c['base_inventory_dependency']
    assert d['pull_request'] == 308
    assert d['merge_order'] == 'MERGE_BASE_INVENTORY_BEFORE_THIS_OVERLAY'
