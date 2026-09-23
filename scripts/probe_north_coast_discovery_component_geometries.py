#!/usr/bin/env python3
"""Freeze separate official ANA geometries for a multi-component discovery grouper.

The parent discovery unit is never converted into a synthetic basin. Each component is
queried by exact official ANA hydrographic-unit code/name and normalized independently.
The script reads no event outcomes, rainfall, hydraulic capacity, thresholds or controls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
SOURCE_ROOT=ROOT/'site/data/phase2/sources/north_coast_discovery_geometry'
SAFE={
    'deployment_status':'RESEARCH_ONLY','test_mode':'TEST_ONLY','production_use':False,
    'production_ready':False,'operational_alerting_enabled':False,'activation_gate':'BLOCKED',
    'missing_data_rule':'UNKNOWN_NOT_LOW_RISK','decision_thresholds':None,'hydraulic_factors':None,
}
ENDPOINT='https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query'

class ProbeError(RuntimeError): pass

def canonical_bytes(v):
    return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()

def dump(path:Path,v):
    path.parent.mkdir(parents=True,exist_ok=True); raw=canonical_bytes(v); path.write_bytes(raw); return sha256(raw).hexdigest()

def load(path:Path): return json.loads(path.read_text(encoding='utf-8'))

def fetch(query):
    params={'where':query['where'],'outFields':query.get('out_fields','*'),'returnGeometry':'true',
            'outSR':str(query.get('out_sr',4326)),'geometryPrecision':str(query.get('geometry_precision',7)),
            'f':query.get('format','geojson')}
    url=query['endpoint']+'?'+urlencode(params)
    with urlopen(Request(url,headers={'User-Agent':'IRFEN-RESEARCH-ONLY/0.1'}),timeout=90) as r:
        return json.loads(r.read().decode()),url

def validate_parent(c):
    for k,v in SAFE.items():
        if c.get(k)!=v: raise ProbeError(f'UNSAFE_PARENT_{k}')
    p=c.get('component_policy') or {}
    required={'parent_is_hydrologic_basin':False,'parent_is_map_polygon':False,'components_must_remain_separate':True,
              'composite_union_forbidden':True,'territorial_reference_is_basin':False}
    for k,v in required.items():
        if p.get(k)!=v: raise ProbeError(f'UNSAFE_COMPONENT_POLICY_{k}')
    g=((c.get('assets') or {}).get('geometry') or {})
    if g.get('path') is not None or not str(g.get('status','')).startswith('MISSING_PARENT_GROUPER'):
        raise ProbeError('PARENT_SYNTHETIC_GEOMETRY_FORBIDDEN')

def validate_component(comp):
    cid=comp.get('component_id'); ident=comp.get('hydrologic_identity') or {}; q=comp.get('source_query') or {}
    code=str(ident.get('ana_unit_code') or ''); name=ident.get('ana_unit_name')
    if not cid or not code or not name: raise ProbeError('INCOMPLETE_COMPONENT_IDENTITY')
    if q.get('endpoint')!=ENDPOINT or q.get('where')!=f"CODIGO='{code}'": raise ProbeError(f'UNSAFE_QUERY_{cid}')
    geom=comp.get('geometry') or {}
    if geom.get('counts_as_operational_geometry') is not False or geom.get('counts_as_event_footprint') is not False:
        raise ProbeError(f'UNSAFE_GEOMETRY_ROLE_{cid}')
    return cid,code,name

def validate_source(src,code,name):
    fs=src.get('features') or []
    if src.get('type')!='FeatureCollection' or len(fs)!=1: raise ProbeError(f'ANA_EXACT_CODE_NOT_UNIQUE_{code}_{len(fs)}')
    f=fs[0]; p=f.get('properties') or {}; got_code=str(p.get('CODIGO') or p.get('codigo') or '')
    got_name=p.get('NOMBRE') or p.get('nombre'); g=f.get('geometry') or {}
    if got_code!=code or got_name!=name: raise ProbeError(f'ANA_IDENTITY_MISMATCH_{code}_{got_code}_{got_name}')
    if g.get('type') not in {'Polygon','MultiPolygon'} or not g.get('coordinates'): raise ProbeError(f'ANA_GEOMETRY_INVALID_{code}')
    return f

def normalized(parent_id,cid,feature,code,name,source_id):
    props={
      'unit_id':f'{parent_id}__{cid}','parent_discovery_id':parent_id,'component_id':cid,'name':name,
      'official_unit_code':code,'source_id':source_id,'representation':'OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT',
      'context_only':True,'counts_as_event_footprint':False,'counts_as_operational_geometry':False,
      'deployment_status':'RESEARCH_ONLY','test_mode':'TEST_ONLY','production_use':False,'production_ready':False,
      'operational_alerting_enabled':False,'alerting_enabled':False,'activation_gate':'BLOCKED',
      'missing_data_rule':'UNKNOWN_NOT_LOW_RISK','decision_thresholds':None,'hydraulic_factors':None}
    return {'type':'FeatureCollection','properties':{
      'deployment_status':'RESEARCH_ONLY','production_use':False,'production_ready':False,
      'operational_alerting_enabled':False,'context_only':True,'parent_discovery_id':parent_id,'source_id':source_id},
      'features':[{'type':'Feature','properties':props,'geometry':feature['geometry']}]}

def source_path(parent_id,cid,code): return SOURCE_ROOT/f'ana_{parent_id}_{cid}_{code}.geojson'
def validation_path(geom_path:Path): return geom_path.with_name(geom_path.stem+'_validation.json')

def run(contract_path:Path,refresh:bool):
    c=load(contract_path); validate_parent(c); parent_id=c.get('discovery_id'); comps=((c.get('assets') or {}).get('geometry_components') or [])
    if len(comps)<2: raise ProbeError('MULTI_COMPONENT_CONTRACT_REQUIRES_AT_LEAST_TWO_COMPONENTS')
    ids=[]; results=[]
    for comp in comps:
        cid,code,name=validate_component(comp)
        if cid in ids: raise ProbeError(f'DUPLICATE_COMPONENT_{cid}')
        ids.append(cid); sp=source_path(parent_id,cid,code); gp=ROOT/comp['geometry']['path']; vp=validation_path(gp)
        if refresh:
            src,url=fetch(comp['source_query']); source_sha=dump(sp,src)
        else:
            if not sp.is_file(): raise ProbeError(f'FROZEN_SOURCE_MISSING_{cid}')
            src=load(sp); source_sha=sha256(sp.read_bytes()).hexdigest(); url=None
        feature=validate_source(src,code,name); norm=normalized(parent_id,cid,feature,code,name,comp['source_id']); geometry_sha=dump(gp,norm)
        val={
          'schema_version':'0.1','parent_discovery_id':parent_id,'component_id':cid,
          'status':'PASS_OFFICIAL_ANA_DISCOVERY_COMPONENT_GEOMETRY',**SAFE,
          'source_id':comp['source_id'],'ana_unit_code':code,'ana_unit_name':name,
          'source_path':sp.relative_to(ROOT).as_posix(),'source_sha256':source_sha,
          'geometry_path':gp.relative_to(ROOT).as_posix(),'geometry_sha256':geometry_sha,
          'request_url':url,'fetched_at_utc':datetime.now(timezone.utc).isoformat() if refresh else None,
          'outcomes_read':False,'rainfall_read':False,'hydraulic_capacity_read':False,'thresholds_used':False,
          'negative_controls_read':False,'approximate_geometry_used':False,'composite_geometry_created':False}
        validation_sha=dump(vp,val); ga=comp['geometry']; ga['status']='PARTIAL_OFFICIAL_BASIN_CONTEXT'; ga['sha256']=geometry_sha
        ga['validation_path']=vp.relative_to(ROOT).as_posix(); ga['validation_sha256']=validation_sha
        results.append(val)
    c['contract_status']='DISCOVERY_CHILD_GEOMETRIES_REPRODUCIBLE_CONTEXT_ONLY'; dump(contract_path,c)
    return results

def main():
    p=argparse.ArgumentParser(); p.add_argument('--contract',type=Path,required=True); p.add_argument('--refresh-source',action='store_true'); a=p.parse_args()
    out=run(a.contract,a.refresh_source); print(json.dumps({'status':'PASS','components':[x['component_id'] for x in out]},sort_keys=True))
if __name__=='__main__': main()
