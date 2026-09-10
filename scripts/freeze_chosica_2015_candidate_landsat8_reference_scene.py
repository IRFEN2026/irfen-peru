#!/usr/bin/env python3
"""Freeze an earlier pre-event Landsat reference scene for each pseudonymous candidate."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(s): return datetime.fromisoformat(str(s).replace('Z','+00:00')).astimezone(timezone.utc)
def stime(x): return x.get('datetime') or x.get('start_datetime')
def wrs(x): return (str(x.get('landsat_wrs_path')),str(x.get('landsat_wrs_row')))
def cloud(x):
    try: return float(x.get('eo_cloud_cover')) if x.get('eo_cloud_cover') is not None else None
    except Exception: return None
def slim(x): return {k:x.get(k) for k in ('item_id','datetime','start_datetime','end_datetime','platform','instruments','eo_cloud_cover','landsat_wrs_path','landsat_wrs_row','landsat_scene_id','landsat_product_id')}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--availability',type=Path,required=True); ap.add_argument('--pairs',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text()); av=json.loads(a.availability.read_text()); pairs=json.loads(a.pairs.read_text())
    if sha(a.availability)!=co['availability_input']['sha256']: raise SystemExit('FAIL_CLOSED_AVAILABILITY_HASH')
    if sha(a.pairs)!=co['pair_input']['sha256']: raise SystemExit('FAIL_CLOSED_PAIR_HASH')
    bad=('pixel_assets_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','surface_signal_used_for_selection','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','sealed_target_unblind_allowed')
    for k in bad:
        if pairs.get(k) is not False: raise SystemExit('FAIL_CLOSED_PAIR_GUARD_'+k)
    avmap={x['candidate_code']:x for x in av['candidates']}; outrows=[]
    for p in sorted(pairs['pairs'],key=lambda z:z['candidate_code']):
        code=p['candidate_code']; selected_pre=p['pre']; selected_dt=dt(stime(selected_pre)); selected_wrs=wrs(selected_pre)
        candidates=[]
        for x in avmap[code]['windows']['pre']['items']:
            xd=dt(stime(x))
            if xd>=selected_dt or wrs(x)!=selected_wrs: continue
            cv=cloud(x); candidates.append(((selected_dt-xd).total_seconds(),0 if cv is not None else 1,float('inf') if cv is None else cv,str(x.get('item_id') or '')),x)
        if not candidates: raise SystemExit('FAIL_CLOSED_NO_EARLIER_REFERENCE_'+code)
        candidates.sort(key=lambda z:z[0]); key,x=candidates[0]
        outrows.append({'candidate_code':code,'reference':slim(x),'frozen_pre_item_id':selected_pre['item_id'],'selection_key':{'seconds_before_frozen_pre':key[0],'cloud_metadata_missing_rank':key[1],'scene_cloud_cover':None if key[1] else key[2]},'eligible_reference_count':len(candidates)})
    if len(outrows)!=co['expected_candidate_count']: raise SystemExit('FAIL_CLOSED_REFERENCE_COUNT')
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_LANDSAT8_PRE_EVENT_REFERENCE_SCENES','guards':co['guards'],'contract_sha256':sha(a.contract),'availability_sha256':sha(a.availability),'pair_manifest_sha256':sha(a.pairs),'candidate_count':len(outrows),'references':outrows,'pixel_assets_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'surface_signal_used_for_selection':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({'status':out['status'],'candidate_count':len(outrows),'unique_reference_scenes':len({x['reference']['item_id'] for x in outrows})},sort_keys=True))
if __name__=='__main__': main()
