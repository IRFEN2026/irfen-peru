#!/usr/bin/env python3
"""Resolve Corrales/Rayos de Sol outlet from pre-unblind static geometry only."""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from pathlib import Path
import numpy as np
import rasterio
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'config/chosica_2015_corrales_outlet_resolution_contract_v0_1.json'
REGISTRY=ROOT/'config/chosica_2015_outlet_freeze_registry_v0_1.json'
DST='EPSG:32718'; RES=30.0; DIRMAP=(64,128,1,2,4,8,16,32)
STEPS={64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()
def tn(lat,lon):
 a,b=math.floor(lat),math.floor(lon); return f"Copernicus_DSM_COG_10_{('N' if a>=0 else 'S')+f'{abs(a):02d}'}_00_{('E' if b>=0 else 'W')+f'{abs(b):03d}'}_00_DEM"
def dl(td,bbox):
 xmin,ymin,xmax,ymax=bbox; ss=[]; prov=[]
 try:
  for a in range(math.floor(ymin),math.floor(ymax-1e-12)+1):
   for b in range(math.floor(xmin),math.floor(xmax-1e-12)+1):
    n=tn(a,b); u=f'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif'; p=td/f'{n}.tif'; r=requests.get(u,timeout=(20,180)); r.raise_for_status(); p.write_bytes(r.content); prov.append({'url':u,'sha256':sha(p),'bytes':p.stat().st_size}); ss.append(rasterio.open(p))
  arr,st=merge(ss,bounds=bbox); pr=ss[0].profile.copy(); crs=ss[0].crs
  for s in ss:s.close()
  hh,ww=arr.shape[1:]; l,bo,ri,to=array_bounds(hh,ww,st); dt,dw,dh=calculate_default_transform(crs,DST,ww,hh,l,bo,ri,to,resolution=RES); sn=pr.get('nodata'); dn=-9999. if sn is None else float(sn); dst=np.full((dh,dw),dn,dtype='float32'); reproject(source=arr[0],destination=dst,src_transform=st,src_crs=crs,src_nodata=sn,dst_transform=dt,dst_crs=DST,dst_nodata=dn,resampling=Resampling.bilinear); out=td/'dem.tif'; pr.update(driver='GTiff',width=dw,height=dh,count=1,dtype='float32',crs=DST,transform=dt,nodata=dn,compress='deflate');
  with rasterio.open(out,'w',**pr) as ds:ds.write(dst,1)
  return out,prov
 finally:
  for s in ss:
   try:s.close()
   except:pass
def center(t,r,c):return tuple(float(v) for v in rasterio.transform.xy(t,r,c,offset='center'))
def cells(t,w,h,x,y):
 inv=~t; cf,rf=inv*(x,y); r0,c0=int(math.floor(rf)),int(math.floor(cf)); rs={r0};cs={c0};e=1e-6
 if abs(rf-round(rf))<=e:rs.add(r0-1)
 if abs(cf-round(cf))<=e:cs.add(c0-1)
 return sorted((r,c) for r in rs for c in cs if 0<=r<h and 0<=c<w)
def trace(fd,start):
 rows,cols=fd.shape; cur=start; out=[]; seen=set()
 for _ in range(rows*cols):
  if cur in seen:break
  seen.add(cur);out.append(cur);r,c=cur;s=STEPS.get(int(fd[r,c]));
  if s is None:break
  nr,nc=r+s[0],c+s[1]
  if not(0<=nr<rows and 0<=nc<cols):break
  cur=(nr,nc)
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();a.report.parent.mkdir(parents=True,exist_ok=True)
 co=json.loads(CONTRACT.read_text());reg=json.loads(REGISTRY.read_text());g=co['guards'];assert g==reg['guards'];m=co['predeclared_resolution_method'];assert not any(m[k] for k in ['selection_used_basin_area','selection_used_channel_length','selection_used_rainfall','selection_used_activation_or_damage','selection_used_a6680_numeric_morphometry']); cash=reg['targets']['cashahuacra'];assert cash['outlet_status']=='FROZEN'; ox,oy=float(cash['accepted_outlet']['x_m']),float(cash['accepted_outlet']['y_m']); s=co['static_sources'];r5=(float(s['corrales_anchor']['easting_m']),float(s['corrales_anchor']['northing_m']));r4=(float(s['rimac_downstream_anchor']['easting_m']),float(s['rimac_downstream_anchor']['northing_m'])); pts=[(ox,oy),r5,r4]; tg=Transformer.from_crs(DST,'EPSG:4326',always_xy=True);ll=[tg.transform(x,y) for x,y in pts];xs=[p[0] for p in ll];ys=[p[1] for p in ll];bbox=(min(xs)-.05,min(ys)-.05,max(xs)+.05,max(ys)+.05)
 rep={'schema_version':'0.1','batch_id':reg['batch_id'],'target_id':'rayos_de_sol','drainage_id':'corrales','method':m['name'],'guards':g,'outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'contract_sha256':sha(CONTRACT),'resolver_sha256':sha(Path(__file__)),'registry_sha256':sha(REGISTRY),'accepted_outlet':None,'freeze_eligible':False,'dem_bbox_wgs84':[round(v,8) for v in bbox]}
 with tempfile.TemporaryDirectory(prefix='corrales_') as raw:
  dp,prov=dl(Path(raw),bbox);rep['dem_tiles']=prov;rep['dem_utm_sha256']=sha(dp)
  with rasterio.open(dp) as ds:t,w,h=ds.transform,ds.width,ds.height; rr,cc=ds.index(ox,oy);cx,cy=center(t,rr,cc); mapdist=math.hypot(cx-ox,cy-oy)
  tol=2*math.hypot(RES,RES);rep['frozen_cashahuacra_grid_map']={'row':rr,'col':cc,'distance_m':round(mapdist,3)};rep['identity_tolerance_m']=round(tol,6)
  if mapdist>math.hypot(RES,RES):rep['status']='PENDING_REVIEW_FROZEN_CASHAHUACRA_GRID_MAP';a.report.write_text(json.dumps(rep,indent=2)+'\n');return 0
  grid=Grid.from_raster(str(dp));dem=grid.read_raster(str(dp));dem=grid.fill_pits(dem);dem=grid.fill_depressions(dem);dem=grid.resolve_flats(dem);fd=np.asarray(grid.flowdir(dem,dirmap=DIRMAP));main=trace(fd,(rr,cc));cent=np.array([center(t,r,c) for r,c in main]);d2=(cent[:,0]-r4[0])**2+(cent[:,1]-r4[1])**2;i=int(np.argmin(d2));nd=float(math.sqrt(float(d2[i])));sd=math.hypot(cent[0,0]-r4[0],cent[0,1]-r4[1]);rep['rimac_path_diagnostic']={'trace_cells':len(main),'nearest_r4_row':main[i][0],'nearest_r4_col':main[i][1],'nearest_r4_distance_m':round(nd,3),'start_to_r4_distance_m':round(sd,3),'progresses_toward_r4':nd<sd,'within_identity_tolerance':nd<=tol}
  if not(nd<sd and nd<=tol):rep['status']='PENDING_REVIEW_CASHAHUACRA_TO_R4_MAINSTEM_NOT_REPRODUCED';a.report.write_text(json.dumps(rep,indent=2)+'\n');return 0
  path=set(main[:i+1]);starts=cells(t,w,h,*r5);rep['corrales_source_cells']=[{'row':r,'col':c} for r,c in starts];ints=[];di=[]
  for st in starts:
   tr=trace(fd,st);first=next((z for z in tr if z in path),None);di.append({'corrales_start':list(st),'status':'FIRST_INTERSECTION_FOUND' if first else 'NO_INTERSECTION',**({'row':first[0],'col':first[1]} if first else {})});
   if first:ints.append(first)
  rep['intersection_diagnostics']=di;uq=sorted(set(ints));rep['first_intersection_cells_unique']=[{'row':r,'col':c} for r,c in uq]
  if len(ints)!=len(starts):rep['status']='PENDING_REVIEW_MISSING_CORRALES_RIMAC_INTERSECTION'
  elif len(uq)!=1:rep['status']='PENDING_REVIEW_NONCONVERGENT_CORRALES_OUTLET'
  else:
   r,c=uq[0];x,y=center(t,r,c);lon,lat=tg.transform(x,y);rep['accepted_outlet']={'row':r,'col':c,'x_m':round(x,3),'y_m':round(y,3),'lon':round(lon,8),'lat':round(lat,8)};rep['status']='PASS_CORRALES_D8_MAINSTEM_INTERSECTION_CANDIDATE';rep['freeze_eligible']=True
 a.report.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rep,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
