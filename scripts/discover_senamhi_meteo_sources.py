#!/usr/bin/env python3
"""Descubre rutas públicas SENAMHI para estaciones y lluvia acumulada.

No autentica ni scrapea datos personales. Inspecciona HTML público de Lima,
La Libertad y Piura para identificar iframes/endpoints que puedan servir como
validación terrestre paralela a IMERG.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import json,re,requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/stations/senamhi_source_discovery.json'
BASE='https://www.senamhi.gob.pe'
DEPARTMENTS={'san_ildefonso':'la-libertad','chosica':'lima','catacaos':'piura'}
PAGES=['estaciones','lluvia-acumulada','descarga-datos-meteorologicos']
HEADERS={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8','Accept':'text/html,application/xhtml+xml,*/*'}

def fetch(url,timeout=30):
 try:
  r=requests.get(url,headers=HEADERS,timeout=timeout,allow_redirects=True)
  return r,None
 except Exception as exc:return None,{'type':type(exc).__name__,'message':str(exc)}
def urls_from_html(html,base):
 values=[]
 patterns=[r'<iframe[^>]+src=["\']([^"\']+)',r'<script[^>]+src=["\']([^"\']+)',r'<link[^>]+href=["\']([^"\']+)',r'["\'](https?://[^"\']+)["\']']
 for pat in patterns:
  for m in re.finditer(pat,html,re.I):
   u=urljoin(base,m.group(1).strip())
   if u.startswith('http') and u not in values:values.append(u)
 return values
def classify(url):
 low=url.lower()
 tags=[]
 for tag,needles in {'iframe':['iframe','estacion','estaciones','hidro','meteo'],'data':['json','ajax','api','datos','data'],'rain':['lluvia','precip'],'map':['mapa','map'],'script':['.js']}.items():
  if any(n in low for n in needles):tags.append(tag)
 return tags
def probe(url):
 r,err=fetch(url,18)
 if err:return {'url':url,'status':'error','error':err}
 ctype=r.headers.get('content-type','')
 text=r.text[:150000] if 'text' in ctype or 'html' in ctype or 'javascript' in ctype or not ctype else ''
 return {'url':url,'status':'available' if r.status_code==200 else 'http_error','http_status':r.status_code,'content_type':ctype,'bytes':len(r.content),'title':(re.search(r'<title[^>]*>(.*?)</title>',text,re.I|re.S).group(1).strip() if text and re.search(r'<title[^>]*>(.*?)</title>',text,re.I|re.S) else None)}
def main():
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'purpose':'Descubrir canales públicos SENAMHI para validación meteorológica en tierra; no sustituye IMERG.','zones':[],'candidate_endpoints':[]}
 seen=set()
 for zone,dp in DEPARTMENTS.items():
  z={'zone_id':zone,'department_slug':dp,'pages':[]}
  for page in PAGES:
   url=f'{BASE}/servicios/main.php?dp={dp}&p={page}'
   r,err=fetch(url)
   item={'page':page,'url':url}
   if err:item.update({'status':'error','error':err});z['pages'].append(item);continue
   item.update({'status':'available' if r.status_code==200 else 'http_error','http_status':r.status_code,'content_type':r.headers.get('content-type',''),'bytes':len(r.content)})
   discovered=urls_from_html(r.text,url);item['discovered_urls']=discovered
   for u in discovered:
    host=urlparse(u).netloc.lower()
    if 'senamhi.gob.pe' not in host:continue
    if u in seen:continue
    seen.add(u);tags=classify(u)
    if not tags:continue
    p=probe(u);p['tags']=tags;report['candidate_endpoints'].append(p)
   z['pages'].append(item)
  report['zones'].append(z)
 report['summary']={'pages_available':sum(1 for z in report['zones'] for p in z['pages'] if p.get('status')=='available'),'candidate_endpoints':len(report['candidate_endpoints']),'available_candidates':sum(1 for p in report['candidate_endpoints'] if p.get('status')=='available')}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'summary':report['summary'],'candidates':report['candidate_endpoints']},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
