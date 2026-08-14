#!/usr/bin/env python3
"""Procesa el dataset abierto SENAMHI GBON/RBON como catálogo/control histórico.

Fuente oficial de datos abiertos: estaciones automáticas de intercambio
internacional, con variables horarias validadas incluida precipitación.
El recurso disponible está actualizado hasta 2024 y NO se trata como tiempo
real. Se descarga temporalmente y solo se guardan metadatos agregados,
estaciones y cobertura temporal/espacial relevante para IRFEN.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import io
import json
import math
import re
import requests

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
OUT=SITE/'data/stations/senamhi_open_data_catalog.json'
URLS=[
 'http://repositorio.senamhi.gob.pe/bitstream/20.500.12542/3635/3/Variables-meteorologicas-estaciones-autom%c3%a1ticas-intercambio-internacional_2024.csv',
 'https://repositorio.senamhi.gob.pe/bitstream/20.500.12542/3635/3/Variables-meteorologicas-estaciones-autom%c3%a1ticas-intercambio-internacional_2024.csv'
]
EXPECTED_CHECKSUM='4ccb872ae29d0d5da8bea5cdf6751b83'
MAX_BYTES=70*1024*1024
TARGETS={
 'san_ildefonso':(-79.0048611,-8.0531944),
 'chosica':(-76.7979167,-11.8723611),
 'catacaos':(-80.68,-5.27),
}

def norm(s):
 return re.sub(r'\s+',' ',str(s or '')).strip()
def keynorm(s):
 s=norm(s).lower()
 repl={'á':'a','é':'e','í':'i','ó':'o','ú':'u','ñ':'n','°':'','_':' '}
 for a,b in repl.items():s=s.replace(a,b)
 return re.sub(r'[^a-z0-9]+',' ',s).strip()
def hdist(lon1,lat1,lon2,lat2):
 r=6371.0088;p1,p2=math.radians(lat1),math.radians(lat2);dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1);a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*r*math.asin(math.sqrt(a))
def num(v):
 try:return float(str(v).replace(',','.'))
 except:return None
def first(row,aliases):
 normalized={keynorm(k):v for k,v in row.items()}
 for a in aliases:
  if keynorm(a) in normalized and norm(normalized[keynorm(a)])!='':return normalized[keynorm(a)]
 return None
def download():
 headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'};attempts=[]
 for url in URLS:
  try:
   r=requests.get(url,headers=headers,timeout=(12,120),allow_redirects=True)
   attempts.append({'url':url,'http_status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type'),'bytes':len(r.content)})
   if r.status_code==200 and r.content and len(r.content)<=MAX_BYTES:return r.content,attempts
  except Exception as exc:attempts.append({'url':url,'status':'error','error_type':type(exc).__name__,'error':str(exc)})
 raise RuntimeError(f'No se pudo descargar recurso SENAMHI: {attempts}')
def decode(data):
 for enc in ('utf-8-sig','utf-8','latin-1'):
  try:return data.decode(enc),enc
  except:pass
 raise UnicodeDecodeError('unknown',b'',0,1,'sin codificación compatible')
def main():
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'source':{'title':'Variables meteorológicas de las estaciones automáticas de intercambio internacional','publisher':'SENAMHI','catalog':'Plataforma Nacional de Datos Abiertos / Repositorio SENAMHI','resource_vintage':'actualizado hasta junio de 2024','use':'station_catalog_and_historical_control_only'},'status':'starting','warning':'Recurso histórico abierto; NO representa observación actual ni reemplaza IMERG.'}
 try:data,attempts=download()
 except Exception as exc:
  report.update({'status':'download_unavailable_from_github_actions','error_type':type(exc).__name__,'error':str(exc)});OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));return 0
 report['download_attempts']=attempts;report['bytes']=len(data);report['md5']=hashlib.md5(data).hexdigest();report['published_checksum_reference']=EXPECTED_CHECKSUM;report['checksum_matches_published_reference']=report['md5'].lower()==EXPECTED_CHECKSUM.lower()
 text,enc=decode(data);report['encoding']=enc
 sample=text[:10000];dialect=None
 try:dialect=csv.Sniffer().sniff(sample,delimiters=',;\t|')
 except:pass
 delimiter=dialect.delimiter if dialect else ';' if sample.count(';')>sample.count(',') else ',';report['delimiter']=delimiter
 reader=csv.DictReader(io.StringIO(text),delimiter=delimiter);report['columns']=reader.fieldnames or []
 stations={};dates=[];precip_nonempty=0;rows=0
 for row in reader:
  rows+=1
  name=first(row,['estacion','nombre estacion','station','nombre'])
  lat=num(first(row,['latitud','latitude','lat']));lon=num(first(row,['longitud','longitude','lon']))
  alt=num(first(row,['altitud','altitude','elevacion','elevation']))
  dep=first(row,['departamento','department']);prov=first(row,['provincia','province']);dist=first(row,['distrito','district']);red=first(row,['red','network'])
  precip=first(row,['precipitacion','precipitación','precipitation','pp'])
  if precip not in (None,''):precip_nonempty+=1
  dateval=first(row,['fecha','date']);timeval=first(row,['hora','time'])
  if dateval:dates.append(norm(dateval))
  if name and lat is not None and lon is not None and -90<=lat<=90 and -180<=lon<=180:
   key=(norm(name),round(lat,6),round(lon,6))
   st=stations.setdefault(key,{'name':norm(name),'lat':lat,'lon':lon,'altitude_m':alt,'department':norm(dep),'province':norm(prov),'district':norm(dist),'network':norm(red),'row_count':0,'precip_nonempty_count':0,'date_min':None,'date_max':None})
   st['row_count']+=1
   if precip not in (None,''):st['precip_nonempty_count']+=1
   if dateval:
    d=norm(dateval);st['date_min']=d if st['date_min'] is None or d<st['date_min'] else st['date_min'];st['date_max']=d if st['date_max'] is None or d>st['date_max'] else st['date_max']
 report['row_count']=rows;report['unique_station_count']=len(stations);report['rows_with_precipitation']=precip_nonempty
 stlist=sorted(stations.values(),key=lambda x:(x['name'],x['lat'],x['lon']));report['stations']=stlist
 nearest={}
 for zid,(tlon,tlat) in TARGETS.items():
  ranked=[]
  for st in stlist:
   ranked.append({**{k:st.get(k) for k in ('name','lat','lon','altitude_m','department','province','district','network','row_count','precip_nonempty_count','date_min','date_max')},'distance_km':round(hdist(tlon,tlat,st['lon'],st['lat']),2)})
  ranked.sort(key=lambda x:x['distance_km']);nearest[zid]=ranked[:8]
 report['nearest_stations']=nearest
 report['status']='catalog_available_historical_only' if stlist else 'downloaded_schema_unresolved'
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':report['status'],'bytes':report.get('bytes'),'md5':report.get('md5'),'checksum_match':report.get('checksum_matches_published_reference'),'columns':report.get('columns'),'row_count':rows,'unique_station_count':len(stlist),'nearest_stations':nearest},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
