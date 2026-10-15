#!/usr/bin/env python3
"""Resolve La Libertad outlet from frozen ANA RD2059 bank geometry + D8 only."""
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
CONTRACT=ROOT/'config/chosica_2015_la_libertad_outlet_resolution_contract_v0_1.json'
DST='EPSG:32718'; RES=30.0; DIRMAP=(64,128,1,2,4,8,16,32)
STEPS={64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()
def tile_name(lat,lon):
 a,b=math.floor(lat),math.floor(lon);return f"Copernicus_DSM_COG_10_{('N' if a>=0 else 'S')+f'{abs(a):02d}'}_00_{('E' if b>=0 else 'W')+f'{abs(b):03d}'}_00_DEM"
def tiles(b):
 xmin,ymin,xmax,ymax=b
 for a in range(math.floor(ymin),math.floor(ymax-1e-12)+1):
  for z in range(math.floor(xmin),math.floor(xmax-1e-12)+1):yield a,z
def download_dem(td,bbox):
 srcs=[];prov=[]
 try:
  for a,b in tiles(bbox):
   n=tile_name(a,b);u=f'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif';p=td/f'{n}.tif';r=requests.get(u,timeout=(20,180));r.raise_for_status();p.write_bytes(r.content);prov.append({'url':u,'sha256':sha(p),'bytes':p.stat().st_size});srcs.append(rasterio.open(p))
  arr,st=merge(srcs,bounds=bbox);pr=srcs[0].profile.copy();crs=srcs[0].crs
  for s in srcs:s.close()
  h,w=arr.shape[1:];l,bo,ri,to=array_bounds(h,w,st);dt,dw,dh=calculate_default_transform(crs,DST,w,h,l,bo,ri,to,resolution=RES);sn=pr.get('nodata');dn=-9999. if sn is None else float(sn);dst=np.full((dh,dw),dn,dtype='float32');reproject(source=arr[0],destination=dst,src_transform=st,src_crs=crs,src_nodata=sn,dst_transform=dt,dst_crs=DST,dst_nodata=dn,resampling=Resampling.bilinear);out=td/'dem.tif';pr.update(driver='GTiff',width=dw,height=dh,count=1,dtype='float32',crs=DST,transform=dt,nodata=dn,compress='deflate')
  with rasterio.open(out,'w',**pr) as ds:ds.write(dst,1)
  return out,prov
 finally:
  for s in srcs:
   try:s.close()
   except:pass
def center(t,r,c):return tuple(float(v) for v in rasterio.transform.xy(t,r,c,offset='center'))
def source_cells(t,w,h,x,y):
 inv=~t;cf,rf=inv*(x,y);r0,c0=int(math.floor(rf)),int(math.floor(cf));rs={r0};cs={c0};eps=1e-6
 if abs(rf-round(rf))<=eps:rs.add(r0-1)
 if abs(cf-round(cf))<=eps:cs.add(c0-1)
 return sorted((r,c) for r in rs for c in cs if 0<=r<h and 0<=c<w)
def trace(fd,start):
 rows,cols=fd.shape;cur=start;seen=set();out=[]
 for _ in range(rows*cols):
  if cur in seen:break
  seen.add(cur);out.append(cur);r,c=cur;s=STEPS.get(int(fd[r,c]))
  if s is None:break
  nr,nc=r+s[0],c+s[1]
  if not(0<=nr<rows and 0<=nc<cols):break
  cur=(nr,nc)
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);args=ap.parse_args();args.report.parent.mkdir(parents=True,exist_ok=True)
 c=json.loads(CONTRACT.read_text());g=c['guards'];m=c['predeclared_resolution_method'];assert g=={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False};assert not any(m[k] for k in ['target_basin_area_used_for_selection','published_channel_length_used_for_selection','published_slope_used_for_selection','published_source_elevation_used_for_selection','rainfall_used_for_selection','territorial_activation_evidence_used','a6680_numeric_morphometry_used'])
 a=c['static_channel_anchors'];up=a['upstream_centerline_midpoint'];dn=a['downstream_centerline_midpoint'];ux,uy=float(up['easting_m']),float(up['northing_m']);dx,dy=float(dn['easting_m']),float(dn['northing_m']);to_ll=Transformer.from_crs(DST,'EPSG:4326',always_xy=True);ulon,ulat=to_ll.transform(ux,uy);dlon,dlat=to_ll.transform(dx,dy);margin=.08;bbox=(min(ulon,dlon)-margin,min(ulat,dlat)-margin,max(ulon,dlon)+margin,max(ulat,dlat)+margin)
 rep={'schema_version':'0.1','batch_id':c['batch_id'],'target_id':'la_libertad','status':'PENDING_REVIEW_NOT_RUN','method':m['name'],'guards':g,'outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'vulnerability_inventory_read':False,'source_anchor_id':c['source_admissibility']['source_id'],'source_role':c['source_admissibility']['source_role'],'contract_sha256':sha(CONTRACT),'resolver_sha256':sha(Path(__file__)),'dem_source':'Copernicus DEM GLO-30 Public','analysis_crs':DST,'target_resolution_m':RES,'dem_bbox_wgs84':[round(v,8) for v in bbox],'accepted_outlet':None,'freeze_eligible':False}
 with tempfile.TemporaryDirectory(prefix='libertad_d8_') as raw:
  dp,prov=download_dem(Path(raw),bbox);rep['dem_tiles']=prov;rep['dem_utm_sha256']=sha(dp)
  with rasterio.open(dp) as ds:t,w,h=ds.transform,ds.width,ds.height;cellx,celly=abs(float(t.a)),abs(float(t.e))
  grid=Grid.from_raster(str(dp));dem=grid.read_raster(str(dp));dem=grid.fill_pits(dem);dem=grid.fill_depressions(dem);dem=grid.resolve_flats(dem);fd=np.asarray(grid.flowdir(dem,dirmap=DIRMAP));starts=source_cells(t,w,h,ux,uy);rep['upstream_source_cells']=[{'row':r,'col':cc} for r,cc in starts];diags=[];sels=[]
  for st in starts:
   tr=trace(fd,st)
   if not tr:diags.append({'start':list(st),'status':'NO_TRACE'});continue
   cs=np.array([center(t,r,cc) for r,cc in tr]);d2=(cs[:,0]-dx)**2+(cs[:,1]-dy)**2;i=int(np.argmin(d2));sel=tr[i];dist=float(math.sqrt(float(d2[i])));startdist=float(math.hypot(cs[0,0]-dx,cs[0,1]-dy));sels.append(sel);diags.append({'start':list(st),'trace_cells':len(tr),'selected_row':sel[0],'selected_col':sel[1],'selected_x_m':round(float(cs[i,0]),3),'selected_y_m':round(float(cs[i,1]),3),'nearest_downstream_midpoint_distance_m':round(dist,3),'start_to_downstream_midpoint_distance_m':round(startdist,3),'progresses_toward_downstream_midpoint':dist<startdist})
  rep['trace_diagnostics']=diags;uq=sorted(set(sels));rep['selected_cells_unique']=[{'row':r,'col':cc} for r,cc in uq];tol=2*math.hypot(cellx,celly);rep['cell_size_m']=[cellx,celly];rep['identity_tolerance_m']=round(tol,6)
  if not starts or not sels:rep['status']='PENDING_REVIEW_NO_D8_TRACE'
  elif len(sels)!=len(starts):rep['status']='PENDING_REVIEW_INCOMPLETE_SOURCE_CELL_TRACES'
  elif len(uq)!=1:rep['status']='PENDING_REVIEW_NONCONVERGENT_SOURCE_CELLS'
  else:
   sel=uq[0];sel_di=[d for d in diags if d.get('selected_row')==sel[0] and d.get('selected_col')==sel[1]];mx=max(float(d['nearest_downstream_midpoint_distance_m']) for d in sel_di);progress=all(bool(d['progresses_toward_downstream_midpoint']) for d in sel_di)
   if not progress:rep['status']='PENDING_REVIEW_TRACE_DOES_NOT_PROGRESS'
   elif mx>tol:rep['status']='PENDING_REVIEW_DOWNSTREAM_IDENTITY_TOLERANCE'
   else:
    x,y=center(t,*sel);lon,lat=to_ll.transform(x,y);rep['accepted_outlet']={'row':sel[0],'col':sel[1],'x_m':round(x,3),'y_m':round(y,3),'lon':round(lon,8),'lat':round(lat,8),'distance_to_ana_0_000_centerline_midpoint_m':round(mx,3)};rep['status']='PASS_LA_LIBERTAD_D8_IDENTITY_CANDIDATE';rep['freeze_eligible']=True
 args.report.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(rep,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
