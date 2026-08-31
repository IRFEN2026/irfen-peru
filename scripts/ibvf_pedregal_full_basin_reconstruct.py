#!/usr/bin/env python3
"""Reconstruct a full Pedregal upstream basin from the static search seed.

RESEARCH_ONLY / TEST_ONLY. The reconstruction uses Copernicus GLO-30, the
existing pedregal_8_20 snapped search seed, and static INGEMMET area context.
It must not read rainfall, selected windows, sensor availability, outcomes,
event dates, damage, risk, alerts, or case/control roles.

The key diagnostic is an independent reverse-D8 traversal, compared with the
legacy pysheds catchment materialization that produced implausibly tiny
polygons despite ~10 km2 upstream accumulation at the selected cell.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from pyproj import Geod
import requests
from pysheds.grid import Grid

GEOD = Geod(ellps="WGS84")
# Pysheds default D8: N, NE, E, SE, S, SW, W, NW
DIR_TO_OFFSET = {64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}


def load(p: Path) -> dict[str, Any]: return json.loads(p.read_text(encoding="utf-8"))
def csha(x: Any) -> str: return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def geod_area_km2(g) -> float:
    a,_=GEOD.geometry_area_perimeter(g); return abs(a)/1e6

def tile_name(lat: int, lon: int) -> str:
    latp=('N' if lat>=0 else 'S')+f'{abs(int(lat)):02d}'
    lonp=('E' if lon>=0 else 'W')+f'{abs(int(lon)):03d}'
    return f'Copernicus_DSM_COG_10_{latp}_00_{lonp}_00_DEM'
def tile_url(lat:int,lon:int)->str:
    n=tile_name(lat,lon); return f'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif'

def polygonize(mask: np.ndarray, transform):
    geoms=[shape(g) for g,v in shapes(mask.astype('uint8'),mask=mask,transform=transform) if int(v)==1]
    return unary_union(geoms).buffer(0) if geoms else None

def reverse_d8(fdir: np.ndarray, outlet_r:int, outlet_c:int) -> np.ndarray:
    rows,cols=fdir.shape
    out=np.zeros((rows,cols),dtype=bool)
    q=deque([(outlet_r,outlet_c)]); out[outlet_r,outlet_c]=True
    while q:
        r,c=q.popleft()
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                if dr==0 and dc==0: continue
                nr,nc=r+dr,c+dc
                if nr<0 or nr>=rows or nc<0 or nc>=cols or out[nr,nc]: continue
                code=int(fdir[nr,nc])
                off=DIR_TO_OFFSET.get(code)
                if off and nr+off[0]==r and nc+off[1]==c:
                    out[nr,nc]=True; q.append((nr,nc))
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--candidate-geojson',type=Path,required=True)
    ap.add_argument('--static-inventory',type=Path,required=True)
    ap.add_argument('--output-report',type=Path,required=True)
    ap.add_argument('--output-geojson',type=Path,required=True)
    args=ap.parse_args()
    fc=load(args.candidate_geojson); inv=load(args.static_inventory)
    assert fc['properties']['production_use'] is False
    assert inv['deployment_status']=='RESEARCH_ONLY' and inv['test_only'] is True
    assert inv['production_use'] is False and inv['production_ready'] is False
    assert inv['operational_alerting_enabled'] is False and inv['uses_operational_event_none_labels'] is False
    assert inv['territorial_activation_evidence_blinded'] is True
    seedf=next(f for f in fc['features'] if f['properties'].get('id')=='pedregal_8_20')
    p=seedf['properties']; lon=float(p['snapped_lon']); lat=float(p['snapped_lat'])
    ref=float(next(d for d in inv['documents'] if d['source_id']=='INGEMMET_HOSTED_MPR_VOL3_STATIC_PEDREGAL')['allowed_static_fields']['reference_catchment_area_km2'])
    pad=.12; xmin,xmax=lon-pad,lon+pad; ymin,ymax=lat-pad,lat+pad
    report={
      'schema_version':'irfen-ibvf-pedregal-full-basin-reconstruction-v0.1',
      'generated_at':datetime.now(timezone.utc).isoformat(),
      'framework':'IRFEN Independent Basin Validation Framework',
      'deployment_status':'RESEARCH_ONLY','test_only':True,
      'production_use':False,'production_ready':False,'operational_alerting_enabled':False,
      'uses_operational_event_none_labels':False,'territorial_activation_evidence_blinded':True,
      'serious_modeling_gate':'CLOSED_MINIMUM_DATASET_NOT_REACHED',
      'rainfall_values_read':False,'selected_window_dates_read':False,'sensor_availability_read':False,
      'territorial_outcome_fields_read':False,'event_dates_read':False,'damage_fields_read':False,
      'case_control_assignment_performed':False,
      'search_seed_feature_id':'pedregal_8_20','search_seed_lon':lon,'search_seed_lat':lat,
      'legacy_accumulation_area_approx_km2':float(p['accumulation_area_approx_km2']),
      'static_reference_area_km2':ref,
      'static_reference_semantics':'SEARCH_CONSTRAINT_ONLY_NOT_VALIDATION_BY_AREA_FITTING'
    }
    with tempfile.TemporaryDirectory(prefix='ibvf_pedregal_full_') as td0:
      td=Path(td0); srcs=[]; tile_hashes=[]
      for tlat in range(math.floor(ymin),math.floor(ymax)+1):
        for tlon in range(math.floor(xmin),math.floor(xmax)+1):
          url=tile_url(tlat,tlon); path=td/f'{tile_name(tlat,tlon)}.tif'
          r=requests.get(url,timeout=(15,120)); r.raise_for_status(); path.write_bytes(r.content)
          tile_hashes.append({'url':url,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()}); srcs.append(rasterio.open(path))
      mosaic,transform=merge(srcs,bounds=(xmin,ymin,xmax,ymax)); profile=srcs[0].profile.copy(); profile.update(height=mosaic.shape[1],width=mosaic.shape[2],transform=transform,count=1)
      for s in srcs:s.close()
      dempath=td/'dem.tif'
      with rasterio.open(dempath,'w',**profile) as dst: dst.write(mosaic[0],1)
      grid=Grid.from_raster(str(dempath)); dem=grid.read_raster(str(dempath)); dem=grid.fill_pits(dem); dem=grid.fill_depressions(dem); dem=grid.resolve_flats(dem); fdir=grid.flowdir(dem); acc=grid.accumulation(fdir)
      arr=np.asarray(acc,dtype=float); fd=np.asarray(fdir)
      # Nearest raster cell center to the frozen snapped search seed.
      invt=~transform; c_float,r_float=invt*(lon,lat); r0=int(math.floor(r_float)); c0=int(math.floor(c_float))
      r0=max(0,min(fd.shape[0]-1,r0)); c0=max(0,min(fd.shape[1]-1,c0))
      x0,y0=rasterio.transform.xy(transform,r0,c0,offset='center'); x0=float(x0); y0=float(y0)
      legacy=grid.catchment(x=x0,y=y0,fdir=fdir,xytype='coordinate'); legacy_mask=np.asarray(legacy,dtype=bool)
      reverse_mask=reverse_d8(fd,r0,c0)
      legacy_geom=polygonize(legacy_mask,transform); reverse_geom=polygonize(reverse_mask,transform)
      if reverse_geom is None or reverse_geom.is_empty: raise SystemExit('FAIL_REVERSE_D8_EMPTY')
      cell_count=int(reverse_mask.sum()); legacy_count=int(legacy_mask.sum())
      report['dem_tiles']=tile_hashes
      report['conditioned_dem_shape']=[int(fd.shape[0]),int(fd.shape[1])]
      report['outlet_grid']={'row':r0,'col':c0,'center_lon':x0,'center_lat':y0,'accumulation_cells':float(arr[r0,c0])}
      report['legacy_coordinate_catchment']={'cell_count':legacy_count,'geodesic_area_km2':geod_area_km2(legacy_geom) if legacy_geom and not legacy_geom.is_empty else None}
      report['reverse_d8_catchment']={'cell_count':cell_count,'geodesic_area_km2':geod_area_km2(reverse_geom)}
      report['reverse_vs_legacy_cell_ratio']=cell_count/max(1,legacy_count)
      report['reverse_area_relative_error_vs_static_reference']=abs(report['reverse_d8_catchment']['geodesic_area_km2']-ref)/ref
      report['reverse_area_relative_error_vs_legacy_accumulation']=abs(report['reverse_d8_catchment']['geodesic_area_km2']-float(p['accumulation_area_approx_km2']))/float(p['accumulation_area_approx_km2'])
      # 3x3 one-cell positional diagnostic; no candidate is promoted by this diagnostic alone.
      sens=[]
      for dr in (-1,0,1):
        for dc in (-1,0,1):
          rr,cc=r0+dr,c0+dc
          if rr<0 or rr>=fd.shape[0] or cc<0 or cc>=fd.shape[1]: continue
          m=reverse_d8(fd,rr,cc); g=polygonize(m,transform); area=geod_area_km2(g) if g and not g.is_empty else None
          xx,yy=rasterio.transform.xy(transform,rr,cc,offset='center')
          sens.append({'dr':dr,'dc':dc,'row':rr,'col':cc,'lon':float(xx),'lat':float(yy),'accumulation_cells':float(arr[rr,cc]),'cell_count':int(m.sum()),'geodesic_area_km2':area})
      report['one_cell_positional_diagnostic']=sens
      report['reconstruction_status']='REVERSE_D8_FULL_BASIN_CANDIDATE_GENERATED_STATIC_REVIEW_ONLY'
      report['canonical_geometry_promoted']=False
      report['modeling_allowed']=False; report['unblind_allowed']=False
      report['next_gate']='VERIFY_REVERSE_D8_AREA_TOPOLOGY_CHANNEL_ALIGNMENT_AND_POSITIONAL_STABILITY_AGAINST_STATIC_ALLOWED_EVIDENCE_BEFORE_CANONICAL_PEDREGAL_FREEZE'
      feature={'type':'Feature','properties':{
        'unit_id':'pedregal','candidate_id':'pedregal_ibvf_reverse_d8_v01','candidate_status':'REVIEW_ONLY',
        'production_use':False,'production_ready':False,'search_seed_feature_id':'pedregal_8_20',
        'search_seed_authority':'STATIC_GEOMORPHIC_SEARCH_ONLY_NOT_VALIDATED_OUTLET',
        'static_reference_area_km2':ref,'delineated_area_km2':round(report['reverse_d8_catchment']['geodesic_area_km2'],6),
        'territorial_outcome_fields_read':False,'event_dates_read':False
      },'geometry':mapping(reverse_geom)}
      outfc={'type':'FeatureCollection','properties':{'framework':'IRFEN Independent Basin Validation Framework','deployment_status':'RESEARCH_ONLY','test_only':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False,'territorial_activation_evidence_blinded':True,'warning':'Research-only Pedregal reconstruction candidate; not canonical and not operational.'},'features':[feature]}
      report['candidate_geojson_canonical_sha256']=csha(outfc)
      args.output_geojson.parent.mkdir(parents=True,exist_ok=True); args.output_geojson.write_text(json.dumps(outfc,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    report['report_canonical_sha256']=csha(report)
    args.output_report.parent.mkdir(parents=True,exist_ok=True); args.output_report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['reconstruction_status'],'reverse_area_km2':report['reverse_d8_catchment']['geodesic_area_km2'],'legacy_area_km2':report['legacy_coordinate_catchment']['geodesic_area_km2'],'reverse_cells':report['reverse_d8_catchment']['cell_count'],'legacy_cells':report['legacy_coordinate_catchment']['cell_count']},indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
