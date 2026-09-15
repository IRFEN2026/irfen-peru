#!/usr/bin/env python3
"""Extract pre-anchor IMERG predictors for the frozen negative-control shortlist without reading outcomes."""
from __future__ import annotations
import argparse,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import requests
from shapely.geometry import shape

import extract_chosica_2015_preunblind_imerg as base

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'config/chosica_2015_negative_control_preunblind_imerg_execution_v0_1.json'
UTC=timezone.utc
GUARDS={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--geojson',type=Path,required=True); ap.add_argument('--report',type=Path,required=True)
    a=ap.parse_args(); a.report.parent.mkdir(parents=True,exist_ok=True)
    co=load(CONTRACT); execution=load(ROOT/co['inherits_target_imerg_execution']); plan=load(ROOT/co['inherits_time_plan']); freeze=load(ROOT/co['geometry_freeze_record'])
    if co['guards']!=GUARDS or execution['guards']!=GUARDS or plan['guards']!=GUARDS or freeze['guards']!=GUARDS: raise RuntimeError('FAIL_CLOSED_GUARD_MISMATCH')
    if freeze['status']!='NEGATIVE_CONTROL_SHORTLIST_GEOMETRY_FROZEN_BY_EXACT_HASH': raise RuntimeError('FAIL_CLOSED_GEOMETRY_NOT_FROZEN')
    if freeze['next_gate']['sealed_target_outcome_unblind_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_TARGET_UNBLIND_OPEN')
    if freeze['anti_leakage']['outcome_evidence_read'] is not False or freeze['anti_leakage']['candidate_outcome_evidence_read'] is not False: raise RuntimeError('FAIL_CLOSED_PRIOR_OUTCOME_READ')
    if base.sha256_path(a.geojson)!=co['geometry']['required_geojson_sha256'] or base.sha256_path(a.geojson)!=freeze['frozen_outputs']['geojson_sha256']: raise RuntimeError('FAIL_CLOSED_GEOMETRY_HASH')
    geomdoc=load(a.geojson)
    if geomdoc.get('type')!='FeatureCollection': raise RuntimeError('FAIL_CLOSED_GEOMETRY_COLLECTION')
    features={f.get('properties',{}).get('candidate_id'):f for f in geomdoc.get('features',[])}
    ids=list(co['candidate_ids'])
    if set(features)!=set(ids) or len(features)!=co['geometry']['candidate_count']: raise RuntimeError('FAIL_CLOSED_CANDIDATE_GEOMETRY_IDS')
    start=base.parse_utc(plan['grid']['start_utc']); end=base.parse_utc(plan['grid']['end_exclusive_utc']); anchor=base.parse_utc(plan['anchor_utc'])
    slot_minutes=int(plan['grid']['slot_minutes']); slot_count=int(plan['grid']['slot_count'])
    if end!=anchor or slot_minutes!=30 or slot_count!=720 or start+timedelta(minutes=slot_minutes*slot_count)!=end: raise RuntimeError('FAIL_CLOSED_TIME_GRID')
    metas={}; global_cells={}
    for cid in ids:
        f=features[cid]; p=f.get('properties') or {}
        for k,v in GUARDS.items():
            if p.get(k)!=v: raise RuntimeError(f'FAIL_CLOSED_FEATURE_GUARD {cid} {k}')
        if p.get('outcome_evidence_read') is not False or p.get('candidate_outcome_evidence_read') is not False: raise RuntimeError(f'FAIL_CLOSED_FEATURE_OUTCOME {cid}')
        geom=shape(f['geometry'])
        if geom.is_empty or not geom.is_valid: geom=geom.buffer(0)
        if geom.is_empty or not geom.is_valid: raise RuntimeError(f'FAIL_CLOSED_INVALID_GEOMETRY {cid}')
        cells=base.imerg_cells_for_geometry(geom)
        for c in cells: global_cells[(c['lon'],c['lat'])]={'lon':c['lon'],'lat':c['lat']}
        metas[cid]={'cells':cells}
    points=[global_cells[k] for k in sorted(global_cells)]; point_index={(p['lon'],p['lat']):i for i,p in enumerate(points)}
    for meta in metas.values():
        for c in meta['cells']: c['global_point_index']=point_index[(c['lon'],c['lat'])]
    retrieval=execution['retrieval']; block_hours=int(retrieval['block_hours']); retry_count=int(retrieval['retry_count']); maximum=int(retrieval['maximum_halfhour_slices_per_block'])
    if block_hours<=0 or block_hours*2>maximum or retry_count<1: raise RuntimeError('FAIL_CLOSED_RETRIEVAL_CONTRACT')
    session=requests.Session(); session.headers.update({'User-Agent':retrieval['user_agent']}); service=execution['source']['service']
    observations={}; duplicate_count=0; ignored_outside_grid=0; request_count=0; cursor=start
    while cursor<end:
        bend=min(end,cursor+timedelta(hours=block_hours)); inclusive=bend-timedelta(minutes=slot_minutes)
        samples=base.sample_block(points,cursor,inclusive,session,service,retry_count); request_count+=1
        for sample in samples:
            attrs=sample.get('attributes') or {}; tm=base.as_millis(attrs.get('StdTime',attrs.get('stdtime')))
            if tm is None: continue
            dt=datetime.fromtimestamp(tm/1000.0,tz=UTC)
            if dt<start or dt>=end or ((dt-start).total_seconds()%(slot_minutes*60))!=0: ignored_outside_grid+=1; continue
            loc=sample.get('location') or {}
            try: lon=float(loc['x']); lat=float(loc['y']); value=float(sample.get('value'))
            except Exception: continue
            if not math.isfinite(value) or value<0: continue
            key=(round(lon,5),round(lat,5)); idx=point_index.get(key)
            if idx is None:
                d2,idx=min((((p['lon']-lon)**2+(p['lat']-lat)**2,i) for i,p in enumerate(points)))
                if d2>0.01**2: raise RuntimeError(f'FAIL_CLOSED_SAMPLE_LOCATION_MISMATCH {lon} {lat}')
            prior=observations.setdefault(tm,{}).get(idx)
            if prior is not None:
                duplicate_count+=1
                if abs(prior-value)>1e-9: raise RuntimeError(f'FAIL_CLOSED_CONFLICTING_DUPLICATE_SAMPLE {tm} {idx}')
            observations[tm][idx]=value
        cursor=bend
    slots=[start+timedelta(minutes=slot_minutes*i) for i in range(slot_count)]; candidates=[]
    for cid in ids:
        meta=metas[cid]; series=[]; valid=0
        for index,dt in enumerate(slots):
            tm=int(dt.timestamp()*1000); vals=observations.get(tm,{}); missing=[c for c in meta['cells'] if c['global_point_index'] not in vals]
            if missing: rate=accum=None
            else:
                rate=sum(vals[c['global_point_index']]*c['weight'] for c in meta['cells']); accum=rate*0.5; valid+=1
            series.append({'slot_index_0based':index,'time_utc':dt.isoformat().replace('+00:00','Z'),'rate_mm_hr':None if rate is None else round(rate,6),'accum_mm':None if accum is None else round(accum,6),'all_weighted_cells_present':not missing,'missing_weighted_cell_count':len(missing)})
        windows={}
        for w in plan['windows']:
            first=int(w['grid_start_index_0based']); last=int(w['grid_end_index_0based_inclusive']); chunk=series[first:last+1]
            if len(chunk)!=int(w['expected_slot_count']): raise RuntimeError(f'FAIL_CLOSED_WINDOW_INDEXING {cid} {w["id"]}')
            complete=all(r['accum_mm'] is not None for r in chunk)
            windows[w['id']]={'kind':w['kind'],'hours':w['hours'],'expected_slot_count':w['expected_slot_count'],'valid_slot_count':sum(r['accum_mm'] is not None for r in chunk),'complete':complete,'accum_mm':round(sum(r['accum_mm'] for r in chunk),6) if complete else None}
        candidates.append({'candidate_id':cid,'geometry_sha256':co['geometry']['required_geojson_sha256'],'intersecting_imerg_cell_count':len(meta['cells']),'spatial_weights':[{'lon':c['lon'],'lat':c['lat'],'intersection_area_m2':round(c['intersection_area_m2'],3),'weight':round(c['weight'],12)} for c in meta['cells']],'slot_count':len(series),'valid_slot_count':valid,'coverage_fraction':valid/slot_count,'windows':windows,'series':series})
    report={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_CHOSICA_2015_NEGATIVE_CONTROL_PREUNBLIND_IMERG','phase':'PREUNBLIND_NEGATIVE_CONTROL_PREDICTOR_RECONSTRUCTION','guards':GUARDS,'outcome_evidence_read':False,'candidate_outcome_evidence_read':False,'a6680_numeric_reference_read':False,'post_anchor_predictor_read':False,'sealed_target_unblind_performed':False,'control_outcome_adjudication_performed':False,'execution_contract':str(CONTRACT.relative_to(ROOT)),'source':execution['source'],'time_grid':plan['grid'],'anchor_utc':plan['anchor_utc'],'candidate_count':len(candidates),'geometry_geojson_sha256':co['geometry']['required_geojson_sha256'],'unique_imerg_cell_count':len(points),'request_count':request_count,'duplicate_sample_count':duplicate_count,'ignored_outside_grid_sample_count':ignored_outside_grid,'missingness_policy':execution['spatial_aggregation']['partial_cell_missingness'],'geometry_or_pour_point_modified':False,'candidate_replaced':False,'window_shifted':False,'zero_imputation_used':False,'candidates':candidates}
    if len(candidates)!=co['output']['required_candidate_count'] or any(c['slot_count']!=co['output']['required_slot_count_per_candidate'] for c in candidates): raise RuntimeError('FAIL_CLOSED_OUTPUT_DIMENSIONS')
    if any(r['time_utc']>=plan['anchor_utc'] for c in candidates for r in c['series']): raise RuntimeError('FAIL_CLOSED_POST_ANCHOR_OUTPUT')
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'candidate_count':report['candidate_count'],'coverage':{c['candidate_id']:round(c['coverage_fraction'],6) for c in candidates},'request_count':request_count},indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
