#!/usr/bin/env python3
"""Genera conjuntos de microcuencas candidatas DEM para quebradas locales de Chosica.

Usa semillas auxiliares OSM únicamente como aproximación de ubicación. Para no
confundir tributarios con el cauce principal del Rímac, genera varios candidatos
en bandas de área y nunca asigna PASS. La selección final requiere evidencia
oficial independiente de outlet/área/recorrido.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json, math, tempfile

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.features import shapes
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union
from pyproj import Geod
import requests
from pysheds.grid import Grid

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
SEEDS=SITE/'data/calibration/chosica_osm_search_seeds.json'
CONTROLS=SITE/'data/calibration/chosica_local_geometry_controls.json'
OUT=SITE/'data/watersheds/chosica_local_candidate_sets.geojson'
REPORT=SITE/'data/watersheds/chosica_local_candidate_sets_validation.json'
BANDS=[(0.5,3),(3,8),(8,20),(20,50),(50,100)]
MAX_SEED_DISTANCE_KM=4.0
GEOD=Geod(ellps='WGS84')

def load(path,default=None):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except Exception:return default

def tile_name(lat,lon):
 latp=('N' if lat>=0 else 'S')+f'{abs(int(lat)):02d}'
 lonp=('E' if lon>=0 else 'W')+f'{abs(int(lon)):03d}'
 return f'Copernicus_DSM_COG_10_{latp}_00_{lonp}_00_DEM'
def tile_url(lat,lon):
 name=tile_name(lat,lon);return f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'
def hkm(a,b):
 lon1,lat1=a;lon2,lat2=b;r=6371.0088;p1,p2=math.radians(lat1),math.radians(lat2);dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1);x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*r*math.asin(math.sqrt(x))
def geod_area_km2(g):
 a,_=GEOD.geometry_area_perimeter(g);return abs(a)/1e6
def polygonize(mask,transform):
 geoms=[shape(g) for g,v in shapes(mask.astype('uint8'),mask=mask.astype(bool),transform=transform) if int(v)==1]
 return unary_union(geoms).buffer(0) if geoms else None

def main():
 seeds=load(SEEDS,{}) or {};controls=load(CONTROLS,{}) or {}
 selected={}
 for q,info in (seeds.get('targets') or {}).items():
  candidates=info.get('candidates') or []
  if not candidates:continue
  preferred=next((x for x in candidates if x.get('waterway')),candidates[0])
  p=preferred.get('candidate_connection_point') or {}
  if p.get('lon') is None or p.get('lat') is None:continue
  selected[q]={'lon':float(p['lon']),'lat':float(p['lat']),'osm':preferred}
 report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'status':'starting','authority':'candidate_set_only','source_dem':'Copernicus DEM GLO-30 Public','search_seed_source':'OpenStreetMap — non-authoritative search seed only','area_bands_km2':[list(x) for x in BANDS],'max_seed_distance_km':MAX_SEED_DISTANCE_KM,'targets':{},'warning':'Ningún polígono de este archivo es una microcuenca validada. Solo sirve para comparar candidatos y localizar la necesidad de un control oficial de outlet/área.'}
 if not selected:
  report['status']='no_search_seeds_available';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps({'type':'FeatureCollection','properties':{'production_use':False},'features':[]},indent=2),encoding='utf-8');REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return 0
 lons=[x['lon'] for x in selected.values()];lats=[x['lat'] for x in selected.values()];xmin,xmax=min(lons)-.18,max(lons)+.18;ymin,ymax=min(lats)-.18,max(lats)+.18
 features=[]
 with tempfile.TemporaryDirectory(prefix='irfen_chosica_dem_') as td:
  td=Path(td);srcs=[]
  for lat in range(math.floor(ymin),math.floor(ymax)+1):
   for lon in range(math.floor(xmin),math.floor(xmax)+1):
    url=tile_url(lat,lon);path=td/f'{tile_name(lat,lon)}.tif'
    try:
     r=requests.get(url,timeout=(15,90));r.raise_for_status();path.write_bytes(r.content);srcs.append(rasterio.open(path))
    except Exception as exc:report.setdefault('tile_errors',[]).append({'url':url,'error':str(exc)})
  if not srcs:
   report['status']='dem_download_failed';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps({'type':'FeatureCollection','properties':{'production_use':False},'features':[]},indent=2),encoding='utf-8');REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return 0
  mosaic,transform=merge(srcs,bounds=(xmin,ymin,xmax,ymax));profile=srcs[0].profile.copy();profile.update(height=mosaic.shape[1],width=mosaic.shape[2],transform=transform,count=1)
  for s in srcs:s.close()
  dempath=td/'dem.tif'
  with rasterio.open(dempath,'w',**profile) as dst:dst.write(mosaic[0],1)
  grid=Grid.from_raster(str(dempath));dem=grid.read_raster(str(dempath));dem=grid.fill_pits(dem);dem=grid.fill_depressions(dem);dem=grid.resolve_flats(dem);fdir=grid.flowdir(dem);acc=grid.accumulation(fdir)
  arr=np.asarray(acc,dtype=float);rows,cols=arr.shape
  # Approx area per 30m cell. Used only to bin candidates, final polygon area is geodesic.
  cell_km2=0.0009
  for q,seed in selected.items():
   qrows=[]
   for lo,hi in BANDS:
    mask=(arr*cell_km2>=lo)&(arr*cell_km2<hi)
    rr,cc=np.where(mask)
    if not len(rr):continue
    xs=transform.c+(cc+.5)*transform.a+(rr+.5)*transform.b;ys=transform.f+(cc+.5)*transform.d+(rr+.5)*transform.e
    d=np.array([hkm((float(x),float(y)),(seed['lon'],seed['lat'])) for x,y in zip(xs,ys)])
    idx=int(np.argmin(d));dist=float(d[idx])
    if dist>MAX_SEED_DISTANCE_KM:continue
    r0,c0=int(rr[idx]),int(cc[idx]);x=float(xs[idx]);y=float(ys[idx]);approx=float(arr[r0,c0]*cell_km2)
    try:catch=grid.catchment(x=x,y=y,fdir=fdir,xytype='coordinate');catch_mask=np.asarray(catch,dtype=bool);geom=polygonize(catch_mask,transform)
    except Exception as exc:qrows.append({'band_km2':[lo,hi],'status':'catchment_error','error':str(exc)});continue
    if geom is None or geom.is_empty:continue
    area=geod_area_km2(geom)
    props={'id':f'{q}_{lo}_{hi}','hazard_subsystem':'chosica_local_debris_flows','quebrada_search_name':q,'candidate_status':'REVIEW_ONLY','production_ready':False,'production_use':False,'seed_authority':'OSM_search_seed_only','seed_lon':seed['lon'],'seed_lat':seed['lat'],'snapped_lon':round(x,7),'snapped_lat':round(y,7),'seed_to_snap_km':round(dist,3),'accumulation_area_approx_km2':round(approx,3),'delineated_area_km2':round(area,3),'area_band_km2':[lo,hi],'official_outlet_validated':False,'official_area_validated':False}
    features.append({'type':'Feature','properties':props,'geometry':mapping(geom)});qrows.append({k:props[k] for k in ('id','candidate_status','seed_to_snap_km','accumulation_area_approx_km2','delineated_area_km2','area_band_km2')})
   report['targets'][q]={'search_seed':seed,'official_controls_summary':(controls.get('summary') or {}).get(q),'candidate_count':len([f for f in features if f['properties']['quebrada_search_name']==q]),'candidates':qrows,'decision':'REVIEW — official outlet/area evidence still required'}
 report['status']='candidate_sets_built' if features else 'no_dem_candidates_passed_search_constraints';report['feature_count']=len(features)
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps({'type':'FeatureCollection','properties':{'version':'0.8-experimental','production_use':False,'warning':report['warning']},'features':features},ensure_ascii=False,indent=2),encoding='utf-8');REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':report['status'],'feature_count':len(features),'targets':report['targets']},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
