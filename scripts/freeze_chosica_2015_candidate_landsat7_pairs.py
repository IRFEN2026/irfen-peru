#!/usr/bin/env python3
"""Freeze deterministic metadata-only Landsat 7 pre/post pairs for blinded candidates."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(s: str): return datetime.fromisoformat(str(s).replace('Z','+00:00')).astimezone(timezone.utc)
def wrs(x):
    a=x.get('landsat_wrs_path');b=x.get('landsat_wrs_row')
    return None if a is None or b is None else (int(a),int(b))
def cloud(x):
    v=x.get('eo_cloud_cover')
    try: return float(v) if v is not None else None
    except Exception: return None
def key(pre,post,anchor):
    dp=(anchor-dt(pre['datetime'])).total_seconds();dq=(dt(post['datetime'])-anchor).total_seconds()
    cp,cq=cloud(pre),cloud(post);missing=0 if cp is not None and cq is not None else 1;csum=(cp+cq) if missing==0 else float('inf')
    return (dp+dq,max(dp,dq),missing,csum,str(pre['item_id']),str(post['item_id']))
def slim(x):
    return {k:x.get(k) for k in ('item_id','datetime','platform','instruments','eo_cloud_cover','landsat_wrs_path','landsat_wrs_row','landsat_scene_id','mirror_collection')}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--availability',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'));av=json.loads(a.availability.read_text(encoding='utf-8'))
    if sha(a.availability)!=co['availability_input']['sha256']: raise SystemExit('FAIL_CLOSED_AVAILABILITY_HASH')
    if av.get('status')!=co['availability_input']['required_status']: raise SystemExit('FAIL_CLOSED_AVAILABILITY_STATUS')
    for k in ('pixel_assets_read','asset_hrefs_read','surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','candidate_selection_modified','candidate_ranking_modified','surface_signal_used_for_scene_selection','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
        if av.get(k) is not False: raise SystemExit('FAIL_CLOSED_INPUT_GUARD_'+k)
    if av.get('candidate_count')!=co['expected']['candidate_count']: raise SystemExit('FAIL_CLOSED_CANDIDATE_COUNT')
    anchor=dt(co['event_anchor_utc']);pairs=[]
    for c in sorted(av['candidates'],key=lambda z:z['candidate_code']):
        eligible=[]
        for p in c['windows']['pre']['items']:
            if dt(p['datetime'])>=anchor: continue
            for q in c['windows']['post']['items']:
                if dt(q['datetime'])<anchor or wrs(p) is None or wrs(p)!=wrs(q): continue
                eligible.append((key(p,q,anchor),p,q))
        if not eligible: raise SystemExit('FAIL_CLOSED_NO_COMPATIBLE_PAIR_'+c['candidate_code'])
        eligible.sort(key=lambda z:z[0]);k,p,q=eligible[0]
        pairs.append({'candidate_code':c['candidate_code'],'pre':slim(p),'post':slim(q),'selection_key':{'total_anchor_distance_seconds':k[0],'max_anchor_distance_seconds':k[1],'cloud_metadata_missing_rank':k[2],'scene_cloud_cover_sum':None if k[2] else k[3]},'eligible_pair_count':len(eligible)})
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_LANDSAT7_METADATA_ONLY_SCENE_PAIRS','guards':co['guards'],'contract_sha256':sha(a.contract),'availability_sha256':sha(a.availability),'event_anchor_utc':co['event_anchor_utc'],'candidate_count':len(pairs),'pairs':pairs,'pixel_assets_read':False,'asset_hrefs_read':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'surface_signal_used_for_selection':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'candidate_count':len(pairs),'unique_scene_pairs':len({(x['pre']['item_id'],x['post']['item_id']) for x in pairs})},sort_keys=True))
if __name__=='__main__': main()
