#!/usr/bin/env python3
"""Compute DEM-only candidate morphometry and freeze a pre-unblind control shortlist."""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from collections import deque
from pathlib import Path

import numpy as np
import rasterio
from pysheds.grid import Grid

import generate_chosica_2015_negative_control_candidates as gen
import compute_chosica_2015_morphometry_phase1 as morph

ROOT = Path(__file__).resolve().parents[1]
OFF = gen.OFF
D8 = gen.D8


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()


def build_upstream(fdir: np.ndarray):
    rows,cols=fdir.shape
    upstream=[[] for _ in range(rows*cols)]
    for r in range(rows):
        for c in range(cols):
            off=OFF.get(int(fdir[r,c]))
            if off is None: continue
            nr,nc=r+off[0],c+off[1]
            if 0<=nr<rows and 0<=nc<cols:
                upstream[nr*cols+nc].append(r*cols+c)
    return upstream


def reverse_catchment(upstream, shape, start_rc):
    rows,cols=shape; sr,sc=start_rc
    start=sr*cols+sc; seen=np.zeros(rows*cols,dtype=bool); seen[start]=True
    q=deque([start])
    while q:
        cur=q.popleft()
        for u in upstream[cur]:
            if not seen[u]:
                seen[u]=True; q.append(u)
    return seen.reshape(shape)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=json.loads(a.contract.read_text(encoding='utf-8'))
    poolp=ROOT/co['candidate_pool_path']; recp=ROOT/co['candidate_pool_freeze_record']; morprecp=ROOT/co['target_morphometry_source']['freeze_record']
    pool=json.loads(poolp.read_text(encoding='utf-8')); rec=json.loads(recp.read_text(encoding='utf-8')); morprec=json.loads(morprecp.read_text(encoding='utf-8'))
    guards=co['guards']
    rep={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PENDING','guards':guards,
         'phase':'PREUNBLIND_NEGATIVE_CONTROL_DEM_MATCHING','outcome_evidence_read':False,'candidate_outcome_evidence_read':False,
         'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'control_outcome_adjudication_performed':False,
         'matching_contract_sha256':sha256(a.contract),'candidate_pool_sha256':sha256(poolp),'candidate_pool_freeze_record_sha256':sha256(recp),
         'target_morphometry_freeze_record_sha256':sha256(morprecp),'shortlist_frozen':False}
    try:
        assert pool['guards']==rec['guards']==morprec['guards']==guards
        assert sha256(poolp)==co['candidate_pool_sha256']==rec['candidate_pool_sha256']
        assert pool['candidate_pool_frozen'] is True and pool['candidate_count']==29
        assert rec['next_gate']['candidate_geometry_and_dem_morphometry_allowed'] is True
        assert rec['next_gate']['control_outcome_adjudication_allowed_before_ranked_shortlist_freeze'] is False
        assert morprec['phase1_frozen'] is True
        assert morprec['provenance']['report_sha256']==co['target_morphometry_source']['report_sha256']
        assert co['target_morphometry_source']['a6680_numeric_reference_read'] is False
        assert co['target_morphometry_source']['outcome_evidence_read'] is False
        assert co['target_morphometry_source']['post_anchor_predictor_read'] is False
        with tempfile.TemporaryDirectory(prefix='chosica_negctrl_match_') as raw:
            td=Path(raw)
            dp,prov=gen.build_dem(td,co['candidate_pool_path'] and [-76.77617513,-12.00374994,-76.64255814,-11.88463456],pool['dem_tiles'])
            rebuilt=sha256(dp)
            if rebuilt!=pool['dem_utm_sha256']:
                raise RuntimeError(f'FAIL_CLOSED_CANDIDATE_POOL_DEM_HASH {rebuilt}')
            grid=Grid.from_raster(str(dp)); dem=grid.read_raster(str(dp)); dem=grid.fill_pits(dem); dem=grid.fill_depressions(dem); dem=grid.resolve_flats(dem)
            fdir_raster=grid.flowdir(dem,dirmap=D8); fdir=np.asarray(fdir_raster)
            upstream=build_upstream(fdir)
            with rasterio.open(dp) as ds:
                z=ds.read(1).astype('float64'); tr=ds.transform; nodata=ds.nodata; dx,dy=abs(float(tr.a)),abs(float(tr.e))
                valid=np.isfinite(z)
                if nodata is not None: valid &= z!=float(nodata)
                slope=morph.horn_slope_deg(z,valid,dx,dy)
                target_cells=[]
                for t in co['target_reference']:
                    rr,cc=ds.index(float(t['outlet_x_m']),float(t['outlet_y_m']))
                    target_cells.append((t['target_id'],int(rr),int(cc)))
                metrics=[]
                for cand in pool['candidates']:
                    fr=int(cand['feeder_cell']['row']); fc=int(cand['feeder_cell']['col'])
                    if not (0<=fr<fdir.shape[0] and 0<=fc<fdir.shape[1]):
                        raise RuntimeError(f"FAIL_CLOSED_FEEDER_OUTSIDE {cand['candidate_id']}")
                    catch=reverse_catchment(upstream,fdir.shape,(fr,fc)) & valid
                    cell_count=int(catch.sum())
                    touch=bool(catch[0,:].any() or catch[-1,:].any() or catch[:,0].any() or catch[:,-1].any())
                    contains=[]
                    for tid,rr,cc in target_cells:
                        if 0<=rr<catch.shape[0] and 0<=cc<catch.shape[1] and bool(catch[rr,cc]): contains.append(tid)
                    eligible=cell_count>=int(co['candidate_geometry_rule']['minimum_catchment_cells']) and not touch and not contains
                    vals=z[catch]
                    sv=slope[catch & np.isfinite(slope)]
                    if vals.size==0 or sv.size==0:
                        eligible=False
                        relief=None; mean_slope=None; elev_min=None; elev_max=None
                    else:
                        elev_min=float(vals.min()); elev_max=float(vals.max()); relief=elev_max-elev_min; mean_slope=float(sv.mean())
                    area=cell_count*dx*dy/1e6
                    metrics.append({'candidate_id':cand['candidate_id'],'eligible_for_matching':eligible,'catchment_cell_count':cell_count,
                        'catchment_touches_dem_boundary':touch,'contains_frozen_target_outlet_ids':contains,
                        'area_km2':round(area,6),'pool_accumulation_area_proxy_km2':cand['feeder_area_proxy_km2'],
                        'area_proxy_absolute_difference_km2':round(abs(area-float(cand['feeder_area_proxy_km2'])),6),
                        'elevation_min_m':None if elev_min is None else round(elev_min,6),'elevation_max_m':None if elev_max is None else round(elev_max,6),
                        'relief_m':None if relief is None else round(relief,6),'mean_basin_slope_deg':None if mean_slope is None else round(mean_slope,9),
                        'mainstem_confluence_x_m':cand['mainstem_cell']['x_m'],'mainstem_confluence_y_m':cand['mainstem_cell']['y_m']})
            eligible=[m for m in metrics if m['eligible_for_matching']]
            if len(eligible)<int(co['shortlist']['per_target']):
                raise RuntimeError(f'FAIL_CLOSED_INSUFFICIENT_ELIGIBLE_CANDIDATES {len(eligible)}')
            eps=float(co['score']['epsilon_relief_m']); rankings={}; shortlists={}
            for t in co['target_reference']:
                rows=[]
                for m in eligible:
                    distance=math.hypot(float(m['mainstem_confluence_x_m'])-float(t['outlet_x_m']),float(m['mainstem_confluence_y_m'])-float(t['outlet_y_m']))
                    ar=float(m['area_km2'])/float(t['area_km2'])
                    rr=max(float(m['relief_m']),eps)/max(float(t['relief_m']),eps)
                    sd=abs(float(m['mean_basin_slope_deg'])-float(t['mean_basin_slope_deg']))
                    score=distance/10000.0+abs(math.log(ar))+abs(math.log(rr))+sd/45.0
                    rows.append({'candidate_id':m['candidate_id'],'score':round(score,9),'distance_m':round(distance,3),
                                 'area_ratio':round(ar,9),'relief_ratio':round(rr,9),'mean_slope_abs_diff_deg':round(sd,9)})
                rows.sort(key=lambda x:(x['score'],x['distance_m'],x['candidate_id']))
                rankings[t['target_id']]=rows
                shortlists[t['target_id']]=rows[:int(co['shortlist']['per_target'])]
            rep.update({'status':'PASS_PREUNBLIND_NEGATIVE_CONTROL_DEM_MATCHING','dem_utm_sha256':rebuilt,'dem_tiles':prov,
                        'candidate_count':len(metrics),'eligible_candidate_count':len(eligible),'candidate_metrics':metrics,
                        'rankings':rankings,'shortlists':shortlists,'shortlist_frozen':True,
                        'score_formula':co['score']['formula'],'shortlist_per_target':int(co['shortlist']['per_target'])})
    except Exception as e:
        rep['status']='FAIL_CLOSED_NEGATIVE_CONTROL_DEM_MATCHING'; rep['error']=str(e)
        a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 2
    a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
