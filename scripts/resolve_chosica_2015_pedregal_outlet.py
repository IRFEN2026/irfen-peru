#!/usr/bin/env python3
"""Resolve a pre-unblind Pedregal/San Antonio outlet from MML 2013 static anchors + D8 only."""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from pathlib import Path
from typing import Iterable
import numpy as np
import rasterio
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'config/chosica_2015_pedregal_outlet_resolution_contract_v0_1.json'
DEFAULT_REPORT=ROOT/'artifacts/chosica_2015_pedregal_outlet_report.json'
DST_CRS='EPSG:32718'; TARGET_RESOLUTION_M=30.0
D8_DIRMAP=(64,128,1,2,4,8,16,32)
D8_STEPS={64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}

def sha256_path(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()

def tile_name(lat,lon):
 a,b=math.floor(lat),math.floor(lon); return f"Copernicus_DSM_COG_10_{('N' if a>=0 else 'S')+f'{abs(a):02d}'}_00_{('E' if b>=0 else 'W')+f'{abs(b):03d}'}_00_DEM"
def relevant_tiles(xmin,ymin,xmax,ymax)->Iterable[tuple[int,int]]:
 for a in range(math.floor(ymin),math.floor(ymax-1e-12)+1):
  for b in range(math.floor(xmin),math.floor(xmax-1e-12)+1): yield a,b

def download_dem_crop(td:Path,bbox):
 srcs=[]; prov=[]
 try:
  for a,b in relevant_tiles(*bbox):
   n=tile_name(float(a),float(b)); u=f'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif'; p=td/f'{n}.tif'
   r=requests.get(u,timeout=(20,180)); r.raise_for_status(); p.write_bytes(r.content); prov.append({'url':u,'sha256':sha256_path(p),'bytes':p.stat().st_size}); srcs.append(rasterio.open(p))
  mosaic,st=merge(srcs,bounds=bbox); profile=srcs[0].profile.copy(); scrs=srcs[0].crs
  for s in srcs:s.close()
  sh,sw=mosaic.shape[1:]; left,bottom,right,top=array_bounds(sh,sw,st)
  dt,dw,dh=calculate_default_transform(scrs,DST_CRS,sw,sh,left,bottom,right,top,resolution=TARGET_RESOLUTION_M)
  sn=profile.get('nodata'); dn=-9999.0 if sn is None else float(sn); dst=np.full((dh,dw),dn,dtype='float32')
  reproject(source=mosaic[0],destination=dst,src_transform=st,src_crs=scrs,src_nodata=sn,dst_transform=dt,dst_crs=DST_CRS,dst_nodata=dn,resampling=Resampling.bilinear)
  out=td/'pedregal_rimac_dem_utm18s_30m.tif'; profile.update(driver='GTiff',width=dw,height=dh,count=1,dtype='float32',crs=DST_CRS,transform=dt,nodata=dn,compress='deflate')
  with rasterio.open(out,'w',**profile) as ds: ds.write(dst,1)
  return out,prov
 finally:
  for s in srcs:
   try:s.close()
   except Exception:pass

def center(t,r,c): return tuple(float(v) for v in rasterio.transform.xy(t,r,c,offset='center'))
def source_cells(t,w,h,x,y):
 inv=~t; cf,rf=inv*(x,y); r0,c0=int(math.floor(rf)),int(math.floor(cf)); rs={r0}; cs={c0}; eps=1e-6
 if abs(rf-round(rf))<=eps:rs.add(r0-1)
 if abs(cf-round(cf))<=eps:cs.add(c0-1)
 return sorted((r,c) for r in rs for c in cs if 0<=r<h and 0<=c<w)
def trace(fdir,start):
 rows,cols=fdir.shape; cur=start; out=[]; seen=set()
 for _ in range(rows*cols):
  if cur in seen:break
  seen.add(cur); out.append(cur); r,c=cur; s=D8_STEPS.get(int(fdir[r,c]))
  if s is None:break
  nr,nc=r+s[0],c+s[1]
  if not(0<=nr<rows and 0<=nc<cols):break
  cur=(nr,nc)
 return out

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--report',type=Path,default=DEFAULT_REPORT); args=ap.parse_args(); args.report.parent.mkdir(parents=True,exist_ok=True)
 d=json.loads(CONTRACT.read_text()); g=d['guards']; m=d['predeclared_resolution_method']
 assert g=={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}
 assert not any(m[k] for k in ['selection_used_basin_area','selection_used_channel_length','selection_used_rainfall','selection_used_activation_or_damage','selection_used_a6680_numeric_morphometry'])
 p=d['static_source']['points']; r4=p['rimac_upstream_bridge_r4']; q=p['pedregal_r7']; r9=p['rimac_downstream_bridge_r9']
 report={'schema_version':'0.1','batch_id':d['batch_id'],'target_id':'pedregal_san_antonio','method':m['name'],'guards':g,'outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'source_anchor_id':d['static_source']['source_id'],'contract_sha256':sha256_path(CONTRACT),'resolver_sha256':sha256_path(Path(__file__)),'dem_source':d['dem']['source'],'analysis_crs':DST_CRS,'target_resolution_m':30.0,'accepted_outlet':None,'freeze_eligible':False}
 togeo=Transformer.from_crs(DST_CRS,'EPSG:4326',always_xy=True); xy=[(float(r4['easting_m']),float(r4['northing_m'])),(float(q['easting_m']),float(q['northing_m'])),(float(r9['easting_m']),float(r9['northing_m']))]; ll=[togeo.transform(x,y) for x,y in xy]; lons=[x for x,y in ll]; lats=[y for x,y in ll]; bbox=(min(lons)-.05,min(lats)-.05,max(lons)+.05,max(lats)+.05); report['dem_bbox_wgs84']=[round(v,8) for v in bbox]
 with tempfile.TemporaryDirectory(prefix='irfen_pedregal_d8_') as rt:
  demp,prov=download_dem_crop(Path(rt),bbox); report['dem_tiles']=prov; report['dem_utm_sha256']=sha256_path(demp)
  with rasterio.open(demp) as ds:t,w,h=ds.transform,ds.width,ds.height; cx,cy=abs(float(t.a)),abs(float(t.e))
  grid=Grid.from_raster(str(demp)); dem=grid.read_raster(str(demp)); dem=grid.fill_pits(dem); dem=grid.fill_depressions(dem); dem=grid.resolve_flats(dem); fdir=np.asarray(grid.flowdir(dem,dirmap=D8_DIRMAP))
  r4s=source_cells(t,w,h,*xy[0]); qs=source_cells(t,w,h,*xy[1]); tol=2*math.hypot(cx,cy); report['r4_source_cells']=[{'row':r,'col':c} for r,c in r4s]; report['pedregal_source_cells']=[{'row':r,'col':c} for r,c in qs]; report['cell_size_m']=[cx,cy]; report['identity_tolerance_m']=round(tol,6)
  paths=[]; di=[]
  for st in r4s:
   tr=trace(fdir,st); cc=np.array([center(t,r,c) for r,c in tr]); d2=(cc[:,0]-xy[2][0])**2+(cc[:,1]-xy[2][1])**2; i=int(np.argmin(d2)); nd=float(math.sqrt(float(d2[i]))); sd=float(math.hypot(cc[0,0]-xy[2][0],cc[0,1]-xy[2][1])); ok=nd<sd and nd<=tol; di.append({'start':list(st),'trace_cells':len(tr),'nearest_r9_row':tr[i][0],'nearest_r9_col':tr[i][1],'nearest_r9_distance_m':round(nd,3),'start_to_r9_distance_m':round(sd,3),'progresses_toward_r9':nd<sd,'within_identity_tolerance':nd<=tol});
   if ok:paths.append(tr[:i+1])
  report['rimac_path_diagnostics']=di
  if not r4s or len(paths)!=len(r4s): report['status']='PENDING_REVIEW_R4_TO_R9_MAINSTEM_NOT_REPRODUCED'
  elif not qs: report['status']='PENDING_REVIEW_NO_PEDREGAL_SOURCE_CELL'
  else:
   ints=[]; idi=[]
   for st in qs:
    tr=trace(fdir,st)
    for pi,path in enumerate(paths):
     s=set(path); first=next((z for z in tr if z in s),None); idi.append({'pedregal_start':list(st),'rimac_path_index':pi,'status':'FIRST_INTERSECTION_FOUND' if first else 'NO_INTERSECTION',**({'row':first[0],'col':first[1]} if first else {})});
     if first:ints.append(first)
   report['intersection_diagnostics']=idi; uniq=sorted(set(ints)); report['first_intersection_cells_unique']=[{'row':r,'col':c} for r,c in uniq]
   if len(ints)!=len(qs)*len(paths):report['status']='PENDING_REVIEW_MISSING_PEDREGAL_RIMAC_INTERSECTION'
   elif len(uniq)!=1:report['status']='PENDING_REVIEW_NONCONVERGENT_PEDREGAL_OUTLET'
   else:
    r,c=uniq[0]; x,y=center(t,r,c); lon,lat=togeo.transform(x,y); report['accepted_outlet']={'row':r,'col':c,'x_m':round(x,3),'y_m':round(y,3),'lon':round(float(lon),8),'lat':round(float(lat),8)}; report['status']='PASS_PEDREGAL_D8_MAINSTEM_INTERSECTION_CANDIDATE'; report['freeze_eligible']=True
 args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(report,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
