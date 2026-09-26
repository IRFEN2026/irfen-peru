#!/usr/bin/env python3
"""Delineate frozen shortlisted negative-control catchments without reading outcomes."""
from __future__ import annotations
import argparse,hashlib,json,tempfile
from pathlib import Path
import numpy as np
import rasterio
from pysheds.grid import Grid
from rasterio.features import shapes
from pyproj import Transformer
from shapely.geometry import mapping,shape
from shapely.ops import transform as shp_transform,unary_union

import generate_chosica_2015_negative_control_candidates as gen
import match_chosica_2015_negative_control_candidates as match

ROOT=Path(__file__).resolve().parents[1]
D8=gen.D8

def load(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--geojson',type=Path,required=True);a=ap.parse_args();a.report.parent.mkdir(parents=True,exist_ok=True);a.geojson.parent.mkdir(parents=True,exist_ok=True)
 co=load(a.contract);poolp=ROOT/co['candidate_pool_path'];pool=load(poolp);mfp=ROOT/co['matching_freeze_record'];mf=load(mfp);genp=ROOT/co['candidate_geometry_rule']['dem_reconstruction_contract'];gc=load(genp)
 rep={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PENDING','guards':co['guards'],'outcome_evidence_read':False,'candidate_outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'contract_sha256':sha(a.contract),'candidate_pool_sha256':sha(poolp),'matching_freeze_record_sha256':sha(mfp),'candidate_count':0}
 try:
  assert pool['guards']==mf['guards']==gc['guards']==co['guards']
  assert sha(poolp)==co['candidate_pool_sha256']
  expected=sorted(co['shortlisted_candidate_ids'])
  actual=sorted({r['candidate_id'] for rows in mf['execution_result']['shortlists'].values() for r in rows})
  assert actual==expected
  with tempfile.TemporaryDirectory(prefix='chosica_ctrlgeom_') as raw:
   td=Path(raw);dp,prov=gen.build_dem(td,gc['corridor']['dem_bbox_wgs84'],pool['dem_tiles'])
   if sha(dp)!=co['candidate_geometry_rule']['required_dem_utm_sha256']:raise RuntimeError('FAIL_CLOSED_DEM_HASH')
   grid=Grid.from_raster(str(dp));dem=grid.read_raster(str(dp));dem=grid.fill_pits(dem);dem=grid.fill_depressions(dem);dem=grid.resolve_flats(dem);fdir=np.asarray(grid.flowdir(dem,dirmap=D8));up=match.build_upstream(fdir)
   lookup={c['candidate_id']:c for c in pool['candidates']};features=[];audit=[]
   to_wgs=Transformer.from_crs('EPSG:32718','EPSG:4326',always_xy=True)
   with rasterio.open(dp) as ds:
    tr=ds.transform
    for cid in expected:
     c=lookup[cid];fr,fc=int(c['feeder_cell']['row']),int(c['feeder_cell']['col']);catch=match.reverse_catchment(up,fdir.shape,(fr,fc));touch=bool(catch[0,:].any() or catch[-1,:].any() or catch[:,0].any() or catch[:,-1].any())
     if touch:raise RuntimeError(f'FAIL_CLOSED_BOUNDARY_TOUCH {cid}')
     gs=[shape(g) for g,v in shapes(catch.astype('uint8'),mask=catch,transform=tr) if int(v)==1]
     if not gs:raise RuntimeError(f'FAIL_CLOSED_EMPTY_GEOMETRY {cid}')
     geom=unary_union(gs);wgs=shp_transform(to_wgs.transform,geom);fx,fy=c['feeder_cell']['x_m'],c['feeder_cell']['y_m'];lon,lat=to_wgs.transform(float(fx),float(fy))
     features.append({'type':'Feature','properties':{'candidate_id':cid,'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False,'outcome_evidence_read':False,'candidate_outcome_evidence_read':False,'feeder_lon':round(lon,8),'feeder_lat':round(lat,8)},'geometry':mapping(wgs)})
     audit.append({'candidate_id':cid,'catchment_cell_count':int(catch.sum()),'catchment_touches_dem_boundary':False,'feeder_lon':round(lon,8),'feeder_lat':round(lat,8)})
   fc={'type':'FeatureCollection','name':'CHOSICA_2015_NEGATIVE_CONTROL_SHORTLIST','features':features};a.geojson.write_text(json.dumps(fc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
   rep.update({'status':'PASS_PREUNBLIND_NEGATIVE_CONTROL_SHORTLIST_GEOMETRY','candidate_count':len(features),'dem_utm_sha256':sha(dp),'dem_tiles':prov,'geojson_sha256':sha(a.geojson),'candidate_audit':audit})
 except Exception as e:
  rep['status']='FAIL_CLOSED_NEGATIVE_CONTROL_SHORTLIST_GEOMETRY';rep['error']=str(e);a.report.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(rep,ensure_ascii=False,indent=2));return 2
 a.report.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(rep,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
