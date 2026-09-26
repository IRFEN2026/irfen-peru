#!/usr/bin/env python3
"""Resolve exact pre-frozen USGS Landsat scenes on a transport-only mirror.
No asset href is requested and no pixel bytes are read.
"""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse
from pathlib import Path
import requests

def shaf(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()
def shab(b:bytes): return hashlib.sha256(b).hexdigest()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 co=json.loads(a.contract.read_text());tpl=co['transport_mirror']['item_endpoint_template'];sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.6'})
 rows=[]
 for frozen in co['frozen_identity_map']:
  url=tpl.replace('{mirror_item_id}',urllib.parse.quote(frozen['mirror_item_id'],safe=''));u=urllib.parse.urlparse(url)
  if u.scheme!='https' or u.hostname!=co['transport_mirror']['endpoint_host']: raise SystemExit('FAIL_CLOSED_MIRROR_ENDPOINT')
  r=sess.get(url,timeout=(20,120),allow_redirects=False)
  if r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_MIRROR_REDIRECT')
  if r.status_code!=200: raise SystemExit(f'FAIL_CLOSED_MIRROR_HTTP_{r.status_code}_{frozen["mirror_item_id"]}')
  rb=r.content;doc=r.json()
  if doc.get('id')!=frozen['mirror_item_id'] or doc.get('collection')!=co['transport_mirror']['collection']: raise SystemExit('FAIL_CLOSED_MIRROR_IDENTITY')
  p=doc.get('properties') or {};pid=p.get('landsat:product_id')
  if pid!=frozen['usgs_product_id']: raise SystemExit(f'FAIL_CLOSED_PRODUCT_ID_{pid}_{frozen["usgs_product_id"]}')
  assets=doc.get('assets') or {};out_assets=[]
  for key in co['required_asset_keys']:
   x=assets.get(key)
   if not isinstance(x,dict) or not isinstance(x.get('href'),str): raise SystemExit(f'FAIL_CLOSED_MIRROR_ASSET_{key}')
   hu=urllib.parse.urlparse(x['href'])
   if hu.scheme!='https' or not hu.hostname: raise SystemExit('FAIL_CLOSED_MIRROR_ASSET_URL')
   out_assets.append({'asset_key':key,'href':x['href'],'href_host':hu.hostname,'href_path':hu.path,'href_query_present':bool(hu.query),'file:checksum':x.get('file:checksum')})
  rows.append({'usgs_item_id':frozen['usgs_item_id'],'usgs_product_id':frozen['usgs_product_id'],'mirror_item_id':doc.get('id'),'datetime':p.get('datetime'),'landsat:product_id':pid,'landsat:wrs_path':p.get('landsat:wrs_path'),'landsat:wrs_row':p.get('landsat:wrs_row'),'item_response_sha256':shab(rb),'assets':out_assets})
 out={'schema_version':'0.2','batch_id':co['batch_id'],'status':'PASS_LANDSAT8_TRANSPORT_MIRROR_EXACT_ITEM_METADATA_ONLY','guards':co['guards'],'contract_sha256':shaf(a.contract),'mirror_provider':co['transport_mirror']['provider'],'mirror_role':'TRANSPORT_ONLY_NOT_SCIENTIFIC_SOURCE','item_count':len(rows),'items':rows,'pixel_bytes_read':False,'asset_href_requested':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'asset_acceptance_authorized':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'item_count':len(rows),'asset_hosts':sorted({x['href_host'] for i in rows for x in i['assets']})},sort_keys=True))
if __name__=='__main__':main()
