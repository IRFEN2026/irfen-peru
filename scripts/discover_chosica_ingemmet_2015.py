#!/usr/bin/env python3
"""Indexa evidencia del informe INGEMMET del evento Chosica 23/03/2015.

Busca mediciones/estaciones de precipitación y elementos de respuesta de las
quebradas. Guarda únicamente páginas, etiquetas y tokens numéricos; no copia
el informe ni modifica umbrales.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import tempfile

import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/calibration/chosica_ingemmet_2015_index.json'
URL='https://repositorio.ingemmet.gob.pe/bitstream/20.500.12544/2265/1/Villacorta-Evaluacion_geodinamica_flujos_de_detritos_23-03-15.pdf'
MAX_BYTES=35*1024*1024

CATEGORIES={
 'event_date':['23 de marzo','23/03/2015','23-03-2015','marzo de 2015'],
 'rainfall':['precipitación','precipitacion','lluvia','pluvial'],
 'station':['estación','estacion','pluviómetro','pluviometro','senamhi'],
 'pedregal':['pedregal'],
 'quiro':['quirio'],
 'libertad':['la libertad'],
 'corrales':['corrales'],
 'carosio':['carosio'],
 'debris_flow':['flujo de detritos','huaico','huayco'],
 'antecedent':['antecedente','acumulada','acumulado','días anteriores','dias anteriores'],
}

def norm(x):return re.sub(r'\s+',' ',x or '').strip()
def mm_tokens(text):
 vals=[]
 patterns=[r'(?<!\d)(\d{1,4}(?:[.,]\d{1,3})?)\s*mm(?:\s*/\s*(?:h|día|dia|hora))?',r'(?<!\d)(\d{1,4}(?:[.,]\d{1,3})?)\s*mil[ií]metros?']
 for pat in patterns:
  for m in re.finditer(pat,text,re.I):
   token=m.group(1)
   if token not in vals:vals.append(token)
 return vals[:100]
def date_tokens(text):
 vals=[]
 for pat in (r'\b\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}\b',r'\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(?:19|20)\d{2}\b'):
  for m in re.finditer(pat,text,re.I):
   v=norm(m.group(0))
   if v not in vals:vals.append(v)
 return vals[:100]
def download(headers):
 r=requests.get(URL,headers=headers,timeout=(20,180),stream=True)
 r.raise_for_status();return r

def main():
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'source':{'title':'Evaluación geodinámica de los flujos de detritos del 23 de marzo del 2015 en Chosica','publisher':'INGEMMET','year':2015,'download_url':URL},'purpose':'Buscar evidencia pluviométrica terrestre del evento usado en el replay de Chosica.','status':'starting','page_index':{},'measurement_candidates':[],'event_pages':[],'warning':'Tokens numéricos requieren validar estación, periodo y unidad antes de compararlos con IMERG.'}
 try:
  headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'};r=download(headers)
  with tempfile.TemporaryDirectory(prefix='irfen_ingemmet_chosica_') as td:
   pdf=Path(td)/'chosica_ingemmet_2015.pdf';total=0
   with pdf.open('wb') as f:
    for chunk in r.iter_content(chunk_size=1024*1024):
     if not chunk:continue
     total+=len(chunk)
     if total>MAX_BYTES:raise RuntimeError('PDF excede límite seguro')
     f.write(chunk)
   report['download_bytes']=total;reader=PdfReader(str(pdf));report['page_count']=len(reader.pages);hits={k:[] for k in CATEGORIES};measures=[];event_pages=[];text_pages=0
   for pageno,page in enumerate(reader.pages,start=1):
    try:raw=page.extract_text() or ''
    except:raw=''
    if not raw.strip():continue
    text_pages+=1;low=raw.lower();cats=[]
    for key,needles in CATEGORIES.items():
     if any(n in low for n in needles):hits[key].append(pageno);cats.append(key)
    if 'event_date' in cats or ({'rainfall','debris_flow'}<=set(cats)):event_pages.append(pageno)
    for token in mm_tokens(raw):measures.append({'page':pageno,'value_text':token,'unit':'mm_or_mm_rate_unresolved','page_categories':sorted(cats),'validated_station':False,'validated_period':False})
   report['text_layer_pages']=text_pages;report['page_index']={k:{'pages':v,'page_count':len(v)} for k,v in hits.items() if v};report['event_pages']=sorted(set(event_pages));report['measurement_candidates']=measures[:250]
   report['event_pages_with_station_and_rainfall']=sorted(set(hits.get('event_date',[])) & set(hits.get('station',[])) & set(hits.get('rainfall',[])))
   report['event_pages_with_mm_tokens']=sorted({m['page'] for m in measures} & set(event_pages))
   report['status']='indexed_for_calibration_review' if text_pages else 'downloaded_without_text_layer'
 except Exception as exc:
  report.update({'status':'download_or_parse_error','error_type':type(exc).__name__,'error':str(exc)})
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':report['status'],'download_bytes':report.get('download_bytes'),'page_count':report.get('page_count'),'event_pages':report.get('event_pages'),'event_pages_with_station_and_rainfall':report.get('event_pages_with_station_and_rainfall'),'event_pages_with_mm_tokens':report.get('event_pages_with_mm_tokens'),'measurement_candidates':report.get('measurement_candidates')},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
