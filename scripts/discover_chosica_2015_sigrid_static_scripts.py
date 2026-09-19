#!/usr/bin/env python3
"""Parse only same-host external JavaScript URLs from the frozen SIGRID portal root."""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
class Scripts(HTMLParser):
    def __init__(self): super().__init__(); self.src=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!='script': return
        d=dict(attrs); s=d.get('src')
        if s: self.src.append(s)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    c=json.loads(a.contract.read_text(encoding='utf-8'))
    assert c['guards']==GUARDS and c['status']=='FROZEN_INFRASTRUCTURE_ONLY_ENDPOINT_DISCOVERY'
    root=c['allowed_root']; u=urllib.parse.urlparse(root)
    req=urllib.request.Request(root,headers={'User-Agent':'IRFEN-research-cleanroom/0.1','Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=30) as r:
        final=r.geturl(); assert urllib.parse.urlparse(final).netloc==u.netloc
        b=r.read(int(c['raw_body_policy']['maximum_bytes'])+1)
        if len(b)>int(c['raw_body_policy']['maximum_bytes']): raise RuntimeError('ROOT_HTML_TOO_LARGE')
        status=int(r.status); ctype=r.headers.get('Content-Type','')
    p=Scripts(); p.feed(b.decode('utf-8','replace'))
    urls=[]
    for src in p.src:
        x=urllib.parse.urljoin(root,src); q=urllib.parse.urlparse(x)
        if q.scheme!='https' or q.netloc!=u.netloc: continue
        if not q.path.lower().endswith('.js'): continue
        urls.append(urllib.parse.urlunparse((q.scheme,q.netloc,q.path,'',q.query,'')))
    urls=sorted(set(urls))
    out={'schema_version':'0.1','batch_id':c['batch_id'],'status':'PASS_INFRASTRUCTURE_ONLY_SIGRID_SCRIPT_URL_DISCOVERY','guards':GUARDS,
         'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE','root_url':root,'root_http_status':status,'root_content_type':ctype,
         'root_response_sha256':hashlib.sha256(b).hexdigest(),'same_host_javascript_urls':urls,'script_bytes_read':False,
         'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,
         'next_gate':'FREEZE_SAME_HOST_STATIC_SCRIPT_URLS_BEFORE_SCRIPT_BYTES_ARE_READ'}
    a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'script_url_count':len(urls),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
