#!/usr/bin/env python3
"""Repair the INGEMMET TLS chain using only a cryptographically verified public intermediate.

The AIA certificate is fetched from the exact frozen URI over untrusted HTTP, then accepted only if
it verifies the frozen server leaf and chains to the runner's system trust store. Only after that
cryptographic gate may exact allowlisted ArcGIS service/layer metadata be read over verified HTTPS.
No feature query or territorial evidence is read.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, tempfile, urllib.parse
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
PEM_RE=re.compile(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',re.S)
SAFE_FIELD=re.compile(r'^[A-Za-z0-9_]{1,96}$')
DATE_HINT=re.compile(r'(date|fecha|time|hora|year|anio|año)',re.I)

def cp(cmd,timeout=60):
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)

def curl_file(url: str, out: Path, *, ca: Path|None=None, proto: str='https', max_bytes: int=8_000_000):
    p=urllib.parse.urlparse(url)
    args=['curl','--fail','--silent','--show-error','--proto',f'={proto}','--max-redirs','0','--connect-timeout','20','--max-time','60','--output',str(out)]
    if ca is not None: args += ['--cacert',str(ca),'--tlsv1.2']
    args += [url]
    r=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=70)
    if r.returncode!=0: raise RuntimeError(f'CURL_{proto.upper()}_FAILED_{r.returncode}:{r.stderr.strip()[:160]}')
    if out.stat().st_size>max_bytes: raise RuntimeError('RESPONSE_TOO_LARGE')

def parse_json(path:Path): return json.loads(path.read_text(encoding='utf-8'))
def fsha(path:Path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    c=json.loads(a.contract.read_text(encoding='utf-8')); assert c['guards']==GUARDS and c['status']=='FROZEN_INFRASTRUCTURE_ONLY_INGEMMET_TLS_TRUST_RECOVERY'
    pol=c['trust_recovery_policy']; host=pol['exact_host']; root=pol['exact_service_root'].rstrip('/'); aia=c['prerequisite']['aia_ca_issuers_uri']; sysca=Path(pol['system_ca_file'])
    assert host=='geocatmin.ingemmet.gob.pe' and root.startswith('https://'+host+'/')
    assert urllib.parse.urlparse(aia).scheme=='http' and urllib.parse.urlparse(aia).hostname=='crt.sectigo.com'
    assert pol['disable_tls_verification_allowed'] is False and sysca.is_file()
    rep={'schema_version':'0.1','batch_id':c['batch_id'],'status':'PENDING','guards':GUARDS,'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE',
         'free_web_search_used':False,'search_engine_used':False,'feature_queries_executed':False,'candidate_territorial_evidence_read':False,
         'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'tls_verification_disabled':False,'raw_http_bodies_persisted':False,
         'aia_uri':aia,'aia_transport_trusted':False,'aia_acceptance_basis':'CRYPTOGRAPHIC_CHAIN_ONLY'}
    try:
      with tempfile.TemporaryDirectory(prefix='irfen_ingemmet_trust_') as td0:
        td=Path(td0); leaf=td/'leaf.pem'; interm_raw=td/'intermediate.raw'; interm=td/'intermediate.pem'; bundle=td/'ca-bundle.pem'
        hs=cp(['openssl','s_client','-connect',f'{host}:443','-servername',host,'-showcerts'],timeout=40)
        pems=PEM_RE.findall((hs.stdout or '')+'\n'+(hs.stderr or ''))
        if not pems: raise RuntimeError('NO_SERVER_LEAF_CERTIFICATE')
        leaf.write_text(pems[0]+'\n',encoding='ascii')
        leaf_hash=fsha(leaf)
        if leaf_hash!=c['prerequisite']['presented_leaf_pem_sha256']: raise RuntimeError(f'FROZEN_LEAF_HASH_MISMATCH {leaf_hash}')
        hc=cp(['openssl','x509','-in',str(leaf),'-noout','-checkhost',host])
        if hc.returncode!=0: raise RuntimeError('LEAF_HOSTNAME_CHECK_FAILED')
        curl_file(aia,interm_raw,proto='http',max_bytes=200_000)
        # AIA CA-Issuers commonly serves DER; accept DER or PEM only through x509 parsing.
        conv=cp(['openssl','x509','-inform','DER','-in',str(interm_raw),'-out',str(interm)])
        if conv.returncode!=0:
            conv=cp(['openssl','x509','-inform','PEM','-in',str(interm_raw),'-out',str(interm)])
        if conv.returncode!=0: raise RuntimeError('AIA_CERTIFICATE_PARSE_FAILED')
        subject=cp(['openssl','x509','-in',str(interm),'-noout','-subject']).stdout.strip()
        issuer=cp(['openssl','x509','-in',str(interm),'-noout','-issuer']).stdout.strip()
        verify=cp(['openssl','verify','-CAfile',str(sysca),'-untrusted',str(interm),str(leaf)])
        if verify.returncode!=0 or ': OK' not in verify.stdout: raise RuntimeError('CRYPTOGRAPHIC_CHAIN_VERIFICATION_FAILED:'+verify.stderr.strip()[:160])
        # Build a verification bundle: trusted system roots plus the now-verified intermediate.
        bundle.write_bytes(sysca.read_bytes()+b'\n'+interm.read_bytes())
        service_path=td/'service.json'; curl_file(root+'?f=pjson',service_path,ca=bundle,proto='https')
        service=parse_json(service_path); ids=sorted({int(x['id']) for x in service.get('layers',[]) if isinstance(x,dict) and isinstance(x.get('id'),int)})
        if not ids: raise RuntimeError('NO_NUMERIC_LAYERS_IN_SERVICE_METADATA')
        layers=[]
        for lid in ids:
            lp=td/f'layer_{lid}.json'; curl_file(root+f'/{lid}?f=pjson',lp,ca=bundle,proto='https')
            d=parse_json(lp); fields=[]
            for f in d.get('fields',[]):
                name=f.get('name');typ=f.get('type')
                if isinstance(name,str) and SAFE_FIELD.fullmatch(name) and isinstance(typ,str): fields.append({'name':name,'type':typ,'temporal_hint':bool(DATE_HINT.search(name))})
            fields.sort(key=lambda x:(x['name'],x['type']))
            layers.append({'layer_id':lid,'metadata_sha256':fsha(lp),'metadata_bytes':lp.stat().st_size,
                           'geometry_type':d.get('geometryType') if isinstance(d.get('geometryType'),str) else None,
                           'supports_query':bool(d.get('capabilities') and 'Query' in str(d.get('capabilities'))),
                           'max_record_count':d.get('maxRecordCount') if isinstance(d.get('maxRecordCount'),int) else None,'fields':fields})
        rep.update({'status':'PASS_INGEMMET_METADATA_VIA_CRYPTOGRAPHIC_TRUST_RECOVERY','leaf_pem_sha256':leaf_hash,
                    'aia_certificate_sha256':fsha(interm_raw),'verified_intermediate_pem_sha256':fsha(interm),
                    'intermediate_subject':subject,'intermediate_issuer':issuer,'system_chain_verification_passed':True,'leaf_hostname_verification_passed':True,
                    'metadata_https_verified_with_repaired_chain':True,'service_metadata_sha256':fsha(service_path),'service_metadata_bytes':service_path.stat().st_size,
                    'layer_count':len(layers),'layers':layers})
    except Exception as e:
        rep.update({'status':'FAIL_CLOSED_INGEMMET_TLS_TRUST_RECOVERY','error_class':type(e).__name__,'error_code':str(e)[:240]})
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':rep['status'],'layer_count':rep.get('layer_count',0),'system_chain_verification_passed':rep.get('system_chain_verification_passed',False),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0 if rep['status'].startswith('PASS_') else 2
if __name__=='__main__': raise SystemExit(main())
