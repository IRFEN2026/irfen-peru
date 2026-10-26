#!/usr/bin/env python3
"""Discover schema metadata from exact pre-frozen official service roots only.

No candidate/event records are queried. Raw response bodies are hashed in-memory and never
written or printed. Output is schema-only and cannot contain feature values, narrative text,
target identifiers, outcomes, A6680, or contaminated material.
"""
from __future__ import annotations
import argparse, hashlib, json, re, urllib.parse, urllib.request
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
SAFE_FIELD=re.compile(r'^[A-Za-z0-9_]{1,96}$')
DATE_HINT=re.compile(r'(date|fecha|time|hora|year|anio|año)',re.I)

def sha_bytes(b: bytes)->str: return hashlib.sha256(b).hexdigest()
def get_bytes(url: str, timeout: int=30):
    req=urllib.request.Request(url,headers={'User-Agent':'IRFEN-research-cleanroom/0.1','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        final=r.geturl()
        if urllib.parse.urlparse(final).netloc != urllib.parse.urlparse(url).netloc:
            raise RuntimeError(f'CROSS_HOST_REDIRECT {url} -> {final}')
        body=r.read(8_000_000+1)
        if len(body)>8_000_000: raise RuntimeError('METADATA_RESPONSE_TOO_LARGE')
        return int(r.status),r.headers.get('Content-Type',''),final,body

def arcgis_metadata(root: str):
    service_url=root.rstrip('/')+'?f=pjson'
    status,ctype,final,body=get_bytes(service_url)
    if status!=200: raise RuntimeError(f'HTTP_{status}')
    obj=json.loads(body.decode('utf-8'))
    layer_ids=[]
    for item in obj.get('layers',[]):
        if isinstance(item,dict) and isinstance(item.get('id'),int): layer_ids.append(item['id'])
    layer_ids=sorted(set(layer_ids))
    layers=[]
    for lid in layer_ids:
        u=root.rstrip('/')+f'/{lid}?f=pjson'
        st,ct,fin,b=get_bytes(u)
        if st!=200: raise RuntimeError(f'LAYER_METADATA_HTTP_{st}_{lid}')
        d=json.loads(b.decode('utf-8'))
        fields=[]
        for f in d.get('fields',[]):
            name=f.get('name'); typ=f.get('type')
            if isinstance(name,str) and SAFE_FIELD.fullmatch(name) and isinstance(typ,str):
                fields.append({'name':name,'type':typ,'temporal_hint':bool(DATE_HINT.search(name))})
        fields.sort(key=lambda x:(x['name'],x['type']))
        layers.append({
            'layer_id':lid,
            'metadata_sha256':sha_bytes(b),
            'geometry_type':d.get('geometryType') if isinstance(d.get('geometryType'),str) else None,
            'supports_query':bool(d.get('capabilities') and 'Query' in str(d.get('capabilities'))),
            'max_record_count':d.get('maxRecordCount') if isinstance(d.get('maxRecordCount'),int) else None,
            'fields':fields
        })
    return {
        'source_status':'METADATA_DISCOVERED',
        'service_metadata_url':service_url,
        'service_metadata_sha256':sha_bytes(body),
        'service_content_type':ctype,
        'layer_count':len(layers),
        'layers':layers,
        'feature_records_read':False
    }

def portal_probe(root: str):
    # HEAD-only reachability probe. No portal/document body is read at this stage.
    req=urllib.request.Request(root,method='HEAD',headers={'User-Agent':'IRFEN-research-cleanroom/0.1'})
    with urllib.request.urlopen(req,timeout=30) as r:
        final=r.geturl()
        if urllib.parse.urlparse(final).netloc != urllib.parse.urlparse(root).netloc:
            raise RuntimeError(f'CROSS_HOST_REDIRECT {root} -> {final}')
        return {
            'source_status':'HEAD_REACHABLE_EXACT_METADATA_ENDPOINT_UNRESOLVED',
            'http_status':int(r.status),
            'content_type':r.headers.get('Content-Type',''),
            'document_or_feature_bytes_read':False
        }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--allowlist',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(a.allowlist.read_text(encoding='utf-8'))
    assert cfg['guards']==GUARDS
    assert cfg['status']=='FROZEN_PRE_READ_CANDIDATE_EVIDENCE_SOURCE_ALLOWLIST'
    n=cfg['network_policy']; assert n['free_web_search_allowed'] is False and n['search_engine_queries_allowed'] is False and n['unrestricted_url_following_allowed'] is False
    sources=[]
    for s in cfg['sources']:
        root=s['service_root']
        try:
            if s['protocol']=='ArcGIS_REST': meta=arcgis_metadata(root)
            elif s['protocol']=='HTTPS_OFFICIAL_PORTAL': meta=portal_probe(root)
            else: raise RuntimeError('UNSUPPORTED_PROTOCOL')
            sources.append({'source_id':s['source_id'],'service_root':root,**meta})
        except Exception as e:
            sources.append({'source_id':s['source_id'],'service_root':root,'source_status':'METADATA_UNAVAILABLE_FAIL_CLOSED','error_class':type(e).__name__,'error_code':str(e)[:180],'evidence_read':False})
    out={
      'schema_version':'0.1','batch_id':cfg['batch_id'],'status':'PASS_ALLOWLISTED_SERVICE_METADATA_DISCOVERY','guards':GUARDS,
      'allowlist_sha256':hashlib.sha256(a.allowlist.read_bytes()).hexdigest(),'free_web_search_used':False,'search_engine_used':False,
      'candidate_feature_queries_executed':False,'candidate_territorial_evidence_read':False,'control_labels_assigned':False,
      'sealed_target_unblind_allowed':False,'sources':sources,
      'next_gate':'BUILD_EXACT_CANDIDATE_BOUNDED_QUERY_MANIFEST_FROM_SCHEMA_ONLY_WHERE_POSSIBLE'
    }
    a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'source_statuses':{x['source_id']:x['source_status'] for x in sources},'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
