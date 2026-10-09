#!/usr/bin/env python3
"""Discover INGEMMET ArcGIS service/layer schema using system curl with certificate verification.

Exact allowlisted metadata endpoints only. No feature query is executed and raw response bodies
are neither printed nor persisted in repository artifacts.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, tempfile, urllib.parse
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
SAFE_FIELD=re.compile(r'^[A-Za-z0-9_]{1,96}$')
DATE_HINT=re.compile(r'(date|fecha|time|hora|year|anio|año)',re.I)

def curl_json(url:str, max_bytes:int=8_000_000):
    p=urllib.parse.urlparse(url)
    assert p.scheme=='https' and p.netloc=='geocatmin.ingemmet.gob.pe'
    with tempfile.TemporaryDirectory(prefix='irfen_ingemmet_meta_') as td:
        out=Path(td)/'body'
        cmd=['curl','--fail','--silent','--show-error','--proto','=https','--tlsv1.2','--max-redirs','0','--connect-timeout','20','--max-time','60','--output',str(out),url]
        cp=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        if cp.returncode!=0:
            raise RuntimeError(f'CURL_VERIFIED_TLS_FAILED_{cp.returncode}:{cp.stderr.strip()[:160]}')
        b=out.read_bytes()
        if len(b)>max_bytes: raise RuntimeError('METADATA_RESPONSE_TOO_LARGE')
        return json.loads(b.decode('utf-8')), hashlib.sha256(b).hexdigest(), len(b)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--allowlist',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(a.allowlist.read_text(encoding='utf-8'));assert cfg['guards']==GUARDS
    assert cfg['status']=='FROZEN_PRE_READ_CANDIDATE_EVIDENCE_SOURCE_ALLOWLIST'
    n=cfg['network_policy'];assert n['free_web_search_allowed'] is False and n['search_engine_queries_allowed'] is False and n['unrestricted_url_following_allowed'] is False
    src=[x for x in cfg['sources'] if x['source_id']=='INGEMMET_GEOCATMIN_PELIGROS_GEOLOGICOS']
    assert len(src)==1;root=src[0]['service_root'].rstrip('/')
    assert root=='https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/SERV_PELIGROS_GEOLOGICOS/MapServer'
    rep={'schema_version':'0.1','batch_id':cfg['batch_id'],'status':'PENDING','guards':GUARDS,'source_id':src[0]['source_id'],'service_root':root,
         'transport':'SYSTEM_CURL_VERIFIED_TLS_NO_INSECURE_FLAGS','free_web_search_used':False,'search_engine_used':False,
         'feature_queries_executed':False,'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False}
    try:
        service,shash,sbytes=curl_json(root+'?f=pjson')
        ids=sorted({int(x['id']) for x in service.get('layers',[]) if isinstance(x,dict) and isinstance(x.get('id'),int)})
        layers=[]
        for lid in ids:
            d,h,z=curl_json(root+f'/{lid}?f=pjson')
            fields=[]
            for f in d.get('fields',[]):
                name=f.get('name');typ=f.get('type')
                if isinstance(name,str) and SAFE_FIELD.fullmatch(name) and isinstance(typ,str):
                    fields.append({'name':name,'type':typ,'temporal_hint':bool(DATE_HINT.search(name))})
            fields.sort(key=lambda x:(x['name'],x['type']))
            layers.append({'layer_id':lid,'metadata_sha256':h,'metadata_bytes':z,'geometry_type':d.get('geometryType') if isinstance(d.get('geometryType'),str) else None,
                           'supports_query':bool(d.get('capabilities') and 'Query' in str(d.get('capabilities'))),'max_record_count':d.get('maxRecordCount') if isinstance(d.get('maxRecordCount'),int) else None,'fields':fields})
        rep.update({'status':'PASS_INGEMMET_VERIFIED_TLS_METADATA_DISCOVERY','service_metadata_sha256':shash,'service_metadata_bytes':sbytes,'layer_count':len(layers),'layers':layers})
    except Exception as e:
        rep.update({'status':'FAIL_CLOSED_INGEMMET_VERIFIED_TLS_METADATA_DISCOVERY','error_class':type(e).__name__,'error_code':str(e)[:220]})
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':rep['status'],'layer_count':rep.get('layer_count',0),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0 if rep['status'].startswith('PASS_') else 2
if __name__=='__main__':raise SystemExit(main())
