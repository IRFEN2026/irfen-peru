#!/usr/bin/env python3
"""Freeze one deterministic metadata-only Landsat 8 pre/post pair per pseudonymous candidate."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path


def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(s: str): return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)
def stime(x): return x.get('datetime') or x.get('start_datetime')
def wrs(x):
    a=x.get('landsat_wrs_path'); b=x.get('landsat_wrs_row')
    return None if a is None or b is None else (str(a),str(b))
def cloud(x):
    v=x.get('eo_cloud_cover')
    try: return float(v) if v is not None else None
    except Exception: return None

def pair_key(pre,post,anchor):
    dp=(anchor-dt(stime(pre))).total_seconds(); dq=(dt(stime(post))-anchor).total_seconds()
    cp,cq=cloud(pre),cloud(post); missing=0 if cp is not None and cq is not None else 1; csum=(cp+cq) if missing==0 else float('inf')
    return (dp+dq,max(dp,dq),missing,csum,str(pre.get('item_id') or ''),str(post.get('item_id') or ''))

def slim(x):
    return {k:x.get(k) for k in ('item_id','datetime','start_datetime','end_datetime','platform','instruments','eo_cloud_cover','landsat_wrs_path','landsat_wrs_row','landsat_scene_id','landsat_product_id')}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--availability',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text()); av=json.loads(a.availability.read_text())
    if sha(a.availability)!=co['availability_input']['sha256']: raise SystemExit('FAIL_CLOSED_AVAILABILITY_HASH')
    if av.get('status')!='PASS_CANDIDATE_ONLY_LANDSAT8_AVAILABILITY_FROZEN_INPUTS': raise SystemExit('FAIL_CLOSED_AVAILABILITY_STATUS')
    for k in ('pixel_assets_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','candidate_selection_modified','candidate_ranking_modified','surface_signal_used_for_scene_selection','free_web_search_used','sealed_target_unblind_allowed'):
        if av.get(k) is not False: raise SystemExit('FAIL_CLOSED_INPUT_GUARD_'+k)
    anchor=dt(co['event_anchor_utc']); pairs=[]
    for c in sorted(av['candidates'],key=lambda z:z['candidate_code']):
        eligible=[]
        for p in c['windows']['pre']['items']:
            if dt(stime(p))>=anchor: continue
            for q in c['windows']['post']['items']:
                if dt(stime(q))<anchor: continue
                if wrs(p) is None or wrs(p)!=wrs(q): continue
                eligible.append((pair_key(p,q,anchor),p,q))
        if not eligible: raise SystemExit('FAIL_CLOSED_NO_COMPATIBLE_PAIR_'+c['candidate_code'])
        eligible.sort(key=lambda z:z[0]); key,p,q=eligible[0]
        pairs.append({'candidate_code':c['candidate_code'],'pre':slim(p),'post':slim(q),'selection_key':{'total_anchor_distance_seconds':key[0],'max_anchor_distance_seconds':key[1],'cloud_metadata_missing_rank':key[2],'scene_cloud_cover_sum':None if key[2] else key[3]},'eligible_pair_count':len(eligible)})
    if len(pairs)!=co['expected']['candidate_count']: raise SystemExit('FAIL_CLOSED_PAIR_COUNT')
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_LANDSAT8_METADATA_ONLY_SCENE_PAIRS','guards':co['guards'],'contract_sha256':sha(a.contract),'availability_sha256':sha(a.availability),'event_anchor_utc':co['event_anchor_utc'],'candidate_count':len(pairs),'pairs':pairs,'pixel_assets_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'surface_signal_used_for_selection':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({'status':out['status'],'candidate_count':len(pairs),'unique_scene_pairs':len({(x['pre']['item_id'],x['post']['item_id']) for x in pairs})},sort_keys=True))
if __name__=='__main__': main()
