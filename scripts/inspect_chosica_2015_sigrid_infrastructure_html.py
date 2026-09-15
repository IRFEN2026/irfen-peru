#!/usr/bin/env python3
"""Inspect only structural HTML attributes from frozen generic SIGRID endpoints."""
from __future__ import annotations
import argparse,hashlib,json,re,urllib.parse,urllib.request
from html.parser import HTMLParser
from pathlib import Path
GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
SAFE_NAME=re.compile(r'^[A-Za-z0-9_:\-\.\[\]]{1,120}$')
FORBIDDEN=re.compile(r'(pedregal|quirio|carossio|carosio|cashahuacra|rayos\s+de\s+sol|la\s+libertad|a6680)',re.I)
class Structure(HTMLParser):
 def __init__(self,base): super().__init__(); self.base=base; self.forms=[]; self.scripts=[]; self._form=None
 def handle_starttag(self,tag,attrs):
  d=dict(attrs); t=tag.lower()
  if t=='form':
   action=d.get('action',''); method=d.get('method','GET').upper(); u=urllib.parse.urljoin(self.base,action) if action else self.base
   q=urllib.parse.urlparse(u); self._form={'method':method if method in ('GET','POST') else 'OTHER','action':urllib.parse.urlunparse((q.scheme,q.netloc,q.path,'',q.query,'')),'inputs':[]}; self.forms.append(self._form)
  elif t in ('input','select','textarea') and self._form is not None:
   name=d.get('name'); typ=('select' if t=='select' else 'textarea' if t=='textarea' else d.get('type','text').lower())
   if isinstance(name,str) and SAFE_NAME.fullmatch(name): self._form['inputs'].append({'name':name,'type':typ[:40]})
  elif t=='script' and d.get('src'):
   u=urllib.parse.urljoin(self.base,d['src']);q=urllib.parse.urlparse(u)
   if q.scheme=='https' and q.netloc=='sigrid.cenepred.gob.pe' and q.path.lower().endswith('.js'):
    self.scripts.append(urllib.parse.urlunparse((q.scheme,q.netloc,q.path,'',q.query,'')))
 def handle_endtag(self,tag):
  if tag.lower()=='form': self._form=None

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 m=json.loads(a.manifest.read_text(encoding='utf-8'));assert m['guards']==GUARDS and m['status']=='FROZEN_SIGRID_GENERIC_INFRASTRUCTURE_ENDPOINTS';assert m['candidate_territorial_evidence_read'] is False and m['sealed_target_unblind_allowed'] is False
 rows=[]
 for ep in m['endpoints']:
  url=ep['url'];q=urllib.parse.urlparse(url);assert q.scheme=='https' and q.netloc=='sigrid.cenepred.gob.pe'
  req=urllib.request.Request(url,headers={'User-Agent':'IRFEN-research-cleanroom/0.1','Accept':'text/html'})
  with urllib.request.urlopen(req,timeout=30) as r:
   final=r.geturl();fq=urllib.parse.urlparse(final);assert fq.scheme=='https' and fq.netloc==q.netloc;b=r.read(int(ep['maximum_bytes'])+1);status=int(r.status);ctype=r.headers.get('Content-Type','')
  if len(b)>int(ep['maximum_bytes']):raise RuntimeError('HTML_TOO_LARGE')
  p=Structure(url);p.feed(b.decode('utf-8','replace'))
  forms=[]
  for f in p.forms:
   aq=urllib.parse.urlparse(f['action'])
   if aq.scheme!='https' or aq.netloc!='sigrid.cenepred.gob.pe':continue
   inputs=sorted({(x['name'],x['type']) for x in f['inputs']});forms.append({'method':f['method'],'action':f['action'],'inputs':[{'name':n,'type':t} for n,t in inputs]})
  forms=sorted(forms,key=lambda x:(x['method'],x['action'],json.dumps(x['inputs'],sort_keys=True)))
  scripts=sorted(set(p.scripts))
  row={'url':url,'http_status':status,'content_type':ctype,'response_sha256':hashlib.sha256(b).hexdigest(),'forms':forms,'same_host_script_urls':scripts}
  raw=json.dumps(row,sort_keys=True)
  if FORBIDDEN.search(raw):raise RuntimeError('FORBIDDEN_CONTENT_IN_STRUCTURAL_OUTPUT')
  rows.append(row)
 out={'schema_version':'0.1','batch_id':m['batch_id'],'status':'PASS_SIGRID_INFRASTRUCTURE_HTML_SCHEMA','guards':GUARDS,'classification':'INFRASTRUCTURE_ONLY_NOT_TERRITORIAL_EVIDENCE','manifest_sha256':hashlib.sha256(a.manifest.read_bytes()).hexdigest(),'endpoints':rows,'text_nodes_retained':False,'input_values_retained':False,'linked_content_followed':False,'scripts_read':False,'candidate_territorial_evidence_read':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'next_gate':'FREEZE_DISCOVERED_FORM_SCHEMAS_AND_STATIC_APP_SCRIPTS_BEFORE_ANY_QUERY_OR_SCRIPT_READ'}
 raw=json.dumps(out,sort_keys=True,separators=(',',':'))+'\n';assert not FORBIDDEN.search(raw);a.output.write_text(raw,encoding='utf-8');print(json.dumps({'status':out['status'],'form_count':sum(len(x['forms']) for x in rows),'script_count':sum(len(x['same_host_script_urls']) for x in rows),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
