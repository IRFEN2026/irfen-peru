#!/usr/bin/env python3
"""Obtiene semillas de búsqueda OSM para quebradas locales de Chosica.

OSM se usa SOLO para localizar nombres/trazas y aproximar la conexión al Rímac.
No es fuente de validación científica ni operativa. Los puntos resultantes deben
ser ajustados al DEM y contrastados con evidencia oficial antes de delinear.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, math, requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/calibration/chosica_osm_search_seeds.json'
OVERPASS='https://overpass-api.de/api/interpreter'
BBOX='-12.10,-77.05,-11.70,-76.55'
TARGETS={'rayos_de_sol':['Rayos de Sol'],'quirio':['Quirio'],'pedregal':['Pedregal','San Antonio de Pedregal']}

def hkm(a,b):
 lon1,lat1=a;lon2,lat2=b;r=6371.0088;p1,p2=math.radians(lat1),math.radians(lat2);dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1);x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*r*math.asin(math.sqrt(x))
def overpass(query):
 r=requests.post(OVERPASS,data={'data':query},headers={'User-Agent':'IRFEN-research/0.8'},timeout=(10,70));r.raise_for_status();return r.json()
def coords(el):
 return [(float(p['lon']),float(p['lat'])) for p in el.get('geometry',[]) if 'lon' in p and 'lat' in p]
def main():
 q=f'''[out:json][timeout:45];(
 way[waterway][name~"R[ií]mac|Rimac",i]({BBOX});
 way[waterway][name~"Rayos de Sol|Quirio|Pedregal|San Antonio",i]({BBOX});
 node[name~"Rayos de Sol|Quirio|Pedregal|San Antonio",i]({BBOX});
 way[name~"Rayos de Sol|Quirio|Pedregal|San Antonio",i]({BBOX});
 );out geom tags;'''
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'authority':'non_authoritative_search_seed_only','source':'OpenStreetMap Overpass','status':'starting','warning':'OSM no valida outlets ni cuencas. Se usa únicamente para generar semillas que después deben ajustarse al DEM y validarse contra fuentes oficiales.','targets':{}}
 try:data=overpass(q)
 except Exception as exc:
  report.update({'status':'access_error','error_type':type(exc).__name__,'error':str(exc)});OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return 0
 elements=data.get('elements',[]);rimac=[]
 for e in elements:
  name=str((e.get('tags') or {}).get('name','')).lower()
  if 'rimac' in name or 'rímac' in name:
   rimac.extend(coords(e))
 for key,names in TARGETS.items():
  candidates=[]
  for e in elements:
   tags=e.get('tags') or {};name=str(tags.get('name',''))
   if not any(n.lower() in name.lower() for n in names):continue
   cs=coords(e)
   if not cs and e.get('type')=='node' and 'lon' in e:cs=[(float(e['lon']),float(e['lat']))]
   if not cs:continue
   endpoints=[cs[0],cs[-1]] if len(cs)>1 else cs
   chosen=min(endpoints,key=lambda p:min((hkm(p,r) for r in rimac),default=999))
   d=min((hkm(chosen,r) for r in rimac),default=None)
   candidates.append({'osm_type':e.get('type'),'osm_id':e.get('id'),'name':name,'waterway':tags.get('waterway'),'candidate_connection_point':{'lon':round(chosen[0],7),'lat':round(chosen[1],7)},'distance_to_osm_rimac_km':None if d is None else round(d,3),'search_seed_only':True})
  candidates.sort(key=lambda x:(x['distance_to_osm_rimac_km'] is None,x['distance_to_osm_rimac_km'] or 999))
  report['targets'][key]={'candidate_count':len(candidates),'candidates':candidates[:10],'ready_for_dem_snap':bool(candidates),'scientific_validation':False}
 report['status']='search_seeds_available' if any(v['candidate_count'] for v in report['targets'].values()) else 'no_named_osm_candidates'
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':report['status'],'targets':report['targets']},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
