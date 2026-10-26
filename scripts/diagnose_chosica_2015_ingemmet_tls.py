#!/usr/bin/env python3
"""Infrastructure-only TLS diagnostics for the exact allowlisted INGEMMET host.

Reads peer certificate metadata only. It never performs HTTP, never disables verification,
and never reads territorial evidence or outcomes.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, tempfile
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
PEM_RE=re.compile(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',re.S)
URI_RE=re.compile(r'CA Issuers - URI:([^\s,]+)')

def run(cmd, input_text=None):
    return subprocess.run(cmd,input=input_text,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)

def cert_meta(p:Path):
    cp=run(['openssl','x509','-in',str(p),'-noout','-subject','-issuer','-dates','-ext','subjectAltName','-ext','authorityInfoAccess','-fingerprint','-sha256'])
    if cp.returncode!=0: raise RuntimeError('OPENSSL_X509_PARSE_FAILED')
    txt=cp.stdout
    def one(prefix):
        for line in txt.splitlines():
            if line.startswith(prefix): return line[len(prefix):].strip()
        return None
    sans=[]
    for line in txt.splitlines():
        if 'DNS:' in line:
            sans += [x.strip()[4:] for x in line.split(',') if x.strip().startswith('DNS:')]
    return {
      'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
      'subject':one('subject='), 'issuer':one('issuer='),
      'not_before':one('notBefore='), 'not_after':one('notAfter='),
      'dns_sans':sorted(set(sans)),
      'aia_ca_issuers_uris':sorted(set(URI_RE.findall(txt)))
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    c=json.loads(a.contract.read_text(encoding='utf-8')); assert c['guards']==GUARDS
    assert c['status']=='FROZEN_INFRASTRUCTURE_ONLY_INGEMMET_TLS_DIAGNOSTICS'
    host=c['source_host']; port=int(c['port']); assert host=='geocatmin.ingemmet.gob.pe' and port==443
    rep={'schema_version':'0.1','batch_id':c['batch_id'],'status':'PENDING','guards':GUARDS,'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE',
         'host':host,'port':port,'http_requests_executed':False,'tls_verification_disabled':False,'aia_uris_fetched':False,
         'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'free_web_search_used':False}
    try:
        cp=run(['openssl','s_client','-connect',f'{host}:{port}','-servername',host,'-showcerts','-verify_return_error'],input_text='')
        combined=(cp.stdout or '')+'\n'+(cp.stderr or '')
        pems=PEM_RE.findall(combined)
        if not pems: raise RuntimeError('NO_PEER_CERTIFICATES_PRESENTED')
        with tempfile.TemporaryDirectory(prefix='irfen_tls_') as td:
            metas=[]
            for i,pem in enumerate(pems):
                p=Path(td)/f'cert_{i}.pem';p.write_text(pem+'\n',encoding='ascii');metas.append(cert_meta(p))
        verify_code=None; verify_text=None
        m=re.search(r'Verify return code:\s*(\d+)\s*\(([^\)]*)\)',combined)
        if m: verify_code=int(m.group(1)); verify_text=m.group(2).strip()
        rep.update({'status':'PASS_INGEMMET_TLS_DIAGNOSTICS','presented_certificate_count':len(metas),'certificates':metas,
                    'openssl_exit_code':cp.returncode,'verify_return_code':verify_code,'verify_return_text':verify_text,
                    'system_trust_verification_passed':verify_code==0 and cp.returncode==0})
    except Exception as e:
        rep.update({'status':'FAIL_CLOSED_INGEMMET_TLS_DIAGNOSTICS','error_class':type(e).__name__,'error_code':str(e)[:220]})
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':rep['status'],'presented_certificate_count':rep.get('presented_certificate_count',0),
                      'system_trust_verification_passed':rep.get('system_trust_verification_passed',False),
                      'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0 if rep['status'].startswith('PASS_') else 2
if __name__=='__main__': raise SystemExit(main())
