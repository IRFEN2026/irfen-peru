#!/usr/bin/env python3
"""Inventory metadata for exactly three frozen Landsat items; never request asset hrefs."""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse
from pathlib import Path
import requests

def sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def sha_bytes(b: bytes): return hashlib.sha256(b).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text()); tpl=co['source']['item_endpoint_template']
    pu=urllib.parse.urlparse(tpl.replace('{item_id}','X'))
    if pu.scheme!='https' or pu.hostname!=co['source']['endpoint_host']: raise SystemExit('FAIL_CLOSED_ENDPOINT')
    if co['source']['http_method']!='GET': raise SystemExit('FAIL_CLOSED_METHOD')
    sess=requests.Session(); sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.1'})
    items=[]
    for iid in co['frozen_item_ids']:
        url=tpl.replace('{item_id}',urllib.parse.quote(iid,safe=''))
        r=sess.get(url,timeout=(20,120),allow_redirects=False)
        if r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_REDIRECT')
        if r.status_code!=200: raise SystemExit(f'FAIL_CLOSED_HTTP_{r.status_code}_{iid}')
        rb=r.content; digest=sha_bytes(rb)
        try: doc=r.json()
        except Exception: raise SystemExit('FAIL_CLOSED_NON_JSON_'+iid)
        if doc.get('id')!=iid: raise SystemExit('FAIL_CLOSED_ITEM_ID_MISMATCH')
        if doc.get('collection')!=co['source']['collection']: raise SystemExit('FAIL_CLOSED_COLLECTION_MISMATCH')
        p=doc.get('properties') or {}; assets=[]
        for key in sorted((doc.get('assets') or {}).keys()):
            x=(doc.get('assets') or {})[key] or {}
            href=x.get('href')
            if not isinstance(href,str) or not href.startswith('https://'): continue
            assets.append({'asset_key':key,'href':href,'type':x.get('type'),'title':x.get('title'),'description':x.get('description'),'roles':x.get('roles'),'eo:bands':x.get('eo:bands'),'raster:bands':x.get('raster:bands'),'file:checksum':x.get('file:checksum'),'file:size':x.get('file:size')})
        items.append({'id':iid,'collection':doc.get('collection'),'datetime':p.get('datetime'),'landsat:wrs_path':p.get('landsat:wrs_path'),'landsat:wrs_row':p.get('landsat:wrs_row'),'item_metadata_response_sha256':digest,'asset_count':len(assets),'assets':assets})
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_LANDSAT8_FROZEN_ITEM_ASSET_METADATA_INVENTORY','guards':co['guards'],'contract_sha256':sha(a.contract),'item_count':len(items),'items':items,'asset_href_requested':False,'pixel_bytes_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({'status':out['status'],'item_count':len(items),'asset_counts':[x['asset_count'] for x in items]},sort_keys=True))
if __name__=='__main__': main()
