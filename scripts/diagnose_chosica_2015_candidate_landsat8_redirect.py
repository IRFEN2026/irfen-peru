#!/usr/bin/env python3
"""Inspect only redirect headers for frozen candidate Landsat QA_PIXEL assets.
No response body is read and redirects are not followed.
"""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse
from pathlib import Path
import requests

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--inventory',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text()); inv=json.loads(a.inventory.read_text())
    if sha256_file(a.inventory)!=co['input']['asset_inventory_sha256']: raise SystemExit('FAIL_CLOSED_INVENTORY_HASH')
    if inv.get('status')!='FROZEN_LANDSAT8_FROZEN_ITEM_ASSET_METADATA_INVENTORY': raise SystemExit('FAIL_CLOSED_INVENTORY_STATUS')
    for k in ('asset_href_requested','pixel_bytes_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','free_web_search_used','sealed_target_unblind_allowed'):
        if inv.get(k) is not False: raise SystemExit('FAIL_CLOSED_INVENTORY_GUARD_'+k)
    rows=[]; s=requests.Session(); s.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.1'})
    for item in inv['items']:
        matches=[x for x in item['assets'] if x['asset_key']==co['input']['asset_key']]
        if len(matches)!=1: raise SystemExit('FAIL_CLOSED_QA_ASSET_CARDINALITY')
        url=matches[0]['href']; u=urllib.parse.urlparse(url)
        if u.scheme!='https' or u.hostname!=co['input']['expected_origin_host']: raise SystemExit('FAIL_CLOSED_ORIGIN_HOST')
        with s.get(url,stream=True,timeout=(20,120),allow_redirects=False) as r:
            loc=r.headers.get('Location'); entry={'item_id':item['id'],'origin_scheme':u.scheme,'origin_host':u.hostname,'origin_path':u.path,'http_status':int(r.status_code),'is_redirect':bool(r.is_redirect or r.is_permanent_redirect)}
            if loc is not None:
                p=urllib.parse.urlparse(loc)
                entry['location_sha256']=sha256_bytes(loc.encode('utf-8'))
                entry['redirect_scheme']=p.scheme
                entry['redirect_host']=p.hostname
                entry['redirect_path']=p.path
                entry['redirect_query_present']=bool(p.query)
            else:
                entry['location_sha256']=None; entry['redirect_scheme']=None; entry['redirect_host']=None; entry['redirect_path']=None; entry['redirect_query_present']=False
            rows.append(entry)
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_TRANSPORT_REDIRECT_DIAGNOSTIC_HEADERS_ONLY','guards':co['guards'],'contract_sha256':sha256_file(a.contract),'inventory_sha256':sha256_file(a.inventory),'request_count':len(rows),'response_body_read':False,'redirect_followed':False,'free_web_search_used':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'qa_bits_or_thresholds_modified':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'responses':rows}
    if not rows or any(not x['is_redirect'] for x in rows): out['status']='FAIL_CLOSED_UNEXPECTED_TRANSPORT_RESPONSE'
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({'status':out['status'],'request_count':len(rows),'redirect_hosts':sorted({x['redirect_host'] for x in rows if x['redirect_host']})},sort_keys=True))
    if out['status'].startswith('FAIL_CLOSED'): raise SystemExit(2)
if __name__=='__main__': main()
