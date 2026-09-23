#!/usr/bin/env python3
"""Freeze exact source-named IGP channel-line features after bounded identity review.

Accepted outputs preserve every preregistered source feature independently. No source
segments are unioned and no endpoint is interpreted as an outlet/confluence. Source
features rejected during static spatial identity review are recorded but never emitted.
"""
from __future__ import annotations
import argparse, hashlib, json, tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'config/phase2_jicamarca_igp_channel_line_freeze_v0_1.json'
VALIDATION=ROOT/'site/data/validation/phase2_jicamarca_igp_channel_line_validation_v0_1.json'
SAFE={
    'deployment_status':'RESEARCH_ONLY','test_mode':'TEST_ONLY','production_use':False,
    'production_ready':False,'operational_alerting_enabled':False,'activation_gate':'BLOCKED',
    'missing_data_rule':'UNKNOWN_NOT_LOW_RISK','decision_thresholds':None,'hydraulic_factors':None,
}
class FreezeError(RuntimeError): pass

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'
def digest_bytes(b): return hashlib.sha256(b).hexdigest()
def digest_path(p): return digest_bytes(Path(p).read_bytes())
def guard(o,label):
    for k,v in SAFE.items():
        if o.get(k)!=v: raise FreezeError(f'UNSAFE_{label}_{k}')
def get_json(url,params):
    full=url+'?'+urlencode(params)
    req=Request(full,headers={'User-Agent':'IRFEN-RESEARCH-ONLY/0.1','Accept':'application/json'})
    with urlopen(req,timeout=90) as r: data=r.read(20_000_001)
    if len(data)>20_000_000: raise FreezeError('SOURCE_RESPONSE_TOO_LARGE')
    try: obj=json.loads(data.decode('utf-8'))
    except Exception as e: raise FreezeError(f'SOURCE_NOT_JSON {full}') from e
    if isinstance(obj,dict) and obj.get('error'): raise FreezeError(f"ARCGIS_ERROR {obj['error']}")
    return obj

def suffix_map(meta):
    out={}
    for f in meta.get('fields',[]):
        name=str(f.get('name') or ''); key=name.rsplit('.',1)[-1].casefold()
        if key and key not in out: out[key]=name
    oid=str(meta.get('objectIdField') or '')
    if oid: out['objectid']=oid
    return out

def arcgis_line_to_geojson(geom):
    paths=(geom or {}).get('paths') or []
    if not paths: raise FreezeError('EMPTY_SOURCE_LINE_GEOMETRY')
    for path in paths:
        if len(path)<2: raise FreezeError('SOURCE_LINE_TOO_SHORT')
        for xy in path:
            if not isinstance(xy,list) or len(xy)<2: raise FreezeError('INVALID_SOURCE_COORDINATE')
            x,y=float(xy[0]),float(xy[1])
            if not (-180<=x<=180 and -90<=y<=90): raise FreezeError(f'COORDINATE_OUTSIDE_WGS84 {x},{y}')
    return {'type':'LineString','coordinates':paths[0]} if len(paths)==1 else {'type':'MultiLineString','coordinates':paths}

