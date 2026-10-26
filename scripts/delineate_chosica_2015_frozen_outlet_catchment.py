#!/usr/bin/env python3
"""Generic pre-unblind D8 catchment delineator for a frozen outlet.

Contract-driven and fail-closed. The algorithm may be reused only after a target-specific
geometry contract is frozen. It reads no outcome, rainfall, A6680 numeric morphometry,
or target basin-size information.
"""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from pathlib import Path
import numpy as np
import rasterio
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT=Path(__file__).resolve().parents[1]; DST='EPSG:32718'; RES=30.0; D8=(64,128,1,2,4,8,16,32)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()
def tname(lat,lon):
 a,b=math.floor(lat),math.floor(lon);return f"Copernicus_DSM_COG_10_{('N' if a>=0 else 'S')+f'{abs(a):02d}'}_00_{('E' if b>=0 else 'W')+f'{abs(b):03d}'}_00_DEM"
def build(td,bbox,expected):
 xmin,ymin,xmax,ymax=bbox; ss=[];prov=[]
 try:
  for a in range(math.floor(ymin),math.floor(ymax-1e-12)+1):
   for b in range(math.floor(xmin),math.floor(xmax-1e-12)+1):
    n=tname(a,b);u=f'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif';p=td/f'{n}.tif';r=requests.get(u,timeout=(20,180));r.raise_for_status();p.write_bytes(r.content);d=sha(p)
    if u in expected and d!=expected[u]:raise RuntimeError(f'SOURCE_TILE_HASH_MISMATCH {u}')
    prov.append({'url':u,'sha256':d,'bytes':p.stat().st_size,'matches_frozen_if_shared':u not in expected or d==expected[u]});ss.append(rasterio.open(p))
  arr,st=merge(ss,bounds=bbox);pr=ss[0].profile.copy();scrs=ss[0].crs
  for s in ss:s.close()
  hh,ww=arr.shape[1:];l,bo,ri,to=array_bounds(hh,ww,st);dt,dw,dh=calculate_default_transform(scrs,DST,ww,hh,l,bo,ri,to,resolution=RES);sn=pr.get('nodata');dn=-9999. if sn is None else float(sn);outa=np.full((dh,dw),dn,dtype='float32');reproject(source=arr[0],destination=outa,src_transform=st,src_crs=scrs,src_nodata=sn,dst_transform=dt,dst_crs=DST,dst_nodata=dn,resampling=Resampling.bilinear);out=td/'dem.tif';pr.update(driver='GTiff',width=dw,height=dh,count=1,dtype='float32',crs=DST,transform=dt,nodata=dn,compress='deflate')
  with rasterio.open(out,'w',**pr) as ds:ds.write(outa,1)
  return out,prov
 finally:
  for s in ss:
   try:s.close()
   except:pass
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--geojson',type=Path,required=True);a=ap.parse_args();a.report.parent.mkdir(parents=True,exist_ok=True);a.geojson.parent.mkdir(parents=True,exist_ok=True)
 co=json.loads(a.contract.read_text());regp=ROOT/co['registry_path'];candp=ROOT/co['candidate_path'];reg=json.loads(regp.read_text());cand=json.loads(candp.read_text());g=co['guards'];assert g==reg['guards'];assert co['morphometry_allowed'] is False and co['unblind_allowed'] is False;assert cand['outcome_evidence_read'] is False and cand['a6680_numeric_reference_read'] is False and cand['post_anchor_predictor_read'] is False;tid=co['target_id'];key=co.get('registry_target_key',tid);frozen=reg['targets'][key];assert frozen['outlet_status']=='FROZEN';ox,oy=float(frozen['accepted_outlet']['x_m']),float(frozen['accepted_outlet']['y_m']);tg=Transformer.from_crs(DST,'EPSG:4326',always_xy=True);ll=[tg.transform(float(p['x_m']),float(p['y_m'])) for p in co['base_extent_points_utm18s']];xs=[p[0] for p in ll];ys=[p[1] for p in ll];base=(min(xs),min(ys),max(xs),max(ys));expected={x['url']:x['sha256'] for x in cand.get('dem_tiles',[])}
 rep={'schema_version':'0.1','batch_id':reg['batch_id'],'target_id':tid,'registry_target_key':key,'status':'PENDING','guards':g,'geometry_only':True,'morphometry_computed':False,'outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'geometry_contract_sha256':sha(a.contract),'registry_sha256':sha(regp),'candidate_sha256':sha(candp),'delineator_sha256':sha(Path(__file__)),'attempts':[],'chosen_margin_degrees':None,'freeze_eligible':False}
 with tempfile.TemporaryDirectory(prefix=f'{tid}_geom_') as raw:
  root=Path(raw)
  for margin in [float(x) for x in co['margin_sequence_degrees']]:
   bbox=(base[0]-margin,base[1]-margin,base[2]+margin,base[3]+margin);td=root/f'm{margin}';td.mkdir()
   try:dp,prov=build(td,bbox,expected)
   except Exception as e:rep['status']='FAIL_CLOSED_SOURCE_INTEGRITY';rep['error']=str(e);a.report.write_text(json.dumps(rep,indent=2)+'\n');return 2
   with rasterio.open(dp) as ds:t=ds.transform;rr,cc=ds.index(ox,oy);cx,cy=rasterio.transform.xy(t,rr,cc,offset='center');dist=math.hypot(float(cx)-ox,float(cy)-oy)
   attempt={'margin_degrees':margin,'bbox_wgs84':[round(v,8) for v in bbox],'dem_utm_sha256':sha(dp),'source_tiles':prov,'outlet_grid_cell':{'row':int(rr),'col':int(cc),'center_x_m':round(float(cx),3),'center_y_m':round(float(cy),3),'distance_to_frozen_outlet_m':round(dist,3)}}
   if dist>math.hypot(RES,RES):attempt['status']='FAIL_OUTLET_MAPPING_TOLERANCE';rep['attempts'].append(attempt);rep['status']='FAIL_CLOSED_OUTLET_MAPPING';a.report.write_text(json.dumps(rep,indent=2)+'\n');return 3
   grid=Grid.from_raster(str(dp));dem=grid.read_raster(str(dp));dem=grid.fill_pits(dem);dem=grid.fill_depressions(dem);dem=grid.resolve_flats(dem);fd=grid.flowdir(dem,dirmap=D8);catch=np.asarray(grid.catchment(x=float(cx),y=float(cy),fdir=fd,dirmap=D8,xytype='coordinate')).astype(bool);touch=bool(catch[0,:].any() or catch[-1,:].any() or catch[:,0].any() or catch[:,-1].any());attempt['catchment_touches_dem_boundary']=touch;attempt['status']='CLIPPED_CONTINUE' if touch else 'COMPLETE';rep['attempts'].append(attempt)
   if touch:continue
   gs=[shape(geom) for geom,val in shapes(catch.astype('uint8'),mask=catch,transform=t) if int(val)==1]
   if not gs:rep['status']='FAIL_CLOSED_NO_GEOMETRY';a.report.write_text(json.dumps(rep,indent=2)+'\n');return 4
   geom=unary_union(gs);wgs=shp_transform(tg.transform,geom);fc={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'batch_id':reg['batch_id'],'target_id':tid,'geometry_status':'PREUNBLIND_D8_CANDIDATE','RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False},'geometry':mapping(wgs)}]};a.geojson.write_text(json.dumps(fc,ensure_ascii=False,separators=(',',':'))+'\n');rep['geometry_geojson_sha256']=sha(a.geojson);rep['chosen_margin_degrees']=margin;rep['chosen_dem_utm_sha256']=sha(dp);rep['catchment_touches_dem_boundary']=False;rep['status']=co['pass_status'];rep['freeze_eligible']=True;a.report.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rep,ensure_ascii=False,indent=2));return 0
 rep['status']='FAIL_CLOSED_ALL_FROZEN_MARGINS_CLIPPED';a.report.write_text(json.dumps(rep,indent=2)+'\n');return 5
if __name__=='__main__':raise SystemExit(main())
