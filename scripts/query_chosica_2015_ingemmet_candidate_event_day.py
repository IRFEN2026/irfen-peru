#!/usr/bin/env python3
"""Execute the frozen candidate-only INGEMMET event-day query manifest.

This stage may read candidate-local evidence only after candidate selection and exact basin geometries
are frozen. It cannot confirm a negative control from absence. Any candidate-local exact-day geological
hazard record only excludes that candidate from a clean negative-control role.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, re, subprocess, tempfile, urllib.parse
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
PEM_RE=re.compile(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',re.S)
FORBIDDEN_TEXT=('pedregal','quirio','carossio','carosio','rayos de sol','cashahuacra','la libertad','a6680','official_outcome_evidence')

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,timeout=70): return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)

def curl_file(args:list[str], out:Path, timeout=80):
    cp=subprocess.run(['curl','--fail','--silent','--show-error','--max-redirs','0','--output',str(out)]+args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if cp.returncode!=0: raise RuntimeError(f'CURL_FAILED_{cp.returncode}:{cp.stderr.strip()[:180]}')
    if out.stat().st_size>8_000_000: raise RuntimeError('RESPONSE_TOO_LARGE')

def bootstrap_verified_bundle(manifest:dict, td:Path):
    src=manifest['source'];host='geocatmin.ingemmet.gob.pe';aia='http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt';sysca=Path('/etc/ssl/certs/ca-certificates.crt')
    leaf=td/'leaf.pem';raw=td/'intermediate.raw';interm=td/'intermediate.pem';bundle=td/'bundle.pem'
    hs=run(['openssl','s_client','-connect',f'{host}:443','-servername',host,'-showcerts'],40)
    pems=PEM_RE.findall((hs.stdout or '')+'\n'+(hs.stderr or ''))
    if not pems: raise RuntimeError('NO_SERVER_CERTIFICATE')
    leaf.write_text(pems[0]+'\n',encoding='ascii')
    if sha(leaf)!=src['tls_leaf_pem_sha256']: raise RuntimeError('FROZEN_LEAF_HASH_MISMATCH')
    if run(['openssl','x509','-in',str(leaf),'-noout','-checkhost',host]).returncode!=0: raise RuntimeError('LEAF_HOSTNAME_CHECK_FAILED')
    curl_file(['--proto','=http',aia],raw)
    if sha(raw)!=src['aia_certificate_sha256']: raise RuntimeError('FROZEN_AIA_CERTIFICATE_HASH_MISMATCH')
    conv=run(['openssl','x509','-inform','DER','-in',str(raw),'-out',str(interm)])
    if conv.returncode!=0: conv=run(['openssl','x509','-inform','PEM','-in',str(raw),'-out',str(interm)])
    if conv.returncode!=0: raise RuntimeError('AIA_CERT_PARSE_FAILED')
    if sha(interm)!=src['verified_intermediate_pem_sha256']: raise RuntimeError('FROZEN_INTERMEDIATE_HASH_MISMATCH')
    vr=run(['openssl','verify','-CAfile',str(sysca),'-untrusted',str(interm),str(leaf)])
    if vr.returncode!=0 or ': OK' not in vr.stdout: raise RuntimeError('CHAIN_VERIFICATION_FAILED')
    bundle.write_bytes(sysca.read_bytes()+b'\n'+interm.read_bytes())
    return bundle

def esri_polygon(geom:dict):
    typ=geom['type']; coords=geom['coordinates']; rings=[]
    if typ=='Polygon': rings=list(coords)
    elif typ=='MultiPolygon':
        for poly in coords: rings.extend(poly)
    else: raise RuntimeError(f'UNSUPPORTED_CANDIDATE_GEOMETRY_{typ}')
    clean=[]
    for ring in rings:
        if len(ring)<4: raise RuntimeError('DEGENERATE_RING')
        rr=[[round(float(x),8),round(float(y),8)] for x,y in ring]
        if rr[0]!=rr[-1]: rr.append(rr[0])
        clean.append(rr)
    return {'rings':clean,'spatialReference':{'wkid':4326}}

def sanitize_value(v):
    if v is None or isinstance(v,(int,float,bool)): return v
    s=' '.join(str(v).split())[:160]
    low=s.lower()
    for tok in FORBIDDEN_TEXT:
        if tok in low: raise RuntimeError('FORBIDDEN_TARGET_OR_SEALED_TOKEN_IN_CANDIDATE_EVIDENCE')
    return s

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    m=json.loads(a.manifest.read_text(encoding='utf-8'));g=json.loads(a.geometry.read_text(encoding='utf-8'))
    assert m['status']=='FROZEN_PRE_EXECUTION_CANDIDATE_POLYGON_BOUNDED_INGEMMET_QUERY_MANIFEST' and m['guards']==GUARDS
    assert sha(a.geometry)==m['candidate_geometry']['sha256']; assert len(g['features'])==m['candidate_geometry']['candidate_count']==7
    assert m['query_policy']['candidate_reranking_allowed'] is False and m['query_policy']['feedback_to_matching_allowed'] is False
    rep={'schema_version':'0.1','batch_id':m['batch_id'],'status':'PENDING','guards':GUARDS,'phase':'CANDIDATE_ONLY_TERRITORIAL_EVIDENCE_INGEMMET_EVENT_DAY',
         'manifest_sha256':sha(a.manifest),'candidate_geometry_sha256':sha(a.geometry),'candidate_count':7,'candidate_selection_modified':False,'candidate_reranking_performed':False,
         'feedback_to_matching_performed':False,'free_web_search_used':False,'search_engine_used':False,'a6680_read':False,'target_outcome_read':False,'contaminated_artifact_read':False,
         'sealed_target_unblind_allowed':False,'absence_can_confirm_control':False,'control_confirmed_by_this_source_alone':False,'raw_responses_persisted':False}
    try:
      with tempfile.TemporaryDirectory(prefix='irfen_candidate_ingemmet_') as td0:
        td=Path(td0);bundle=bootstrap_verified_bundle(m,td); root=m['source']['service_root'].rstrip('/');where=m['event_day_filter']['where'];results=[]
        features=sorted(g['features'],key=lambda f:f['properties']['candidate_code'])
        for f in features:
            code=f['properties']['candidate_code'];poly=json.dumps(esri_polygon(f['geometry']),separators=(',',':'))
            records=[];query_hashes=[]
            for layer in m['layers']:
                lid=int(layer['layer_id']);outfields=','.join(layer['out_fields']);rp=td/f'{code}_{lid}.json'
                args=['--proto','=https','--cacert',str(bundle),'--tlsv1.2','--request','POST',
                      '--data-urlencode','f=json','--data-urlencode',f'where={where}','--data-urlencode',f'geometry={poly}',
                      '--data-urlencode','geometryType=esriGeometryPolygon','--data-urlencode','inSR=4326','--data-urlencode',f'spatialRel={m["candidate_geometry"]["geometry_relation"]}',
                      '--data-urlencode',f'outFields={outfields}','--data-urlencode','returnGeometry=false',root+f'/{lid}/query']
                curl_file(args,rp);raw=rp.read_bytes();query_hashes.append({'layer_id':lid,'response_sha256':hashlib.sha256(raw).hexdigest(),'response_bytes':len(raw)})
                d=json.loads(raw.decode('utf-8'))
                if 'error' in d: raise RuntimeError(f'ARCGIS_QUERY_ERROR_LAYER_{lid}_{d["error"].get("code","UNKNOWN")}')
                for row in d.get('features',[]):
                    attrs=row.get('attributes',{});rec={'layer_id':lid}
                    for key in layer['out_fields']:
                        if key in attrs: rec[key]=sanitize_value(attrs[key])
                    records.append(rec)
            records.sort(key=lambda x:(x.get('layer_id'),x.get('OBJECTID',-1),str(x.get('FECHA'))))
            disposition='EXCLUDE_FROM_CLEAN_NEGATIVE_CONTROL' if records else 'OUTCOME_UNKNOWN_NOT_CONTROL'
            results.append({'candidate_code':code,'candidate_local_exact_day_record_count':len(records),'disposition':disposition,'records':records,'query_responses':query_hashes})
        rep.update({'status':'PASS_CANDIDATE_ONLY_INGEMMET_EVENT_DAY_QUERY','results':results,'candidate_with_local_record_count':sum(bool(x['candidate_local_exact_day_record_count']) for x in results),
                    'candidate_excluded_count':sum(x['disposition']=='EXCLUDE_FROM_CLEAN_NEGATIVE_CONTROL' for x in results),'candidate_outcome_unknown_count':sum(x['disposition']=='OUTCOME_UNKNOWN_NOT_CONTROL' for x in results)})
    except Exception as e:
        rep.update({'status':'FAIL_CLOSED_CANDIDATE_ONLY_INGEMMET_EVENT_DAY_QUERY','error_class':type(e).__name__,'error_code':str(e)[:240]})
    a.output.write_text(json.dumps(rep,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':rep['status'],'candidate_with_local_record_count':rep.get('candidate_with_local_record_count',0),'candidate_excluded_count':rep.get('candidate_excluded_count',0),'candidate_outcome_unknown_count':rep.get('candidate_outcome_unknown_count',0),'output_sha256':sha(a.output)},sort_keys=True))
    return 0 if rep['status'].startswith('PASS_') else 2
if __name__=='__main__': raise SystemExit(main())
