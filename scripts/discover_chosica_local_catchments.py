#!/usr/bin/env python3
"""Indexa referencias geométricas para quebradas locales de Chosica.

Usa el informe INGEMMET/SIGRID del evento 23/03/2015 para localizar páginas,
coordenadas UTM/geográficas y áreas candidatas asociadas a Rayos de Sol, Quirio,
Pedregal y quebradas vecinas. No interpreta automáticamente una coordenada como
outlet ni un área como cuenca; todo queda en revisión antes de delinear DEM.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
import json,re,tempfile,zipfile
import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/calibration/chosica_local_catchment_references.json'
DOC_ID=3642
URLS=[
 f'https://sigrid.cenepred.gob.pe/sigridv3/documento/{DOC_ID}/descargar',
 f'https://sigrid4.cenepred.gob.pe/sigridv4/documento/{DOC_ID}/descargar',
 f'https://sigrid.cenepred.gob.pe/sigridv3/documento/{DOC_ID}'
]
MAX_BYTES=45*1024*1024
QUEBRADAS={
 'rayos_de_sol':['rayos de sol'],
 'quirio':['quirio'],
 'pedregal':['pedregal','san antonio de pedregal'],
 'carosio':['carosio'],
 'la_libertad':['la libertad'],
 'corrales':['corrales'],
 'cashahuacra':['cashahuacra'],
}

def norm(x):return re.sub(r'\s+',' ',x or '').strip()
def download():
 headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'};attempts=[]
 for u in URLS:
  try:
   r=requests.get(u,headers=headers,timeout=(15,120),allow_redirects=True)
   attempts.append({'url':u,'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type'),'bytes':len(r.content)})
   if r.status_code==200 and len(r.content)<=MAX_BYTES:
    if r.content[:4]==b'%PDF' or zipfile.is_zipfile(BytesIO(r.content)):return r.content,attempts
  except Exception as exc:attempts.append({'url':u,'status':'error','error_type':type(exc).__name__,'error':str(exc)})
 raise RuntimeError(f'No se obtuvo PDF/ZIP válido: {attempts}')
def utm_pairs(text):
 out=[]
 patterns=[
  r'(?i)(?:este|easting|utm\s*e|coordenada\s*e)\D{0,25}(\d{5,7}(?:[.,]\d+)?)\D{0,100}(?:norte|northing|utm\s*n|coordenada\s*n)\D{0,25}(\d{6,8}(?:[.,]\d+)?)',
  r'\b(\d{6})\s*(?:m\s*)?[Ee]\b.{0,100}?\b(\d{7})\s*(?:m\s*)?[Nn]\b'
 ]
 for pat in patterns:
  for m in re.finditer(pat,text,re.S):
   try:e=float(m.group(1).replace(',','.'));n=float(m.group(2).replace(',','.'))
   except:continue
   if 100000<=e<=900000 and 8000000<=n<=10000000:out.append({'easting':e,'northing':n})
 ded=[];seen=set()
 for x in out:
  k=(x['easting'],x['northing'])
  if k not in seen:seen.add(k);ded.append(x)
 return ded[:100]
def lonlat_pairs(text):
 out=[]
 pats=[
  r'(?i)(?:latitud|lat)\D{0,20}(-?\d{1,2}[.,]\d+)\D{0,80}(?:longitud|lon)\D{0,20}(-?\d{2,3}[.,]\d+)',
  r'\b(-?1[01][.,]\d{3,})\s*[,; ]+(-?7[67][.,]\d{3,})\b'
 ]
 for pat in pats:
  for m in re.finditer(pat,text,re.S):
   try:a=float(m.group(1).replace(',','.'));b=float(m.group(2).replace(',','.'))
   except:continue
   lat,lon=(a,b) if -20<a<0 and -90<b<-60 else (b,a)
   if -20<lat<0 and -90<lon<-60:out.append({'lon':lon,'lat':lat})
 return out[:100]
def area_tokens(text):
 out=[]
 for m in re.finditer(r'(?<!\d)(\d{1,5}(?:[.,]\d{1,3})?)\s*(km(?:2|²)|ha|hectáreas|hectareas)\b',text,re.I):
  out.append({'value_text':m.group(1),'unit_text':m.group(2)})
 return out[:100]
def crs_tokens(text):
 vals=[]
 for pat,label in [(r'(?i)WGS\s*[- ]?84','WGS84'),(r'(?i)UTM','UTM'),(r'(?i)(?:zona|zone)\s*18\s*S','UTM zone 18S'),(r'(?i)(?:zona|zone)\s*18','UTM zone 18')]:
  if re.search(pat,text):vals.append(label)
 return vals
def process_pdf(pdf):
 reader=PdfReader(str(pdf));pages={k:[] for k in QUEBRADAS};records=[];text_pages=0
 for pageno,page in enumerate(reader.pages,start=1):
  try:raw=page.extract_text() or ''
  except:raw=''
  if not raw.strip():continue
  text_pages+=1;low=raw.lower();hits=[]
  for k,needles in QUEBRADAS.items():
   if any(n in low for n in needles):pages[k].append(pageno);hits.append(k)
  if not hits:continue
  record={'page':pageno,'quebrada_tags':sorted(hits),'utm_candidates':utm_pairs(raw),'geographic_candidates':lonlat_pairs(raw),'area_candidates':area_tokens(raw),'crs_tokens':crs_tokens(raw),'production_use':False}
  if record['utm_candidates'] or record['geographic_candidates'] or record['area_candidates'] or record['crs_tokens']:records.append(record)
 return {'page_count':len(reader.pages),'text_layer_pages':text_pages,'page_index':{k:v for k,v in pages.items() if v},'geometry_reference_candidates':records}
def main():
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'source':{'document_id':DOC_ID,'publisher':'INGEMMET / SIGRID-CENEPRED','document_page':f'https://sigrid4.cenepred.gob.pe/sigridv4/documento/{DOC_ID}'},'status':'starting','purpose':'Obtener controles geométricos para delinear microcuencas locales de Chosica sin confundirlas con Huaycoloro.','warning':'Coordenadas/áreas son candidatos por página y no se consideran outlets ni áreas de cuenca hasta revisar su significado.'}
 try:
  data,attempts=download();report['download_attempts']=attempts;report['download_bytes']=len(data)
  with tempfile.TemporaryDirectory(prefix='irfen_chosica_local_') as td:
   td=Path(td);pdfs=[]
   if data[:4]==b'%PDF':p=td/'source.pdf';p.write_bytes(data);pdfs=[p]
   else:
    with zipfile.ZipFile(BytesIO(data)) as z:
     for i,m in enumerate(z.namelist()):
      if m.lower().endswith('.pdf'):p=td/f'{i}.pdf';p.write_bytes(z.read(m));pdfs.append(p)
   report['files']=[]
   for p in pdfs:
    try:report['files'].append(process_pdf(p))
    except Exception as exc:report['files'].append({'error_type':type(exc).__name__,'error':str(exc)})
  report['status']='indexed_for_catchment_review' if any(f.get('text_layer_pages',0)>0 for f in report['files']) else 'downloaded_without_text_layer'
 except Exception as exc:report.update({'status':'download_or_parse_error','error_type':type(exc).__name__,'error':str(exc)})
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
