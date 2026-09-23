#!/usr/bin/env python3
"""Bounded attribute-only probe of the official IGP Quebrada_Lima layer.

This script intentionally does not request geometry. A name match is evidence for
source identity review only and cannot become a basin, outlet, confluence or route.
"""
from __future__ import annotations
import argparse, json, unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'config/phase2_jicamarca_igp_hydrography_probe_v0_1.json'
SAFE={
    'deployment_status':'RESEARCH_ONLY','test_mode':'TEST_ONLY','production_use':False,
    'production_ready':False,'operational_alerting_enabled':False,'activation_gate':'BLOCKED',
    'missing_data_rule':'UNKNOWN_NOT_LOW_RISK','decision_thresholds':None,'hydraulic_factors':None,
}
class ProbeError(RuntimeError): pass

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
def guard(o,label):
    for k,v in SAFE.items():
        if o.get(k)!=v: raise ProbeError(f'UNSAFE_{label}_{k}')
def norm(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode('ascii')
    return ' '.join(s.casefold().split())
def get_json(url,params):
    full=url+'?'+urlencode(params)
    req=Request(full,headers={'User-Agent':'IRFEN-RESEARCH-ONLY/0.1','Accept':'application/json'})
    with urlopen(req,timeout=90) as r:
        data=r.read(20_000_001)
    if len(data)>20_000_000: raise ProbeError('SOURCE_RESPONSE_TOO_LARGE')
    try: obj=json.loads(data.decode('utf-8'))
    except Exception as e: raise ProbeError(f'SOURCE_NOT_JSON {full}') from e
    if isinstance(obj,dict) and obj.get('error'): raise ProbeError(f"ARCGIS_ERROR {obj['error']}")
    return obj

def field_map(meta):
    out={}
    for field in meta.get('fields',[]):
        name=str(field.get('name') or '')
        suffix=name.rsplit('.',1)[-1].casefold()
        if suffix and suffix not in out: out[suffix]=name
    oid=str(meta.get('objectIdField') or '')
    if oid: out['objectid']=oid
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=DEFAULT); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args()
    cp=a.contract if a.contract.is_absolute() else ROOT/a.contract
    co=load(cp); guard(co,'CONTRACT')
    src=co['source']; layer_url=f"{src['service_url']}/{int(src['layer_id'])}"
    meta=get_json(layer_url,{'f':'json'})
    if meta.get('name')!=src['expected_layer_name']: raise ProbeError(f"LAYER_NAME_DRIFT {meta.get('name')}")
    if meta.get('geometryType')!=src['expected_geometry_type']: raise ProbeError(f"GEOMETRY_TYPE_DRIFT {meta.get('geometryType')}")
    sr=(meta.get('extent') or {}).get('spatialReference') or {}
    wkid=sr.get('latestWkid') or sr.get('wkid')
    if int(wkid)!=int(src['expected_spatial_reference_wkid']): raise ProbeError(f'SPATIAL_REFERENCE_DRIFT {wkid}')
    if meta.get('serviceItemId') not in (None,src['service_item_id']): raise ProbeError(f"SERVICE_ITEM_DRIFT {meta.get('serviceItemId')}")
    fmap=field_map(meta)
    required={str(x).casefold() for x in src['observed_required_fields']}
    missing=sorted(required-set(fmap))
    if missing: raise ProbeError(f"SCHEMA_DRIFT missing={missing} available={sorted(fmap)}")
    actual_fields=[fmap[x] for x in sorted(required)]
    query_url=layer_url+'/query'
    ids=get_json(query_url,{'where':'1=1','returnIdsOnly':'true','f':'json'}).get('objectIds') or []
    ids=sorted({int(x) for x in ids})
    if not ids: raise ProbeError('NO_OBJECT_IDS')
    if len(ids)>int(co['limits']['max_object_ids']): raise ProbeError(f'TOO_MANY_OBJECT_IDS {len(ids)}')
    chunk=int(co['limits']['query_chunk_size']); attrs=[]
    semantic={
        'objectid':'objectid','nombre':'name','nomdep':'department','nomprov':'province',
        'nomdist':'district','clasificac':'classification','tipo':'source_type','ubigeo':'ubigeo'}
    for i in range(0,len(ids),chunk):
        subset=ids[i:i+chunk]
        obj=get_json(query_url,{
            'objectIds':','.join(map(str,subset)),
            'outFields':','.join(actual_fields),
            'returnGeometry':'false','f':'json'})
        for feature in obj.get('features',[]):
            raw=feature.get('attributes') or {}
            row={semantic[k]:raw.get(fmap[k]) for k in semantic}
            attrs.append(row)
    if len(attrs)!=len(ids): raise ProbeError(f'ATTRIBUTE_COUNT_MISMATCH ids={len(ids)} features={len(attrs)}')
    target_results=[]
    for target in co['targets']:
        aliases={norm(x) for x in target['accepted_name_aliases']}
        exact=[]; contains=[]
        for row in attrs:
            n=norm(row.get('name'))
            if n in aliases: exact.append(row)
            elif n and any(a in n or n in a for a in aliases): contains.append(row)
        key=lambda r:(str(r.get('name') or ''),int(r.get('objectid') or 0))
        exact.sort(key=key); contains.sort(key=key)
        target_results.append({
            'child_id':target['child_id'],'accepted_name_aliases':target['accepted_name_aliases'],
            'exact_match_count':len(exact),'exact_matches':exact,
            'contains_match_count':len(contains),'contains_matches':contains,
            'geometry_accepted':False,'outlet_accepted':False,'routing_enabled':False,
        })
    report={
        'schema_version':'0.2','status':'PASS_BOUNDED_IGP_HYDROGRAPHY_ATTRIBUTE_PROBE',**SAFE,
        'source':{'institution':src['institution'],'layer_url':layer_url,'layer_name':meta.get('name'),
                  'geometry_type':meta.get('geometryType'),'spatial_reference_wkid':int(wkid),
                  'service_item_id':meta.get('serviceItemId') or src['service_item_id'],
                  'resolved_field_names':{k:fmap[k] for k in sorted(required)}},
        'object_id_count':len(ids),'attribute_feature_count':len(attrs),'geometry_requested':False,
        'geometry_accepted':False,'outlets_inferred':False,'confluences_inferred':False,
        'routing_enabled':False,'targets':target_results,
        'interpretation_rule':'Name matches are candidate source-identity evidence only. Geometry/outlet acceptance requires a separate frozen review and reproducible geometry retrieval.',
    }
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(canonical(report),encoding='utf-8')
    print(json.dumps({'status':report['status'],'object_id_count':len(ids),'matches':{x['child_id']:x['exact_match_count'] for x in target_results}},ensure_ascii=False,sort_keys=True))

if __name__=='__main__': main()
