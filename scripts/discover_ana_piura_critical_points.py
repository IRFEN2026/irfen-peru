#!/usr/bin/env python3
"""Descubre fichas ANA 2026 de puntos críticos relevantes para Catacaos/Bajo Piura.

Descarga temporalmente paquetes oficiales SIGRID y usa únicamente la capa de
texto disponible en los PDFs para extraer metadatos estructurados. No usa OCR,
no republica fichas y no convierte referencias en alertas o umbrales.
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json,re,tempfile,zipfile
import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/ana_piura_critical_points_2026.json'
MAX_DOWNLOAD=120*1024*1024
DOCUMENTS=[
 {'id':21411,'url':'https://sigrid.cenepred.gob.pe/sigridv3/documento/21411/descargar?boletin=578','office':'0127-2026-ANA-J'},
 {'id':22176,'url':'https://sigrid.cenepred.gob.pe/sigridv3/documento/22176/descargar','office':'0774-2026-ANA-J'},
 {'id':22191,'url':'https://sigrid.cenepred.gob.pe/sigridv3/documento/22191/descargar','office':'0788-2026-ANA-J'}]
TERRITORY={'catacaos':['catacaos'],'la_legua':['la legua'],'simbila':['simbilá','simbila'],'pedregal_grande':['pedregal grande'],'cura_mori':['cura mori'],'bajo_piura':['bajo piura'],'rio_piura':['río piura','rio piura']}
INTERVENTIONS={'descolmatacion':['descolmatación','descolmatacion'],'enrocado':['enrocado'],'dique':['dique'],'defensa_riberena':['defensa ribereña','defensa riberena'],'limpieza_cauce':['limpieza de cauce','limpieza del cauce'],'encauzamiento':['encauzamiento'],'reforestacion':['reforestación','reforestacion']}
HAZARDS={'inundacion':['inundación','inundacion'],'erosion_fluvial':['erosión fluvial','erosion fluvial'],'desborde':['desborde'],'socavacion':['socavación','socavacion']}

def clean_name(name):return name.replace('\\','/').split('/')[-1]
def norm(text):return re.sub(r'\s+',' ',text or ' ').strip()
def download(url,headers):
 r=requests.get(url,timeout=(20,150),headers=headers);r.raise_for_status();data=r.content
 if len(data)>MAX_DOWNLOAD:raise RuntimeError(f'Descarga excede límite de {MAX_DOWNLOAD} bytes')
 return data,r.headers.get('content-type','')
def relevant_from_name(name):
 low=name.lower();return sorted(k for k,needles in TERRITORY.items() if any(n in low for n in needles))
def classify(text,groups):
 low=text.lower();return sorted(k for k,needles in groups.items() if any(n in low for n in needles))
def unique(values):
 out=[]
 for v in values:
  v=norm(v).strip(' :-–—,.;')
  if v and v.lower() not in {x.lower() for x in out}:out.append(v)
 return out

def labeled_values(raw,label,maxlen=100):
 pats=[rf'(?im)^\s*{label}\s*[:\-]?\s*([^\n]{{2,{maxlen}}})',rf'(?i){label}\s*[:\-]\s*([^;,.]{{2,{maxlen}}})']
 vals=[]
 for pat in pats:
  for m in re.finditer(pat,raw):vals.append(m.group(1))
 return unique(vals)[:8]
def number_candidates(text,words,unit_words=()):
 low=text.lower();out=[]
 for word in words:
  for m in re.finditer(rf'{word}.{{0,90}}?(\d{{1,7}}(?:[.,]\d+)?)',low,re.I):
   val=m.group(1).replace(',','.')
   try:n=float(val)
   except:continue
   if 0<n<10000000:out.append(n)
 return sorted(set(out))[:12]
def coordinate_candidates(text):
 out=[]
 patterns=[
  r'(?i)(?:este|easting|utm\s*e|coordenada\s*e)\D{0,20}(\d{5,7}(?:[.,]\d+)?)\D{0,80}(?:norte|northing|utm\s*n|coordenada\s*n)\D{0,20}(\d{6,8}(?:[.,]\d+)?)',
  r'\b(\d{6})\s*(?:m\s*)?[Ee]\b.{0,80}?\b(\d{7})\s*(?:m\s*)?[Nn]\b']
 for pat in patterns:
  for m in re.finditer(pat,text,re.S):
   try:e=float(m.group(1).replace(',','.'));n=float(m.group(2).replace(',','.'))
   except:continue
   if 100000<=e<=900000 and 8000000<=n<=10000000:out.append({'easting':e,'northing':n,'crs':'UTM zone not yet confirmed'})
 ded=[];seen=set()
 for x in out:
  k=(x['easting'],x['northing'])
  if k not in seen:seen.add(k);ded.append(x)
 return ded[:12]
def extract_pdf(path):
 try:reader=PdfReader(str(path))
 except Exception:return {'page_count':0,'text_layer_available':False,'territory_page_hits':{},'structured':{}}
 page_hits={k:[] for k in TERRITORY};raw_pages=[]
 for pageno,page in enumerate(reader.pages,start=1):
  try:raw=page.extract_text() or ''
  except:raw=''
  if not raw.strip():continue
  raw_pages.append(raw);low=raw.lower()
  for k,needles in TERRITORY.items():
   if any(n in low for n in needles):page_hits[k].append(pageno)
 raw='\n'.join(raw_pages);text=norm(raw);low=text.lower()
 structured={
  'district_candidates':labeled_values(raw,r'distrito'),
  'province_candidates':labeled_values(raw,r'provincia'),
  'sector_candidates':unique(labeled_values(raw,r'sector')+labeled_values(raw,r'centro\s+poblado')+labeled_values(raw,r'localidad'))[:12],
  'hazard_tags':classify(text,HAZARDS),
  'intervention_tags':classify(text,INTERVENTIONS),
  'utm_candidates':coordinate_candidates(raw),
  'population_number_candidates':number_candidates(text,['población','poblacion','habitantes']),
  'housing_number_candidates':number_candidates(text,['viviendas','vivienda']),
  'flow_m3s_candidates':[]}
 for m in re.finditer(r'(\d{1,5}(?:[.,]\d+)?)\s*(?:m3/s|m³/s)',text,re.I):
  try:v=float(m.group(1).replace(',','.'))
  except:continue
  if 0<v<20000:structured['flow_m3s_candidates'].append(v)
 structured['flow_m3s_candidates']=sorted(set(structured['flow_m3s_candidates']))[:12]
 structured={k:v for k,v in structured.items() if v}
 return {'page_count':len(reader.pages),'text_layer_available':bool(raw_pages),'territory_page_hits':{k:v for k,v in page_hits.items() if v},'structured':structured}
def process_pdf(path,doc,member_name=None):
 parsed=extract_pdf(path);name=member_name or path.name;name_hits=relevant_from_name(name);hits=parsed['territory_page_hits'];relevant=bool(hits or name_hits)
 return {'source_document_id':doc['id'],'office':doc['office'],'source_page':f"https://sigrid.cenepred.gob.pe/sigridv3/documento/{doc['id']}",'file_name':clean_name(name),'page_count':parsed['page_count'],'text_layer_available':parsed['text_layer_available'],'territory_hits_from_filename':name_hits,'territory_page_hits':hits,'structured':parsed['structured'],'relevant_to_catacaos_model':relevant,'production_use':False}
def main():
 headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'}
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'status':'starting','purpose':'Descubrir fichas ANA 2026 relacionadas con Catacaos/Bajo Piura y estructurar metadatos sin asumir que todo punto crítico de Piura afecta Catacaos.','documents':[],'relevant_files':[],'warning':'Campos numéricos son candidatos extraídos automáticamente y requieren revisión de significado/unidad/ubicación antes de uso científico u operativo.'}
 with tempfile.TemporaryDirectory(prefix='irfen_ana_piura_') as td:
  work=Path(td)
  for doc in DOCUMENTS:
   item={'document_id':doc['id'],'office':doc['office'],'download_url':doc['url']}
   try:
    data,ctype=download(doc['url'],headers);item.update({'download_bytes':len(data),'content_type':ctype,'files':[]})
    if zipfile.is_zipfile(BytesIO(data)):
     item['container']='zip'
     with zipfile.ZipFile(BytesIO(data)) as z:
      members=[m for m in z.namelist() if not m.endswith('/')];item['member_count']=len(members)
      for idx,member in enumerate(members):
       name=clean_name(member);item['files'].append({'file_name':name,'extension':Path(name).suffix.lower(),'territory_hits_from_filename':relevant_from_name(name)})
       if Path(name).suffix.lower()!='.pdf':continue
       p=work/f"{doc['id']}_{idx}.pdf";p.write_bytes(z.read(member));result=process_pdf(p,doc,member)
       if result['relevant_to_catacaos_model']:report['relevant_files'].append(result)
    elif data[:4]==b'%PDF':
     item['container']='pdf';p=work/f"{doc['id']}.pdf";p.write_bytes(data);result=process_pdf(p,doc);item['files'].append({'file_name':p.name,'extension':'.pdf'})
     if result['relevant_to_catacaos_model']:report['relevant_files'].append(result)
    else:item.update({'container':'unknown','error':'Formato descargado no reconocido como ZIP/PDF'})
   except Exception as exc:item.update({'status':'error','error_type':type(exc).__name__,'error':str(exc)})
   else:item['status']='processed'
   report['documents'].append(item)
 report['status']='discovered' if report['relevant_files'] else 'processed_no_catacaos_match_yet';report['relevant_file_count']=len(report['relevant_files'])
 report['territory_summary']={k:sum(1 for f in report['relevant_files'] if k in f.get('territory_page_hits',{}) or k in f.get('territory_hits_from_filename',[])) for k in TERRITORY}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':report['status'],'relevant_file_count':report['relevant_file_count'],'territory_summary':report['territory_summary'],'relevant_files':[{'file':f['file_name'],'doc':f['source_document_id'],'hits':f['territory_page_hits'],'structured':f['structured']} for f in report['relevant_files']]},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
