#!/usr/bin/env python3
"""Discover transport-only mirror records for already-frozen USGS Landsat scenes.
No asset href is requested. Mirror metadata cannot change scene selection.
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
 co=json.loads(a.contract.read_text());ep=co['transport_mirror']['stac_search_endpoint'];u=urllib.parse.urlparse(ep)
 if u.scheme!='https' or u.hostname!=co['transport_mirror']['endpoint_host']: raise SystemExit('FAIL_CLOSED_MIRROR_ENDPOINT')
 sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.5','Content-Type':'application/json'})
 rows=[]
 for frozen in co['frozen_usgs_items']:
  day=frozen['date'];body={'collections':[co['transport_mirror']['collection']],'datetime':f'{day}T00:00:00Z/{day}T23:59:59Z','query':{'landsat:product_id':{'eq':frozen['usgs_product_id']}},'limit':10}
  r=sess.post(ep,json=body,timeout=(20,120),allow_redirects=False)
  if r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_MIRROR_REDIRECT')
  if r.status_code!=200: raise SystemExit(f'FAIL_CLOSED_MIRROR_HTTP_{r.status_code}_{day}')
  rb=r.content;doc=r.json();features=doc.get('features') or []
  matches=[]
  for f in features:
   p=f.get('properties') or {};pid=p.get('landsat:product_id')
   if pid==frozen['usgs_product_id']: matches.append(f)
  if len(matches)!=1: raise SystemExit(f'FAIL_CLOSED_MIRROR_CARDINALITY_{frozen["usgs_product_id"]}_{len(matches)}')
  f=matches[0];p=f.get('properties') or {};assets=f.get('assets') or {};out_assets=[]
  for key in co['required_asset_keys']:
   x=assets.get(key)
   if not isinstance(x,dict) or not isinstance(x.get('href'),str): raise SystemExit(f'FAIL_CLOSED_MIRROR_ASSET_{key}')
   hu=urllib.parse.urlparse(x['href'])
   if hu.scheme!='https' or not hu.hostname: raise SystemExit('FAIL_CLOSED_MIRROR_ASSET_URL')
   out_assets.append({'asset_key':key,'href':x['href'],'href_host':hu.hostname,'href_path':hu.path,'href_query_present':bool(hu.query),'file:checksum':x.get('file:checksum')})
  rows.append({'usgs_item_id':frozen['usgs_item_id'],'usgs_product_id':frozen['usgs_product_id'],'mirror_item_id':f.get('id'),'datetime':p.get('datetime'),'landsat:product_id':p.get('landsat:product_id'),'landsat:wrs_path':p.get('landsat:wrs_path'),'landsat:wrs_row':p.get('landsat:wrs_row'),'metadata_response_sha256':shab(rb),'assets':out_assets})
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_LANDSAT8_TRANSPORT_MIRROR_METADATA_ONLY','guards':co['guards'],'contract_sha256':shaf(a.contract),'mirror_provider':co['transport_mirror']['provider'],'mirror_role':'TRANSPORT_ONLY_NOT_SCIENTIFIC_SOURCE','item_count':len(rows),'items':rows,'pixel_bytes_read':False,'asset_href_requested':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'asset_acceptance_authorized':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'item_count':len(rows),'asset_hosts':sorted({x['href_host'] for i in rows for x in i['assets']})},sort_keys=True))
if __name__=='__main__':main()
