#!/usr/bin/env python3
"""Extract only generic infrastructure endpoint routes from inline scripts on frozen SIGRID pages.

Raw HTML and inline script bodies are never persisted or printed. Extracted routes are not followed.
"""
from __future__ import annotations
import argparse,hashlib,json,re,urllib.parse,urllib.request
from html.parser import HTMLParser
from pathlib import Path
GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
QUOTED=re.compile(r"(?P<q>['\"])(?P<s>(?:\\.|(?!\1).){1,500})(?P=q)")
FORBIDDEN=re.compile(r'(pedregal|quirio|carossio|carosio|cashahuacra|rayos\s+de\s+sol|la\s+libertad|a6680)',re.I)
NUMERIC_DOC=re.compile(r'/documento/\d+(?:/|$)',re.I)
class InlineScripts(HTMLParser):
 def __init__(self):super().__init__();self.in_inline=False;self.buf=[];self.blocks=[]
 def handle_starttag(self,tag,attrs):
  if tag.lower()=='script':
   d=dict(attrs);self.in_inline=not bool(d.get('src'));self.buf=[]
 def handle_data(self,data):
  if self.in_inline:self.buf.append(data)
 def handle_endtag(self,tag):
  if tag.lower()=='script' and self.in_inline:
   self.blocks.append(''.join(self.buf));self.in_inline=False;self.buf=[]
def norm(base,s,markers):
 s=s.replace('\\/','/').strip()
 if not s or len(s)>500 or any(x in s for x in ('\n','\r','\t','{','}')):return None
 if not (s.startswith(('https://','/','./','../')) or '/' in s):return None
 if not any(m in s.lower() for m in markers):return None
 try:u=urllib.parse.urljoin(base,s);q=urllib.parse.urlparse(u)
 except Exception:return None
 if q.scheme!='https':return None
 host=q.hostname or ''
 if not (host=='sigrid.cenepred.gob.pe' or host.endswith('.cenepred.gob.pe')):return None
 path=urllib.parse.unquote(q.path)
 if FORBIDDEN.search(path) or NUMERIC_DOC.search(path):return None
 # Query is intentionally discarded to avoid carrying identifiers or values into the next stage.
 return urllib.parse.urlunparse((q.scheme,q.netloc,q.path,'','',''))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 c=json.loads(a.contract.read_text(encoding='utf-8'));assert c['guards']==GUARDS and c['status']=='FROZEN_INFRASTRUCTURE_ONLY_INLINE_ENDPOINT_DISCOVERY';assert c['candidate_territorial_evidence_read'] is False and c['sealed_target_unblind_allowed'] is False
 markers=tuple(x.lower() for x in c['route_markers']);rows=[]
 for url in c['endpoints']:
  u=urllib.parse.urlparse(url);assert u.scheme=='https' and u.netloc=='sigrid.cenepred.gob.pe'
  req=urllib.request.Request(url,headers={'User-Agent':'IRFEN-research-cleanroom/0.1','Accept':'text/html'})
  with urllib.request.urlopen(req,timeout=30) as r:
   f=urllib.parse.urlparse(r.geturl());assert f.scheme=='https' and f.netloc==u.netloc
   b=r.read(int(c['extraction_policy']['maximum_html_bytes'])+1);status=int(r.status);ctype=r.headers.get('Content-Type','')
  if len(b)>int(c['extraction_policy']['maximum_html_bytes']):raise RuntimeError('HTML_TOO_LARGE')
  p=InlineScripts();p.feed(b.decode('utf-8','replace'))
  routes=[];hashes=[]
  for block in p.blocks:
   bb=block.encode('utf-8');hashes.append({'sha256':hashlib.sha256(bb).hexdigest(),'bytes':len(bb)})
   for mt in QUOTED.finditer(block):
    x=norm(url,mt.group('s'),markers)
    if x:routes.append(x)
  routes=sorted(set(routes));hashes=sorted(hashes,key=lambda x:(x['sha256'],x['bytes']))
  rows.append({'url':url,'http_status':status,'content_type':ctype,'html_response_sha256':hashlib.sha256(b).hexdigest(),'inline_script_count':len(p.blocks),'inline_script_hashes':hashes,'generic_endpoint_routes':routes,'generic_endpoint_route_count':len(routes)})
 out={'schema_version':'0.1','batch_id':c['batch_id'],'status':'PASS_SIGRID_INLINE_INFRASTRUCTURE_ENDPOINT_DISCOVERY','guards':GUARDS,'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE','contract_sha256':hashlib.sha256(a.contract.read_bytes()).hexdigest(),'endpoints':rows,'raw_html_written':False,'raw_inline_script_written':False,'raw_inline_script_logged':False,'external_script_bytes_read':False,'extracted_routes_followed':False,'query_strings_retained':False,'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'next_gate':'FREEZE_GENERIC_SPATIAL_ENDPOINTS_BEFORE_ANY_CANDIDATE_BOUNDED_QUERY'}
 raw=json.dumps(out,sort_keys=True,separators=(',',':'))+'\n'
 if FORBIDDEN.search(raw) or NUMERIC_DOC.search(raw):raise RuntimeError('FORBIDDEN_CONTENT_IN_INFRASTRUCTURE_OUTPUT')
 a.output.write_text(raw,encoding='utf-8');print(json.dumps({'status':out['status'],'route_count':sum(x['generic_endpoint_route_count'] for x in rows),'inline_script_count':sum(x['inline_script_count'] for x in rows),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
