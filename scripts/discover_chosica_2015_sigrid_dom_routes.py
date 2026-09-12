#!/usr/bin/env python3
"""Emit only same-host endpoint-like URLs from URL-bearing attributes on the exact SIGRID root."""
from __future__ import annotations
import argparse,hashlib,json,re,urllib.parse,urllib.request
from html.parser import HTMLParser
from pathlib import Path
GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
FORBIDDEN=re.compile(r'(pedregal|quirio|carossio|carosio|cashahuacra|rayos\s+de\s+sol|la\s+libertad|a6680)',re.I)
class Links(HTMLParser):
 def __init__(self):super().__init__();self.values=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs);t=tag.lower()
  if t=='a' and d.get('href'):self.values.append(('a.href',d['href']))
  elif t=='form' and d.get('action'):self.values.append(('form.action',d['action']))
  elif t=='script' and d.get('src'):self.values.append(('script.src',d['src']))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 c=json.loads(a.contract.read_text(encoding='utf-8'));assert c['guards']==GUARDS and c['status']=='FROZEN_INFRASTRUCTURE_ONLY_DOM_ROUTE_DISCOVERY';assert c['candidate_territorial_evidence_read'] is False and c['sealed_target_unblind_allowed'] is False
 root=c['allowed_root'];rp=urllib.parse.urlparse(root);req=urllib.request.Request(root,headers={'User-Agent':'IRFEN-research-cleanroom/0.1','Accept':'text/html'})
 with urllib.request.urlopen(req,timeout=30) as r:
  final=r.geturl();fp=urllib.parse.urlparse(final);assert fp.scheme=='https' and fp.netloc==rp.netloc;b=r.read(int(c['raw_body_policy']['maximum_bytes'])+1);status=int(r.status);ctype=r.headers.get('Content-Type','')
 if len(b)>int(c['raw_body_policy']['maximum_bytes']):raise RuntimeError('ROOT_HTML_TOO_LARGE')
 p=Links();p.feed(b.decode('utf-8','replace'));markers=tuple(x.lower() for x in c['route_markers']);outlinks=[]
 for attr,v in p.values:
  try:u=urllib.parse.urljoin(root,v);q=urllib.parse.urlparse(u)
  except Exception:continue
  if q.scheme!='https' or q.netloc!=rp.netloc:continue
  normalized=urllib.parse.urlunparse((q.scheme,q.netloc,q.path,'',q.query,''))
  low=normalized.lower()
  if not any(m in low for m in markers):continue
  if FORBIDDEN.search(normalized):continue
  outlinks.append({'attribute':attr,'url':normalized})
 outlinks=sorted({(x['attribute'],x['url']) for x in outlinks});rows=[{'attribute':x,'url':y} for x,y in outlinks]
 out={'schema_version':'0.2','batch_id':c['batch_id'],'status':'PASS_INFRASTRUCTURE_ONLY_SIGRID_DOM_ROUTE_DISCOVERY','guards':GUARDS,'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE','root_url':root,'root_http_status':status,'root_content_type':ctype,'root_response_sha256':hashlib.sha256(b).hexdigest(),'routes':rows,'route_count':len(rows),'routes_followed':False,'linked_content_read':False,'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'next_gate':'FREEZE_EXACT_CANDIDATE_METADATA_ENDPOINTS_BEFORE_ANY_ROUTE_IS_FOLLOWED'}
 raw=json.dumps(out,sort_keys=True,separators=(',',':'))+'\n';assert not FORBIDDEN.search(raw);a.output.write_text(raw,encoding='utf-8');print(json.dumps({'status':out['status'],'route_count':len(rows),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
