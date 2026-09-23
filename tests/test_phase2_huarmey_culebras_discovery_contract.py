import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'site/data/validation/phase2_discovery_contracts/ancash_huarmey_culebras.json'
SAFE={
 'deployment_status':'RESEARCH_ONLY','test_mode':'TEST_ONLY','production_use':False,'production_ready':False,
 'operational_alerting_enabled':False,'activation_gate':'BLOCKED','missing_data_rule':'UNKNOWN_NOT_LOW_RISK',
 'decision_thresholds':None,'hydraulic_factors':None,
}

def test_huarmey_culebras_parent_is_non_geometric_grouper_and_children_are_separate():
    c=json.loads(CONTRACT.read_text())
    for k,v in SAFE.items(): assert c[k]==v
    p=c['component_policy']
    assert p['parent_is_hydrologic_basin'] is False
    assert p['parent_is_map_polygon'] is False
    assert p['components_must_remain_separate'] is True
    assert p['composite_union_forbidden'] is True
    assert c['assets']['geometry']['path'] is None
    assert c['assets']['geometry']['status']=='MISSING_NO_REPRODUCIBLE_GEOMETRY'
    comps={x['component_id']:x for x in c['assets']['geometry_components']}
    assert set(comps)=={'huarmey','culebras'}
    assert comps['huarmey']['hydrologic_identity']=={'ana_unit_code':'137594','ana_unit_name':'Cuenca Huarmey'}
    assert comps['culebras']['hydrologic_identity']=={'ana_unit_code':'1375952','ana_unit_name':'Cuenca Culebras'}
    assert comps['huarmey']['geometry']['path'] != comps['culebras']['geometry']['path']
    for x in comps.values():
        code=x['hydrologic_identity']['ana_unit_code']
        assert x['source_query']['where']==f"CODIGO='{code}'"
        assert x['geometry']['counts_as_operational_geometry'] is False
        assert x['geometry']['counts_as_event_footprint'] is False

def test_frozen_component_files_remain_guarded_when_present():
    c=json.loads(CONTRACT.read_text())
    for x in c['assets']['geometry_components']:
        path=ROOT/x['geometry']['path']
        if not path.exists():
            continue
        doc=json.loads(path.read_text())
        assert len(doc['features'])==1
        f=doc['features'][0]
        assert f['properties']['parent_discovery_id']=='ancash_huarmey_culebras'
        assert f['properties']['component_id']==x['component_id']
        assert f['properties']['deployment_status']=='RESEARCH_ONLY'
        assert f['properties']['production_use'] is False
        assert f['properties']['production_ready'] is False
        assert f['properties']['operational_alerting_enabled'] is False
        assert f['properties']['activation_gate']=='BLOCKED'
        assert f['properties']['decision_thresholds'] is None
        assert f['properties']['hydraulic_factors'] is None
        assert f['properties']['counts_as_event_footprint'] is False
        assert f['properties']['counts_as_operational_geometry'] is False
