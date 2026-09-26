import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'site/data/validation/phase2_discovery_packages/piura_paita_urban_local_ravines.json'
SRC=ROOT/'site/data/phase2/sources/piura_paita_official_evidence_v0_1.json'

def load(p): return json.loads(p.read_text(encoding='utf-8'))

def test_paita_documentary_topology_is_fail_closed():
    p=load(PKG); s=load(SRC)
    for x in (p,s):
        assert x['deployment_status']=='RESEARCH_ONLY'
        assert x['test_mode']=='TEST_ONLY'
        assert x['production_use'] is False
        assert x['production_ready'] is False
        assert x['operational_alerting_enabled'] is False
        assert x['activation_gate']=='BLOCKED'
        assert x['decision_thresholds'] is None
        assert x['hydraulic_factors'] is None
    t=p['documentary_topology']
    assert t['current_outlet_coordinates_available'] is False
    assert t['travel_time_available'] is False
    assert t['hydraulic_capacity_available'] is False
    r=t['relationships']
    assert r['la_catarata']['documentary_receiver']=='El Zanjón'
    assert r['villa_naval']['role']=='LOCAL_RAVINE_WITH_SEPARATE_COASTAL_OUTFALL'
    assert r['paita_alta_blind_basins']['documentary_receiver']=='NONE_ASSIGNED'

def test_paita_historical_routing_not_promoted():
    p=load(PKG); r=p['documentary_topology']['relationships']
    assert r['nueva_esperanza']['historical_receiver']=='El Zanjón'
    assert r['la_piscina']['historical_receiver_chain']==['Nueva Esperanza','El Zanjón']
    assert r['la_piscina']['current_receiver']=='UNRESOLVED'
    assert p['qa']['documentary_topology_is_not_geometry'] is True
    assert p['qa']['historical_topology_is_not_assumed_current'] is True

def test_paita_sources_have_claim_bounds():
    s=load(SRC)
    ids={x['source_id'] for x in s['sources']}
    assert {'IGP-PAITA-GEODYNAMICS-2021','PPRRD-PAITA-2019-2021','INDECI-PAITA-MAP-2000','SENAMHI-PAITA-INTERCUENCAL-CONTEXT'}.issubset(ids)
    for x in s['sources']:
        assert x['admissible_claims'] and x['forbidden_inferences']
    assert s['topology_policy']['documentary_topology_is_not_outlet_coordinate'] is True
    assert s['topology_policy']['historical_topology_is_not_assumed_current'] is True
