#!/usr/bin/env python3
"""Validate exact frozen Landsat acquisitions on a transport-only STAC mirror.
This stage reads item metadata only. It never requests asset hrefs or pixel bytes.
"""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse
from datetime import datetime
from pathlib import Path
import requests

def shaf(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

def shab(b: bytes) -> str: return hashlib.sha256(b).hexdigest()

def utc_date(value):
    if not isinstance(value,str): return None
    try:
        return datetime.fromisoformat(value.replace('Z','+00:00')).date().isoformat()
    except Exception:
        return value[:10] if len(value)>=10 else None

def as_int(v):
    try: return int(v)
    except Exception: return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'));tpl=co['transport_mirror']['item_endpoint_template']
    sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.7'})
    rows=[]
    for frozen in co['frozen_identity_map']:
        url=tpl.replace('{mirror_item_id}',urllib.parse.quote(frozen['mirror_item_id'],safe=''))
        u=urllib.parse.urlparse(url)
        if u.scheme!='https' or u.hostname!=co['transport_mirror']['endpoint_host']: raise SystemExit('FAIL_CLOSED_MIRROR_ENDPOINT')
        r=sess.get(url,timeout=(20,120),allow_redirects=False)
        if r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_MIRROR_REDIRECT')
        if r.status_code!=200: raise SystemExit(f'FAIL_CLOSED_MIRROR_HTTP_{r.status_code}_{frozen["mirror_item_id"]}')
        rb=r.content
        try: doc=json.loads(rb)
        except Exception: raise SystemExit('FAIL_CLOSED_MIRROR_NON_JSON')
        if doc.get('id')!=frozen['mirror_item_id']: raise SystemExit('FAIL_CLOSED_MIRROR_ITEM_ID')
        if doc.get('collection')!=co['transport_mirror']['collection']: raise SystemExit('FAIL_CLOSED_MIRROR_COLLECTION')
        if not str(doc.get('id','')).startswith(frozen['sensor_prefix']): raise SystemExit('FAIL_CLOSED_SENSOR_PREFIX')
        p=doc.get('properties') or {};dt=p.get('datetime') or p.get('start_datetime')
        if utc_date(dt)!=frozen['date']: raise SystemExit(f'FAIL_CLOSED_ACQUISITION_DATE_{dt}_{frozen["date"]}')
        wp=as_int(p.get('landsat:wrs_path'));wr=as_int(p.get('landsat:wrs_row'))
        if wp!=int(frozen['wrs_path']) or wr!=int(frozen['wrs_row']): raise SystemExit(f'FAIL_CLOSED_WRS_{wp}_{wr}')
        assets=doc.get('assets') or {};out_assets=[]
        for key in co['required_asset_keys']:
            x=assets.get(key)
            if not isinstance(x,dict) or not isinstance(x.get('href'),str): raise SystemExit(f'FAIL_CLOSED_MIRROR_ASSET_{key}')
            hu=urllib.parse.urlparse(x['href'])
            if hu.scheme!='https' or not hu.hostname: raise SystemExit('FAIL_CLOSED_MIRROR_ASSET_URL')
            out_assets.append({'asset_key':key,'href':x['href'],'href_host':hu.hostname,'href_path':hu.path,'href_query_present':bool(hu.query),'file:checksum':x.get('file:checksum'),'type':x.get('type')})
        rows.append({'usgs_item_id':frozen['usgs_item_id'],'usgs_product_id':frozen['usgs_product_id'],'mirror_item_id':doc.get('id'),'datetime':dt,'acquisition_utc_date':utc_date(dt),'landsat:wrs_path':wp,'landsat:wrs_row':wr,'item_response_sha256':shab(rb),'assets':out_assets})
    out={'schema_version':'0.3','batch_id':co['batch_id'],'status':'PASS_LANDSAT8_TRANSPORT_MIRROR_EXACT_ITEM_IMMUTABLE_METADATA_ONLY','guards':co['guards'],'contract_sha256':shaf(a.contract),'mirror_provider':co['transport_mirror']['provider'],'mirror_role':'TRANSPORT_ONLY_NOT_SCIENTIFIC_SOURCE','item_count':len(rows),'items':rows,'pixel_bytes_read':False,'asset_href_requested':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'asset_acceptance_authorized':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'item_count':len(rows),'asset_hosts':sorted({x['href_host'] for i in rows for x in i['assets']})},sort_keys=True))
if __name__=='__main__': main()