def feature_props(component, expected, raw, fmap):
    return {
        'unit_id':f"jicamarca__{component['component_id']}__igp_{expected['objectid']}",
        'component_id':component['component_id'],
        'hydrologic_child_id':component['hydrologic_child_id'],
        'source_institution':'Instituto Geofisico del Peru','source_layer':'Quebrada_Lima',
        'source_objectid':expected['objectid'],'source_name':raw.get(fmap['nombre']),
        'source_district':raw.get(fmap['nomdist']),'source_province':raw.get(fmap['nomprov']),
        'source_department':raw.get(fmap['nomdep']),'source_type':raw.get(fmap['tipo']),
        'geometry_role':'OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY',
        'catchment_polygon':False,'outlet_or_confluence':False,'event_footprint':False,
        'routing_parameter':False,'activation_evidence':False,'risk_or_alert_layer':False,
        'deployment_status':'RESEARCH_ONLY','test_mode':'TEST_ONLY','production_use':False,
        'production_ready':False,'alerting_enabled':False,'operational_alerting_enabled':False,
        'activation_gate':'BLOCKED','missing_data_rule':'UNKNOWN_NOT_LOW_RISK',
        'decision_thresholds':None,'hydraulic_factors':None,
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=DEFAULT); a=ap.parse_args()
    cp=a.contract if a.contract.is_absolute() else ROOT/a.contract
    co=load(cp); guard(co,'CONTRACT'); src=co['source']; layer=src['layer_url']
    rejected=co.get('rejected_after_geometry_review') or []
    if not rejected or not all(x.get('status')=='REJECTED_WRONG_SAME_NAME_GEOGRAPHY_DO_NOT_PUBLISH' for x in rejected):
        raise FreezeError('REJECTION_LEDGER_MISSING_OR_UNSAFE')
    if any(x.get('event_outcome_used') is not False for x in rejected): raise FreezeError('REJECTION_USED_OUTCOME')
    accepted_ids={int(x['objectid']) for c in co['components'] for x in c['source_features']}
    rejected_ids={int(x['source_feature']['objectid']) for x in rejected}
    if accepted_ids & rejected_ids: raise FreezeError('REJECTED_SOURCE_ID_STILL_ACCEPTED')

    meta=get_json(layer,{'f':'json'})
    if meta.get('name')!=src['layer_name']: raise FreezeError(f"LAYER_NAME_DRIFT {meta.get('name')}")
    if meta.get('geometryType')!=src['geometry_type']: raise FreezeError(f"GEOMETRY_TYPE_DRIFT {meta.get('geometryType')}")
    sr=(meta.get('extent') or {}).get('spatialReference') or {}; wkid=sr.get('latestWkid') or sr.get('wkid')
    if int(wkid)!=int(src['spatial_reference_wkid']): raise FreezeError(f'SPATIAL_REFERENCE_DRIFT {wkid}')
    if meta.get('serviceItemId') not in (None,src['service_item_id']): raise FreezeError('SERVICE_ITEM_DRIFT')
    fmap=suffix_map(meta); required={'objectid','nombre','nomdist','nomprov','nomdep','tipo'}
    if not required.issubset(fmap): raise FreezeError(f'SCHEMA_DRIFT {sorted(required-set(fmap))}')

    generated=[]
    with tempfile.TemporaryDirectory(prefix='jicamarca_igp_lines_') as rawdir:
        td=Path(rawdir)
        for component in co['components']:
            if component.get('source_segments_must_remain_separate') is not True: raise FreezeError('SEGMENT_SEPARATION_GUARD_MISSING')
            features=[]
            for expected in component['source_features']:
                oid=int(expected['objectid'])
                obj=get_json(layer+'/query',{'objectIds':str(oid),'outFields':','.join(fmap[k] for k in sorted(required)),'returnGeometry':'true','outSR':'4326','f':'json'})
                rows=obj.get('features') or []
                if len(rows)!=1: raise FreezeError(f'OBJECTID_NOT_UNIQUE {oid} count={len(rows)}')
                row=rows[0]; attrs=row.get('attributes') or {}
                if int(attrs.get(fmap['objectid']))!=oid: raise FreezeError(f'OBJECTID_DRIFT {oid}')
                checks={'nombre':'name','nomdist':'district','nomprov':'province','nomdep':'department','tipo':'source_type'}
                for field,contract_key in checks.items():
                    if attrs.get(fmap[field])!=expected[contract_key]:
                        raise FreezeError(f"ATTRIBUTE_DRIFT oid={oid} {field}={attrs.get(fmap[field])!r} expected={expected[contract_key]!r}")
                features.append({'type':'Feature','properties':feature_props(component,expected,attrs,fmap),'geometry':arcgis_line_to_geojson(row.get('geometry'))})
            fc={'type':'FeatureCollection','properties':{
                'component_id':component['component_id'],'hydrologic_child_id':component['hydrologic_child_id'],
                'geometry_role':'OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY','source_segments_union_performed':False,
                'catchment_polygon':False,'outlet_or_confluence':False,'event_footprint':False,'routing_enabled':False,**SAFE,
            },'features':features}
            staged=td/Path(component['output_path']).name; staged.write_text(canonical(fc),encoding='utf-8')
            generated.append((component,staged,digest_path(staged),len(features)))
        for component,staged,sha,count in generated:
            out=ROOT/component['output_path']; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(staged.read_bytes())

    validation={
        'schema_version':'0.2','status':'PASS_FROZEN_IGP_NAMED_CHANNEL_LINES_WITH_REJECTION_LEDGER',**SAFE,
        'contract_path':cp.relative_to(ROOT).as_posix(),'contract_sha256':digest_path(cp),
        'source_layer':layer,'source_geometry_type':'esriGeometryPolyline','source_spatial_reference_wkid':4326,
        'initial_selection_used_geometry':False,'selection_used_outcomes':False,'source_segments_union_performed':False,
        'post_geometry_identity_rejection_performed':True,'catchment_polygons_created':False,
        'outlets_or_confluences_inferred':False,'routing_enabled':False,
        'components':[{'component_id':c['component_id'],'hydrologic_child_id':c['hydrologic_child_id'],'path':c['output_path'],
             'sha256':sha,'feature_count':count,'source_objectids':[x['objectid'] for x in c['source_features']],
             'catchment_geometry_resolved':False,'outlet_resolved':False} for c,_,sha,count in generated],
        'rejected_components':[{'component_id':x['component_id'],'hydrologic_child_id':x['hydrologic_child_id'],
            'source_objectid':x['source_feature']['objectid'],'status':x['status'],'geometry_published':False,
            'outlet_inferred':False,'catchment_inferred':False,'event_outcome_used':False} for x in rejected],
        'withheld_components':[x['component_id'] for x in co['withheld_from_geometry_publication']],
    }
    VALIDATION.parent.mkdir(parents=True,exist_ok=True); VALIDATION.write_text(canonical(validation),encoding='utf-8')
    print(json.dumps({'status':validation['status'],'components':{x['component_id']:x['sha256'] for x in validation['components']},'rejected':validation['rejected_components']},sort_keys=True))

if __name__=='__main__': main()
