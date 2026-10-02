#!/usr/bin/env python3
"""Query fixed candidate-only USGS Landsat STAC metadata windows; never read pixel assets."""
from __future__ import annotations
import argparse, hashlib, json, re, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
import requests

FORBIDDEN = ("a6680","official_outcome_evidence","pedregal","quirio","carossio","carosio","rayos de sol","cashahuacra","la libertad")
CODE_RE = re.compile(r"^C_[0-9a-f]{12}$")

def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: Path) -> str: return sha_bytes(p.read_bytes())
def pick(p, *keys):
    for k in keys:
        if k in p and p[k] not in (None, ""): return p[k]
    return None

def parse_utc(s):
    if not s: return None
    return datetime.fromisoformat(str(s).replace('Z','+00:00')).astimezone(timezone.utc)

def is_l8(item):
    p=item.get('properties') or {}; iid=str(item.get('id') or '')
    platform=str(p.get('platform') or '').lower().replace('_','-')
    return iid.startswith('LC08_') or platform in ('landsat-8','landsat8')

def normalize(item, response_sha):
    p=item.get('properties') or {}
    return {
      'item_id': item.get('id'),
      'datetime': pick(p,'datetime'),
      'start_datetime': pick(p,'start_datetime'),
      'end_datetime': pick(p,'end_datetime'),
      'platform': pick(p,'platform'),
      'instruments': pick(p,'instruments'),
      'eo_cloud_cover': pick(p,'eo:cloud_cover','cloud_cover'),
      'landsat_wrs_path': pick(p,'landsat:wrs_path','wrs_path'),
      'landsat_wrs_row': pick(p,'landsat:wrs_row','wrs_row'),
      'landsat_scene_id': pick(p,'landsat:scene_id','scene_id'),
      'landsat_product_id': pick(p,'landsat:product_id','product_id'),
      'metadata_response_sha256': response_sha
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--geometry',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text(encoding='utf-8')); raw=a.geometry.read_bytes()
    if sha_bytes(raw)!=co['candidate_geometry']['sha256']: raise SystemExit('FAIL_CLOSED_GEOMETRY_HASH')
    low=raw.lower()
    if any(x.encode() in low for x in FORBIDDEN): raise SystemExit('FAIL_CLOSED_REVEALING_GEOMETRY_CONTENT')
    gj=json.loads(raw); feats=gj.get('features',[])
    if len(feats)!=co['candidate_geometry']['candidate_count']: raise SystemExit('FAIL_CLOSED_CANDIDATE_COUNT')
    endpoint=co['source']['stac_search_endpoint']; u=urllib.parse.urlparse(endpoint)
    if u.scheme!='https' or u.hostname!=co['source']['endpoint_host']: raise SystemExit('FAIL_CLOSED_ENDPOINT')
    if co['source'].get('http_method')!='POST': raise SystemExit('FAIL_CLOSED_TRANSPORT_METHOD')
    anchor=parse_utc(co['event_anchor_utc']); session=requests.Session(); session.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.1'})
    rows=[]
    for f in sorted(feats,key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
        code=(f.get('properties') or {}).get('candidate_code')
        if not isinstance(code,str) or CODE_RE.fullmatch(code) is None: raise SystemExit('FAIL_CLOSED_CANDIDATE_CODE')
        cand={'candidate_code':code,'windows':{}}
        for wn in ('pre','post'):
            w=co['fixed_windows'][wn]
            body={'collections':[co['source']['collection']], 'intersects':f['geometry'], 'datetime':f"{w['start']}/{w['end']}", 'limit':int(co['query']['max_results'])}
            r=session.post(endpoint,json=body,timeout=(20,120),allow_redirects=False)
            if r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_REDIRECT')
            if r.status_code!=200: raise SystemExit(f"FAIL_CLOSED_HTTP_{r.status_code}")
            rb=r.content; digest=sha_bytes(rb)
            try: doc=r.json()
            except Exception: raise SystemExit('FAIL_CLOSED_NON_JSON')
            if doc.get('type')!='FeatureCollection' or not isinstance(doc.get('features'),list): raise SystemExit('FAIL_CLOSED_NON_STAC_FEATURECOLLECTION')
            items=[normalize(x,digest) for x in doc['features'] if is_l8(x)]
            items.sort(key=lambda x:(str(x.get('datetime') or x.get('start_datetime') or ''),str(x.get('item_id') or '')))
            for it in items:
                dt=parse_utc(it.get('datetime') or it.get('start_datetime'))
                if dt is None: raise SystemExit('FAIL_CLOSED_SCENE_TIME_MISSING')
                if wn=='pre' and not dt < anchor: raise SystemExit('FAIL_CLOSED_PRE_SCENE_NOT_PREANCHOR')
                if wn=='post' and not dt >= anchor: raise SystemExit('FAIL_CLOSED_POST_SCENE_NOT_POSTANCHOR')
            cand['windows'][wn]={'query_response_sha256':digest,'returned_feature_count':len(doc['features']),'landsat8_result_count':len(items),'items':items}
        pre=cand['windows']['pre']['items']; post=cand['windows']['post']['items']
        def wrs(x):
            p=x.get('landsat_wrs_path'); q=x.get('landsat_wrs_row')
            return None if p is None or q is None else (str(p),str(q))
        common=sorted(({wrs(x) for x in pre if wrs(x) is not None}) & ({wrs(x) for x in post if wrs(x) is not None}))
        cand['common_wrs_path_rows']=[{'wrs_path':x[0],'wrs_row':x[1]} for x in common]
        cand['same_wrs_bracketing_available']=bool(common); rows.append(cand)
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_CANDIDATE_ONLY_LANDSAT8_AVAILABILITY_FROZEN_INPUTS','guards':co['guards'],'contract_sha256':sha_file(a.contract),'candidate_geometry_sha256':sha_file(a.geometry),'event_anchor_utc':co['event_anchor_utc'],'fixed_windows':co['fixed_windows'],'candidate_count':len(rows),'candidates':rows,'pixel_assets_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'surface_signal_used_for_scene_selection':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'candidate_count':len(rows),'with_same_wrs_bracketing':sum(x['same_wrs_bracketing_available'] for x in rows),'total_l8_pre':sum(x['windows']['pre']['landsat8_result_count'] for x in rows),'total_l8_post':sum(x['windows']['post']['landsat8_result_count'] for x in rows)},sort_keys=True))
if __name__=='__main__': main()
