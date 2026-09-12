#!/usr/bin/env python3
"""Inventory asset metadata for every unique Landsat 7 scene in the already-frozen windows."""
from __future__ import annotations
import argparse,hashlib,json,urllib.parse
from pathlib import Path
import requests

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def shab(b:bytes): return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--availability',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());av=json.loads(a.availability.read_text())
 if sha(a.availability)!=co['availability_input']['sha256'] or av.get('status')!=co['availability_input']['required_status']: raise SystemExit('FAIL_CLOSED_AVAILABILITY')
 for k in ('pixel_assets_read','asset_hrefs_read','surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','candidate_selection_modified','candidate_ranking_modified','surface_signal_used_for_scene_selection','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
  if av.get(k) is not False: raise SystemExit('FAIL_CLOSED_AVAILABILITY_GUARD_'+k)
 scenes={'pre':{},'post':{}}
 for c in av['candidates']:
  for wn in ('pre','post'):
   for x in c['windows'][wn]['items']:
    iid=x['item_id'];sig=(x['datetime'],int(x['landsat_wrs_path']),int(x['landsat_wrs_row']))
    if iid in scenes[wn] and scenes[wn][iid]!=sig: raise SystemExit('FAIL_CLOSED_SCENE_METADATA_INCONSISTENCY')
    scenes[wn][iid]=sig
 if len(scenes['pre'])!=co['scene_policy']['expected_unique_pre_scene_count'] or len(scenes['post'])!=co['scene_policy']['expected_unique_post_scene_count']: raise SystemExit('FAIL_CLOSED_SCENE_COUNT')
 tm=co['transport_mirror'];sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/l7-multiscene-inventory-0.1'});items=[]
 for wn in ('pre','post'):
  for iid in sorted(scenes[wn]):
   url=tm['item_endpoint_template'].replace('{item_id}',urllib.parse.quote(iid,safe=''));u=urllib.parse.urlparse(url)
   if u.scheme!='https' or u.hostname!=tm['endpoint_host'] or tm.get('tls_verify') is not True: raise SystemExit('FAIL_CLOSED_ENDPOINT')
   r=sess.get(url,timeout=(20,120),allow_redirects=False)
   if r.status_code!=200 or r.is_redirect or r.is_permanent_redirect: raise SystemExit('FAIL_CLOSED_HTTP_OR_REDIRECT')
   rb=r.content;doc=json.loads(rb)
   if doc.get('id')!=iid or doc.get('collection')!=tm['collection']: raise SystemExit('FAIL_CLOSED_IDENTITY')
   p=doc.get('properties') or {};assets=doc.get('assets') or {};rows=[]
   for key in co['required_asset_keys']:
    x=assets.get(key)
    if not isinstance(x,dict) or not isinstance(x.get('href'),str): raise SystemExit('FAIL_CLOSED_MISSING_ASSET_'+key)
    hu=urllib.parse.urlparse(x['href'])
    if hu.scheme!='https' or not hu.hostname: raise SystemExit('FAIL_CLOSED_ASSET_URL')
    rows.append({'asset_key':key,'href':x['href'],'href_host':hu.hostname,'href_path':hu.path,'href_query_present':bool(hu.query),'file:checksum':x.get('file:checksum'),'type':x.get('type')})
   items.append({'window':wn,'item_id':iid,'datetime':p.get('datetime') or p.get('start_datetime'),'landsat_wrs_path':p.get('landsat:wrs_path'),'landsat_wrs_row':p.get('landsat:wrs_row'),'item_response_sha256':shab(rb),'assets':rows})
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_LANDSAT7_ALL_FIXED_WINDOW_SCENE_ASSET_METADATA','guards':co['guards'],'contract_sha256':sha(a.contract),'availability_sha256':sha(a.availability),'pre_scene_count':len(scenes['pre']),'post_scene_count':len(scenes['post']),'items':items,'asset_href_metadata_read':True,'asset_href_requested':False,'pixel_bytes_read':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'pre_scene_count':out['pre_scene_count'],'post_scene_count':out['post_scene_count'],'item_count':len(items)},sort_keys=True))
if __name__=='__main__': main()
