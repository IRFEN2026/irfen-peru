#!/usr/bin/env python3
"""Read only the frozen SIGRID application script and emit endpoint-like routes.

The raw JavaScript body is never written or printed. Only URL/path-like string literals with
infrastructure markers are retained, and no discovered route is followed in this stage.
"""
from __future__ import annotations
import argparse, hashlib, json, re, urllib.parse, urllib.request
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
QUOTED=re.compile(r"(?P<q>['\"])(?P<s>(?:\\.|(?!\1).){1,400})(?P=q)")
INFRA=re.compile(r'(api|ajax|document|buscar|search|map|query|service|controller|action|json|php|sigrid|geoserver|arcgis)',re.I)
FORBIDDEN_CONTENT=re.compile(r'(pedregal|quirio|carossio|carosio|cashahuacra|rayos\s+de\s+sol|la\s+libertad|a6680)',re.I)

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def normalize(root:str,s:str):
    s=s.replace('\\/','/').strip()
    if not s or any(ch in s for ch in ('\n','\r','\t','{','}')): return None
    if not (s.startswith(('http://','https://','/','./','../','gp/','sigridv3/')) or '/' in s): return None
    if not INFRA.search(s): return None
    try: u=urllib.parse.urljoin(root,s); p=urllib.parse.urlparse(u)
    except Exception: return None
    if p.scheme!='https' or p.netloc!='sigrid.cenepred.gob.pe': return None
    path=urllib.parse.unquote(p.path)
    if FORBIDDEN_CONTENT.search(path) or FORBIDDEN_CONTENT.search(p.query): return None
    # Strip fragments; preserve static query parameters only as discovered text, never execute here.
    return urllib.parse.urlunparse((p.scheme,p.netloc,p.path,'',p.query,''))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    m=json.loads(a.manifest.read_text(encoding='utf-8'))
    assert m['guards']==GUARDS and m['status']=='FROZEN_INFRASTRUCTURE_STATIC_SCRIPT_READ_MANIFEST'
    assert m['candidate_territorial_evidence_read'] is False and m['sealed_target_unblind_allowed'] is False
    root='https://sigrid.cenepred.gob.pe/sigridv3/'
    results=[]
    for item in m['scripts']:
        url=item['url'];u=urllib.parse.urlparse(url)
        assert u.scheme=='https' and u.netloc=='sigrid.cenepred.gob.pe' and u.path.endswith('/main.js')
        req=urllib.request.Request(url,headers={'User-Agent':'IRFEN-research-cleanroom/0.1','Accept':'application/javascript,text/javascript,*/*;q=0.1'})
        with urllib.request.urlopen(req,timeout=30) as r:
            final=r.geturl();fp=urllib.parse.urlparse(final)
            if fp.scheme!='https' or fp.netloc!=u.netloc: raise RuntimeError('CROSS_HOST_REDIRECT')
            b=r.read(int(item['maximum_bytes'])+1)
            if len(b)>int(item['maximum_bytes']): raise RuntimeError('SCRIPT_TOO_LARGE')
            status=int(r.status);ctype=r.headers.get('Content-Type','')
        txt=b.decode('utf-8','replace')
        routes=[]
        for mt in QUOTED.finditer(txt):
            route=normalize(root,mt.group('s'))
            if route: routes.append(route)
        routes=sorted(set(routes))
        results.append({'url':url,'http_status':status,'content_type':ctype,'script_sha256':sha(b),'endpoint_like_routes':routes,'route_count':len(routes)})
    out={'schema_version':'0.1','batch_id':m['batch_id'],'status':'PASS_FROZEN_SCRIPT_ENDPOINT_ROUTE_EXTRACTION','guards':GUARDS,
         'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE','manifest_sha256':hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
         'raw_script_bytes_written':False,'raw_script_bytes_logged':False,'discovered_routes_followed':False,
         'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,
         'scripts':results,'next_gate':'FREEZE_EXACT_ENDPOINT_ROUTE_MANIFEST_BEFORE_ANY_DISCOVERED_ROUTE_IS_FOLLOWED'}
    raw=json.dumps(out,sort_keys=True,separators=(',',':'))+'\n'
    if FORBIDDEN_CONTENT.search(raw): raise RuntimeError('FORBIDDEN_CONTENT_IN_INFRASTRUCTURE_OUTPUT')
    a.output.write_text(raw,encoding='utf-8')
    print(json.dumps({'status':out['status'],'routes':sum(x['route_count'] for x in results),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True))
    return 0
if __name__=='__main__':raise SystemExit(main())
