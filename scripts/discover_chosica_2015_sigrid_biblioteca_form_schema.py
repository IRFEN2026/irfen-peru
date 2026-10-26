#!/usr/bin/env python3
"""Read only SIGRID biblioteca HTML form/schema infrastructure.

No form is submitted, no link is followed, no visible text/value/document metadata is retained.
This is an infrastructure-only clean-room discovery stage.
"""
from __future__ import annotations
import argparse, hashlib, html.parser, json, urllib.parse, urllib.request
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
HOST="sigrid.cenepred.gob.pe"

class Forms(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.forms=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        d={str(k).lower():str(v) for k,v in attrs if k and v is not None}
        t=tag.lower()
        if t=='form':
            self.current={'method':d.get('method','get').lower(),'action':d.get('action',''),'controls':[]}; self.forms.append(self.current)
        elif self.current is not None and t in ('input','select','textarea','button'):
            name=d.get('name','').strip()
            if name:
                self.current['controls'].append({'tag':t,'name':name,'type':d.get('type','').lower() if t in ('input','button') else t})
    def handle_endtag(self, tag):
        if tag.lower()=='form': self.current=None

def canonical_action(base, raw):
    u=urllib.parse.urljoin(base,raw or '')
    p=urllib.parse.urlparse(u)
    if p.scheme!='https' or p.hostname!=HOST: raise RuntimeError('FORM_ACTION_LEFT_FROZEN_HOST')
    return urllib.parse.urlunparse((p.scheme,p.netloc,p.path,'','',''))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    c=json.loads(a.contract.read_text(encoding='utf-8')); assert c['guards']==GUARDS
    assert c['status']=='FROZEN_INFRASTRUCTURE_ONLY_SIGRID_BIBLIOTECA_FORM_DISCOVERY'
    assert c['network_policy']=={'free_web_search_allowed':False,'search_engine_allowed':False,'redirects_allowed':False,'same_host_only':True,'forms_submitted':False,'linked_routes_followed':False}
    url=c['exact_url']; p=urllib.parse.urlparse(url); assert p.scheme=='https' and p.hostname==HOST and p.query=='' and p.fragment==''
    rep={'schema_version':'0.1','batch_id':c['batch_id'],'status':'PENDING','guards':GUARDS,'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE',
         'exact_url':url,'free_web_search_used':False,'search_engine_used':False,'forms_submitted':False,'linked_routes_followed':False,
         'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,
         'visible_text_retained':False,'input_values_retained':False,'option_values_or_labels_retained':False,'document_metadata_retained':False}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'IRFEN-ResearchOnly-InfrastructureSchema/0.1'})
        opener=urllib.request.build_opener(urllib.request.HTTPHandler(),urllib.request.HTTPSHandler())
        with opener.open(req,timeout=30) as r:
            if getattr(r,'status',200)!=200: raise RuntimeError(f'HTTP_STATUS_{getattr(r,"status",None)}')
            final=urllib.parse.urlparse(r.geturl())
            if final.scheme!='https' or final.hostname!=HOST or r.geturl()!=url: raise RuntimeError('REDIRECT_OR_HOST_CHANGE')
            body=r.read(2_000_001); ctype=r.headers.get('Content-Type','')
        if len(body)>2_000_000: raise RuntimeError('HTML_TOO_LARGE')
        parser=Forms(); parser.feed(body.decode('utf-8','replace'))
        forms=[]
        for f in parser.forms:
            method=f['method'] if f['method'] in ('get','post') else 'other'
            controls=sorted({(x['tag'],x['name'],x['type']) for x in f['controls']})
            forms.append({'method':method,'action':canonical_action(url,f['action']),'controls':[{'tag':x[0],'name':x[1],'type':x[2]} for x in controls]})
        forms=sorted(forms,key=lambda x:(x['action'],x['method'],json.dumps(x['controls'],sort_keys=True)))
        rep.update({'status':'PASS_SIGRID_BIBLIOTECA_FORM_SCHEMA_DISCOVERY','http_status':200,'content_type':ctype.split(';')[0].strip().lower(),
                    'response_sha256':hashlib.sha256(body).hexdigest(),'form_count':len(forms),'forms':forms})
    except Exception as e:
        rep.update({'status':'FAIL_CLOSED_SIGRID_BIBLIOTECA_FORM_SCHEMA_DISCOVERY','error_class':type(e).__name__,'error_code':str(e)[:220]})
    a.output.write_text(json.dumps(rep,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':rep['status'],'form_count':rep.get('form_count',0),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0 if rep['status'].startswith('PASS_') else 2

if __name__=='__main__': raise SystemExit(main())
