#!/usr/bin/env python3
"""Inventory metadata for assets of already-frozen Landsat 7 scene pairs; no asset request."""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
import requests

def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def shab(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def dt(s): return datetime.fromisoformat(str(s).replace('Z','+00:00')).astimezone(timezone.utc)
def as_int(v):
    try: return int(v)
    except Exception: return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--pairs',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'));pairs=json.loads(a.pairs.read_text(encoding='utf-8'))
    if sha(a.pairs)!=co['pair_input']['sha256']: raise SystemExit('FAIL_CLOSED_PAIR_HASH')
    if pairs.get('status')!=co['pair_input']['required_status'] or pairs.get('candidate_count')!=7: raise SystemExit('FAIL_CLOSED_PAIR_STATUS')
    for k in ('pixel_assets_read','asset_hrefs_read','surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','surface_signal_used_for_selection','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
        if pairs.get(k) is not False: raise SystemExit('FAIL_CLOSED_PAIR_GUARD_'+k)
    expected={}
    for row in pairs['pairs']:
        for role in ('pre','post'):
            x=row[role];iid=x['item_id'];sig=(x['datetime'],int(x['landsat_wrs_path']),int(x['landsat_wrs_row']))
            if iid in expected and expected[iid]!=sig: raise SystemExit('FAIL_CLOSED_PAIR_ITEM_INCONSISTENT')
            expected[iid]=sig
    tm=co['transport_mirror'];sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/l7-asset-metadata-0.1'});items=[]
    for iid in sorted(expected):
        url=tm['item_endpoint_template'].replace('{item_id}',urllib.parse.quote(iid,safe=''));u=urllib.parse.urlparse(url)
        if u.scheme!='https' or u.hostname!=tm['endpoint_host'] or tm.get('tls_verify') is not True: raise SystemExit('FAIL_CLOSED_ENDPOINT')
        r=sess.get(url,timeout=(20,120),allow_redirects=False)
        if r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_REDIRECT')
        if r.status_code!=200: raise SystemExit(f'FAIL_CLOSED_HTTP_{r.status_code}_{iid}')
        rb=r.content
        try: doc=json.loads(rb)
        except Exception: raise SystemExit('FAIL_CLOSED_NON_JSON')
        if doc.get('id')!=iid or doc.get('collection')!=tm['collection']: raise SystemExit('FAIL_CLOSED_ITEM_IDENTITY')
        p=doc.get('properties') or {};platform=str(p.get('platform') or '').lower().replace('_','-')
        if platform not in ('landsat-7','landsat7'): raise SystemExit('FAIL_CLOSED_PLATFORM')
        obs=(p.get('datetime') or p.get('start_datetime'),as_int(p.get('landsat:wrs_path')),as_int(p.get('landsat:wrs_row')))
        exp=expected[iid]
        if dt(obs[0])!=dt(exp[0]) or obs[1]!=exp[1] or obs[2]!=exp[2]: raise SystemExit('FAIL_CLOSED_IMMUTABLE_METADATA_MISMATCH')
        assets=doc.get('assets') or {};rows=[]
        for key in co['required_asset_keys']:
            x=assets.get(key)
            if not isinstance(x,dict) or not isinstance(x.get('href'),str): raise SystemExit('FAIL_CLOSED_MISSING_ASSET_'+key)
            hu=urllib.parse.urlparse(x['href'])
            if hu.scheme!='https' or not hu.hostname: raise SystemExit('FAIL_CLOSED_ASSET_URL_'+key)
            rows.append({'asset_key':key,'href':x['href'],'href_host':hu.hostname,'href_path':hu.path,'href_query_present':bool(hu.query),'file:checksum':x.get('file:checksum'),'type':x.get('type')})
        items.append({'item_id':iid,'datetime':obs[0],'platform':p.get('platform'),'landsat_wrs_path':obs[1],'landsat_wrs_row':obs[2],'item_response_sha256':shab(rb),'assets':rows})
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_LANDSAT7_FROZEN_PAIR_ASSET_METADATA_INVENTORY','guards':co['guards'],'contract_sha256':sha(a.contract),'pair_input_sha256':sha(a.pairs),'scientific_source':'USGS_LANDSAT_COLLECTION_2_LEVEL_2','transport_mirror_provider':tm['provider'],'transport_mirror_role':tm['role'],'item_count':len(items),'items':items,'asset_href_metadata_read':True,'asset_href_requested':False,'pixel_bytes_read':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'item_count':len(items),'assets_per_item':[len(x['assets']) for x in items],'asset_hosts':sorted({a['href_host'] for x in items for a in x['assets']}),'checksums_present':sum(a.get('file:checksum') is not None for x in items for a in x['assets'])},sort_keys=True))
if __name__=='__main__': main()
