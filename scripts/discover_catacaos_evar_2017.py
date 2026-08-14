#!/usr/bin/env python3
"""Indexa el EVAR CENEPRED 2017 específico de Catacaos.

Extrae páginas temáticas y candidatos numéricos de la capa de texto existente.
No republica el informe, no deriva un impact_score y no crea umbrales.
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json,re,tempfile,zipfile
import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/catacaos_evar_2017_discovery.json'
URL='https://sigrid.cenepred.gob.pe/sigridv3/documento/4104/descargar'
PAGE='https://sigrid.cenepred.gob.pe/sigridv3/documento/4104'
MAX_BYTES=90*1024*1024
CATEGORIES={
 'river_overflow':['desborde del río piura','desborde del rio piura','inundación fluvial','inundacion fluvial'],
 'pluvial_flood':['inundación pluvial','inundacion pluvial'],
 'very_high_risk':['riesgo muy alto'],
 'high_risk':['riesgo alto'],
 'very_high_hazard':['peligro muy alto'],
 'high_hazard':['peligro alto'],
 'population_exposure':['población expuesta','poblacion expuesta','población en riesgo','poblacion en riesgo'],
 'housing_exposure':['viviendas expuestas','viviendas en riesgo'],
 'vulnerability':['vulnerabilidad'],
 'evacuation':['evacuación','evacuacion','zona segura'],
 'flow':['m3/s','m³/s','caudal'],
 'water_depth':['tirante','altura de agua','nivel de agua']}

def norm(x):return re.sub(r'\s+',' ',x or ' ').strip()
def classify_pages(reader):
 pages={k:[] for k in CATEGORIES};texts=[]
 for i,p in enumerate(reader.pages,start=1):
  try:raw=p.extract_text() or ''
  except:raw=''
  texts.append(raw);low=raw.lower()
  for k,needles in CATEGORIES.items():
   if any(n in low for n in needles):pages[k].append(i)
 return {k:v for k,v in pages.items() if v},texts
def numeric_near(text,labels,maxv=10000000):
 low=norm(text).lower();out=[]
 for label in labels:
  for m in re.finditer(rf'{label}.{{0,100}}?(\d{{1,8}}(?:[.,]\d+)?)',low,re.I):
   try:v=float(m.group(1).replace(',','.'))
   except:continue
   if 0<v<maxv:out.append(v)
 return sorted(set(out))[:30]
def process(pdf):
 reader=PdfReader(str(pdf));page_index,texts=classify_pages(reader);alltext='\n'.join(texts);flat=norm(alltext)
 flows=[]
 for m in re.finditer(r'(\d{1,5}(?:[.,]\d+)?)\s*(?:m3/s|m³/s)',flat,re.I):
  try:v=float(m.group(1).replace(',','.'))
  except:continue
  if 0<v<20000:flows.append(v)
 return {
  'page_count':len(reader.pages),
  'text_layer_available':any(t.strip() for t in texts),
  'page_index':page_index,
  'numeric_candidates':{
   'population':numeric_near(alltext,['población expuesta','poblacion expuesta','población en riesgo','poblacion en riesgo']),
   'housing':numeric_near(alltext,['viviendas expuestas','viviendas en riesgo','viviendas']),
   'flow_m3s':sorted(set(flows))[:30]
  }
 }
def main():
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'source':{'title':'Informe de evaluación de riesgo por desborde del río Piura e inundación pluvial en el centro poblado de Catacaos','publisher':'CENEPRED','year':2017,'document_page':PAGE,'download_url':URL},'status':'starting','warning':'Páginas y números son un índice automático para revisión. No representan valores validados hasta revisar significado, escenario, unidad y población de referencia.'}
 headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'}
 r=requests.get(URL,timeout=(20,180),headers=headers);r.raise_for_status();data=r.content
 if len(data)>MAX_BYTES:raise RuntimeError('EVAR excede límite de descarga seguro')
 report['download_bytes']=len(data);report['content_type']=r.headers.get('content-type','')
 with tempfile.TemporaryDirectory(prefix='irfen_evar_') as td:
  td=Path(td);pdfs=[]
  if zipfile.is_zipfile(BytesIO(data)):
   report['container']='zip'
   with zipfile.ZipFile(BytesIO(data)) as z:
    for i,m in enumerate(z.namelist()):
     if m.lower().endswith('.pdf'):
      p=td/f'{i}.pdf';p.write_bytes(z.read(m));pdfs.append((m,p))
  elif data[:4]==b'%PDF':
   report['container']='pdf';p=td/'evar.pdf';p.write_bytes(data);pdfs=[('EVAR Catacaos 2017.pdf',p)]
  else:raise RuntimeError('Formato EVAR no reconocido')
  report['files']=[]
  for name,p in pdfs:
   try:index=process(p)
   except Exception as exc:index={'error_type':type(exc).__name__,'error':str(exc)}
   report['files'].append({'file_name':name.replace('\\','/').split('/')[-1],**index})
 report['status']='indexed_for_exposure_review' if any(f.get('text_layer_available') for f in report['files']) else 'downloaded_without_text_layer'
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':report['status'],'download_bytes':report['download_bytes'],'files':report['files']},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
