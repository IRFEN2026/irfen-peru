#!/usr/bin/env python3
"""Generate the frozen pre-unblind negative-control candidate pool using DEM/geography only."""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from pathlib import Path
import numpy as np
import rasterio
from pysheds.grid import Grid
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests

ROOT = Path(__file__).resolve().parents[1]
DST = "EPSG:32718"
RES = 30.0
D8 = (64,128,1,2,4,8,16,32)
OFF = {64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def build_dem(td: Path, bbox, tiles):
    srcs=[]; provenance=[]
    try:
        for i,tile in enumerate(tiles):
            p=td/f"tile_{i}.tif"
            r=requests.get(tile['url'],timeout=(20,180)); r.raise_for_status(); p.write_bytes(r.content)
            digest=sha256(p)
            if digest != tile['sha256']:
                raise RuntimeError(f"SOURCE_TILE_HASH_MISMATCH {tile['url']} {digest}")
            provenance.append({'url':tile['url'],'sha256':digest,'bytes':p.stat().st_size})
            srcs.append(rasterio.open(p))
        arr, st = merge(srcs, bounds=bbox)
        src_crs=srcs[0].crs; profile=srcs[0].profile.copy(); nodata=profile.get('nodata')
        h,w=arr.shape[1:]; left,bottom,right,top=array_bounds(h,w,st)
        dt,dw,dh=calculate_default_transform(src_crs,DST,w,h,left,bottom,right,top,resolution=RES)
        dn=-9999.0 if nodata is None else float(nodata)
        out=np.full((dh,dw),dn,dtype='float32')
        reproject(arr[0],out,src_transform=st,src_crs=src_crs,src_nodata=nodata,dst_transform=dt,dst_crs=DST,dst_nodata=dn,resampling=Resampling.bilinear)
        dp=td/'dem.tif'; profile.update(driver='GTiff',width=dw,height=dh,count=1,dtype='float32',crs=DST,transform=dt,nodata=dn,compress='deflate')
        with rasterio.open(dp,'w',**profile) as ds: ds.write(out,1)
        return dp, provenance
    finally:
        for s in srcs:
            try: s.close()
            except Exception: pass

def trace_to_anchor(fdir, start, target_xy, transform, tolerance_m):
    r,c=start; path=[]; seen=set(); best=float('inf')
    rows,cols=fdir.shape
    for _ in range(rows*cols):
        if (r,c) in seen: raise RuntimeError('MAINSTEM_TRACE_LOOP')
        seen.add((r,c)); path.append((r,c))
        x,y=rasterio.transform.xy(transform,r,c,offset='center')
        dist=math.hypot(float(x)-target_xy[0],float(y)-target_xy[1]); best=min(best,dist)
        if dist <= tolerance_m: return path, dist
        code=int(fdir[r,c])
        if code not in OFF: raise RuntimeError(f'MAINSTEM_TRACE_INVALID_FDIR {code}')
        dr,dc=OFF[code]; nr,nc=r+dr,c+dc
        if nr<0 or nr>=rows or nc<0 or nc>=cols: raise RuntimeError('MAINSTEM_TRACE_LEFT_DEM')
        r,c=nr,nc
    raise RuntimeError(f'MAINSTEM_TRACE_NO_ANCHOR best={best}')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=json.loads(a.contract.read_text(encoding='utf-8'))
    regp=ROOT/co['inputs']['outlet_freeze_registry']; ancp=ROOT/co['inputs']['static_anchor_registry']
    reg=json.loads(regp.read_text(encoding='utf-8')); anc=json.loads(ancp.read_text(encoding='utf-8'))
    guards=co['guards']
    assert guards==reg['guards']==anc['guards']
    assert reg['batch_gate']['frozen_outlet_count']==reg['batch_gate']['required_frozen_outlet_count']==6
    assert reg['batch_gate']['frozen_geometry_count']==reg['batch_gate']['required_frozen_geometry_count']==6
    assert reg['batch_gate']['unblind_allowed'] is False
    assert reg['anti_leakage']['outcome_evidence_read'] is False
    assert reg['anti_leakage']['a6680_numeric_reference_read'] is False
    assert reg['anti_leakage']['post_anchor_predictor_read'] is False
    rep={'schema_version':'0.1','batch_id':reg['batch_id'],'status':'PENDING','guards':guards,
         'phase':'PREUNBLIND_NEGATIVE_CONTROL_CANDIDATE_POOL','outcome_evidence_read':False,
         'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,
         'control_outcome_adjudication_performed':False,'candidate_selection_used_observed_2015_response':False,
         'contract_sha256':sha256(a.contract),'outlet_registry_sha256':sha256(regp),'static_anchor_registry_sha256':sha256(ancp),
         'candidate_pool_frozen':False}
    try:
        with tempfile.TemporaryDirectory(prefix='chosica_negctrl_') as raw:
            td=Path(raw); dp,prov=build_dem(td,co['corridor']['dem_bbox_wgs84'],co['inputs']['dem_tiles'])
            grid=Grid.from_raster(str(dp)); dem=grid.read_raster(str(dp)); dem=grid.fill_pits(dem); dem=grid.fill_depressions(dem); dem=grid.resolve_flats(dem)
            fdir_raster=grid.flowdir(dem,dirmap=D8); fd=np.asarray(fdir_raster); acc=np.asarray(grid.accumulation(fdir_raster,dirmap=D8))
            with rasterio.open(dp) as ds:
                tr=ds.transform
                s=reg['targets']['cashahuacra']['accepted_outlet']; sr,sc=ds.index(float(s['x_m']),float(s['y_m']))
                r9=anc['anchors']['r9_puente_california_rimac']; target_xy=(float(r9['easting_m']),float(r9['northing_m']))
                path,terminal_dist=trace_to_anchor(fd,(sr,sc),target_xy,tr,float(co['corridor']['downstream_identity_tolerance_m']))
                mainset=set(path); frozen=[]
                for t in reg['targets'].values():
                    o=t['accepted_outlet']; frozen.append((float(o['x_m']),float(o['y_m'])))
                minacc=int(co['candidate_rule']['minimum_feeder_accumulation_cells']); ex=float(co['candidate_rule']['exclude_within_m_of_any_frozen_target_outlet'])
                candidates=[]
                for idx,(mr,mc) in enumerate(path):
                    feeders=[]
                    for nr in range(max(0,mr-1),min(fd.shape[0],mr+2)):
                        for nc in range(max(0,mc-1),min(fd.shape[1],mc+2)):
                            if (nr,nc)==(mr,mc) or (nr,nc) in mainset: continue
                            code=int(fd[nr,nc]); off=OFF.get(code)
                            if off and (nr+off[0],nc+off[1])==(mr,mc) and float(acc[nr,nc])>=minacc:
                                feeders.append((float(acc[nr,nc]),nr,nc))
                    if not feeders: continue
                    feeders.sort(key=lambda z:(-z[0],z[1],z[2])); aval,fr,fc=feeders[0]
                    mx,my=rasterio.transform.xy(tr,mr,mc,offset='center'); fx,fy=rasterio.transform.xy(tr,fr,fc,offset='center')
                    nearest=min(math.hypot(float(mx)-x,float(my)-y) for x,y in frozen)
                    if nearest < ex: continue
                    candidates.append({'candidate_id':f'NC_{len(candidates)+1:03d}','mainstem_path_index':idx,
                        'mainstem_cell':{'row':mr,'col':mc,'x_m':round(float(mx),3),'y_m':round(float(my),3)},
                        'feeder_cell':{'row':fr,'col':fc,'x_m':round(float(fx),3),'y_m':round(float(fy),3)},
                        'feeder_accumulation_cells':int(round(aval)),'feeder_area_proxy_km2':round(aval*RES*RES/1e6,6),
                        'nearest_frozen_target_outlet_m':round(nearest,3)})
            candidates.sort(key=lambda z:(z['mainstem_path_index'],z['feeder_cell']['row'],z['feeder_cell']['col']))
            if not candidates: raise RuntimeError('NO_ELIGIBLE_DEM_ONLY_CONTROL_CANDIDATES')
            rep.update({'status':'PASS_PREUNBLIND_NEGATIVE_CONTROL_CANDIDATE_POOL','dem_utm_sha256':sha256(dp),'dem_tiles':prov,
                        'mainstem_start_cell':{'row':int(sr),'col':int(sc)},'mainstem_trace_cells':len(path),
                        'terminal_distance_to_r9_m':round(float(terminal_dist),3),'candidate_count':len(candidates),'candidates':candidates,
                        'candidate_pool_frozen':True})
    except Exception as e:
        rep['status']='FAIL_CLOSED_NEGATIVE_CONTROL_CANDIDATE_GENERATION'; rep['error']=str(e)
        a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 2
    a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(rep,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
