#!/usr/bin/env python3
"""Outcome-blind Quirio catchment delineation using the frozen expansion contract."""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from pathlib import Path
from typing import Iterable
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

ROOT=Path(__file__).resolve().parents[1]
METHOD=ROOT/'config/chosica_2015_quirio_geometry_delineation_contract_v0_1.json'
OUTLET_CONTRACT=ROOT/'config/chosica_2015_quirio_outlet_resolution_contract_v0_1.json'
REGISTRY=ROOT/'config/chosica_2015_outlet_freeze_registry_v0_1.json'
CANDIDATE=ROOT/'site/data/validation/chosica_2015_quirio_outlet_candidate.json'
DST_CRS='EPSG:32718'; RES=30.0; D8=(64,128,1,2,4,8,16,32)

def sha(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()
def tname(lat,lon):
 a,b=math.floor(lat),math.floor(lon); return f"Copernicus_DSM_COG_10_{('N' if a>=0 else 'S')+f'{abs(a):02d}'}_00_{('E' if b>=0 else 'W')+f'{abs(b):03d}'}_00_DEM"
def tiles(b):
 xmin,ymin,xmax,ymax=b
 for a in range(math.floor(ymin),math.floor(ymax-1e-12)+1):
  for c in range(math.floor(xmin),math.floor(xmax-1e-12)+1): yield a,c

def exact_base_extent(contract):
 p=contract['static_source']['points']; keys=['rimac_upstream_bridge_r4','quirio_r8','rimac_downstream_bridge_r9']; tr=Transformer.from_crs(DST_CRS,'EPSG:4326',always_xy=True)
 ll=[tr.transform(float(p[k]['easting_m']),float(p[k]['northing_m'])) for k in keys]; xs=[x for x,y in ll]; ys=[y for x,y in ll]; return min(xs),min(ys),max(xs),max(ys)
def bbox(base,m): return base[0]-m,base[1]-m,base[2]+m,base[3]+m

def build_dem(td:Path,b,expected):
 srcs=[]; prov=[]
 try:
  for a,c in tiles(b):
   n=tname(float(a),float(c)); u=f'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif'; p=td/f'{n}.tif'; r=requests.get(u,timeout=(20,180)); r.raise_for_status(); p.write_bytes(r.content); digest=sha(p)
   if u in expected and digest!=expected[u]: raise RuntimeError(f'SOURCE_TILE_HASH_MISMATCH {u}')
   prov.append({'url':u,'sha256':digest,'bytes':p.stat().st_size,'matches_frozen_if_shared':u not in expected or digest==expected[u]}); srcs.append(rasterio.open(p))
  arr,st=merge(srcs,bounds=b); prof=srcs[0].profile.copy(); scrs=srcs[0].crs
  for s in srcs:s.close()
  sh,sw=arr.shape[1:]; left,bottom,right,top=array_bounds(sh,sw,st); dt,dw,dh=calculate_default_transform(scrs,DST_CRS,sw,sh,left,bottom,right,top,resolution=RES); sn=prof.get('nodata'); dn=-9999. if sn is None else float(sn); outa=np.full((dh,dw),dn,dtype='float32')
  reproject(source=arr[0],destination=outa,src_transform=st,src_crs=scrs,src_nodata=sn,dst_transform=dt,dst_crs=DST_CRS,dst_nodata=dn,resampling=Resampling.bilinear)
  out=td/'dem.tif'; prof.update(driver='GTiff',width=dw,height=dh,count=1,dtype='float32',crs=DST_CRS,transform=dt,nodata=dn,compress='deflate')
  with rasterio.open(out,'w',**prof) as ds:ds.write(outa,1)
  return out,prov
 finally:
  for s in srcs:
   try:s.close()
   except Exception:pass

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--report',type=Path,required=True); ap.add_argument('--geojson',type=Path,required=True); a=ap.parse_args(); a.report.parent.mkdir(parents=True,exist_ok=True); a.geojson.parent.mkdir(parents=True,exist_ok=True)
 method=json.loads(METHOD.read_text()); oc=json.loads(OUTLET_CONTRACT.read_text()); reg=json.loads(REGISTRY.read_text()); cand=json.loads(CANDIDATE.read_text()); g=method['guards']; assert g==reg['guards']; assert method['morphometry_allowed'] is False and method['unblind_allowed'] is False; assert cand['outcome_evidence_read'] is False and cand['a6680_numeric_reference_read'] is False and cand['post_anchor_predictor_read'] is False
 frozen=reg['targets']['quirio']; assert frozen['outlet_status']=='FROZEN'; outlet=frozen['accepted_outlet']; ox,oy=float(outlet['x_m']),float(outlet['y_m']); expected={z['url']:z['sha256'] for z in cand['dem_tiles']}; base=exact_base_extent(oc); margins=[float(x) for x in method['margin_sequence_degrees']]
 report={'schema_version':'0.1','batch_id':reg['batch_id'],'target_id':'quirio','status':'PENDING','guards':g,'geometry_only':True,'morphometry_computed':False,'outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'geometry_contract_sha256':sha(METHOD),'outlet_contract_sha256':sha(OUTLET_CONTRACT),'registry_sha256':sha(REGISTRY),'candidate_sha256':sha(CANDIDATE),'delineator_sha256':sha(Path(__file__)),'attempts':[],'chosen_margin_degrees':None,'freeze_eligible':False}
 togeo=Transformer.from_crs(DST_CRS,'EPSG:4326',always_xy=True)
 with tempfile.TemporaryDirectory(prefix='irfen_qexp_') as raw:
  root=Path(raw)
  for margin in margins:
   td=root/f'm{margin}'; td.mkdir(); b=bbox(base,margin)
   try:demp,prov=build_dem(td,b,expected)
   except Exception as e:
    report['status']='FAIL_CLOSED_SOURCE_INTEGRITY'; report['error']=str(e); a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); return 2
   with rasterio.open(demp) as ds:
    t=ds.transform; w,h=ds.width,ds.height; rr,cc=ds.index(ox,oy); cx,cy=rasterio.transform.xy(t,rr,cc,offset='center'); dist=math.hypot(float(cx)-ox,float(cy)-oy)
   attempt={'margin_degrees':margin,'bbox_wgs84':[round(v,8) for v in b],'dem_utm_sha256':sha(demp),'source_tiles':prov,'outlet_grid_cell':{'row':int(rr),'col':int(cc),'center_x_m':round(float(cx),3),'center_y_m':round(float(cy),3),'distance_to_frozen_outlet_m':round(dist,3)}}
   if dist>math.hypot(RES,RES): attempt['status']='FAIL_OUTLET_MAPPING_TOLERANCE'; report['attempts'].append(attempt); report['status']='FAIL_CLOSED_OUTLET_MAPPING'; a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); return 3
   grid=Grid.from_raster(str(demp)); dem=grid.read_raster(str(demp)); dem=grid.fill_pits(dem); dem=grid.fill_depressions(dem); dem=grid.resolve_flats(dem); fdir=grid.flowdir(dem,dirmap=D8); catch=np.asarray(grid.catchment(x=float(cx),y=float(cy),fdir=fdir,dirmap=D8,xytype='coordinate')).astype(bool); touch=bool(catch[0,:].any() or catch[-1,:].any() or catch[:,0].any() or catch[:,-1].any()); attempt['catchment_touches_dem_boundary']=touch; attempt['status']='CLIPPED_CONTINUE' if touch else 'COMPLETE'; report['attempts'].append(attempt)
   if touch: continue
   geoms=[shape(geom) for geom,val in shapes(catch.astype('uint8'),mask=catch,transform=t) if int(val)==1]
   if not geoms: report['status']='FAIL_CLOSED_NO_GEOMETRY'; a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); return 4
   geom=unary_union(geoms); wgs=shp_transform(togeo.transform,geom); fc={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'batch_id':reg['batch_id'],'target_id':'quirio','geometry_status':'PREUNBLIND_D8_CANDIDATE','RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False},'geometry':mapping(wgs)}]}; a.geojson.write_text(json.dumps(fc,ensure_ascii=False,separators=(',',':'))+'\n'); report['geometry_geojson_sha256']=sha(a.geojson); report['chosen_margin_degrees']=margin; report['chosen_dem_utm_sha256']=sha(demp); report['catchment_touches_dem_boundary']=False; report['status']='PASS_QUIRIO_EXPANDED_D8_CATCHMENT_CANDIDATE'; report['freeze_eligible']=True; a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(report,ensure_ascii=False,indent=2)); return 0
 report['status']='FAIL_CLOSED_ALL_FROZEN_MARGINS_CLIPPED'; a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); return 5
if __name__=='__main__': raise SystemExit(main())
