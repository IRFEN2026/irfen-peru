#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,urllib.parse
from datetime import datetime
from pathlib import Path
import requests

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def shab(b:bytes): return hashlib.sha256(b).hexdigest()
def date(s): return datetime.fromisoformat(str(s).replace('Z','+00:00')).date().isoformat()
def asint(v):
 try:return int(v)
 except:return None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--availability',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());av=json.loads(a.availability.read_text())
 if sha(a.availability)!=co['availability_input']['sha256'] or av.get('status')!=co['availability_input']['required_status']:raise SystemExit('FAIL_CLOSED_AVAILABILITY')
 for k in ('pixel_assets_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','candidate_selection_modified','candidate_ranking_modified','surface_signal_used_for_scene_selection','free_web_search_used'):
  if av.get(k) is not False:raise SystemExit('FAIL_CLOSED_AVAILABILITY_GUARD_'+k)
 expected_pre=sorted({x['item_id'] for c in av['candidates'] for x in c['windows']['pre']['items']});expected_post=sorted({x['item_id'] for c in av['candidates'] for x in c['windows']['post']['items']})
 if len(expected_pre)!=2 or len(expected_post)!=3:raise SystemExit('FAIL_CLOSED_SCENE_COUNT')
 if sorted(x['usgs_item_id'] for x in co['identity_map'] if x['window']=='pre')!=expected_pre or sorted(x['usgs_item_id'] for x in co['identity_map'] if x['window']=='post')!=expected_post:raise SystemExit('FAIL_CLOSED_IDENTITY_MAP_NOT_EXACT_AVAILABILITY')
 tm=co['transport_mirror'];sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/l8-multiscene-mirror-0.1'});rows=[]
 for x in co['identity_map']:
  url=tm['item_endpoint_template'].replace('{mirror_item_id}',urllib.parse.quote(x['mirror_item_id'],safe=''));u=urllib.parse.urlparse(url)
  if u.scheme!='https' or u.hostname!=tm['endpoint_host'] or tm.get('tls_verify') is not True:raise SystemExit('FAIL_CLOSED_ENDPOINT')
  r=sess.get(url,timeout=(20,120),allow_redirects=False)
  if r.status_code!=200 or r.is_redirect or r.is_permanent_redirect:raise SystemExit('FAIL_CLOSED_MIRROR_HTTP')
  rb=r.content;doc=json.loads(rb);p=doc.get('properties') or {}
  if doc.get('id')!=x['mirror_item_id'] or doc.get('collection')!=tm['collection'] or date(p.get('datetime') or p.get('start_datetime'))!=x['date'] or asint(p.get('landsat:wrs_path'))!=x['wrs_path'] or asint(p.get('landsat:wrs_row'))!=x['wrs_row']:raise SystemExit('FAIL_CLOSED_IMMUTABLE_IDENTITY')
  assets=[]
  for key in co['required_asset_keys']:
   z=(doc.get('assets') or {}).get(key)
   if not isinstance(z,dict) or not isinstance(z.get('href'),str):raise SystemExit('FAIL_CLOSED_ASSET_'+key)
   hu=urllib.parse.urlparse(z['href'])
   if hu.scheme!='https' or not hu.hostname:raise SystemExit('FAIL_CLOSED_ASSET_URL')
   assets.append({'asset_key':key,'href':z['href'],'href_host':hu.hostname,'href_path':hu.path,'href_query_present':bool(hu.query),'file:checksum':z.get('file:checksum'),'type':z.get('type')})
  rows.append({'window':x['window'],'usgs_item_id':x['usgs_item_id'],'mirror_item_id':x['mirror_item_id'],'datetime':p.get('datetime') or p.get('start_datetime'),'wrs_path':asint(p.get('landsat:wrs_path')),'wrs_row':asint(p.get('landsat:wrs_row')),'item_response_sha256':shab(rb),'assets':assets})
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_LANDSAT8_ALL_FROZEN_WINDOW_SCENE_MIRROR_METADATA','guards':co['guards'],'contract_sha256':sha(a.contract),'availability_sha256':sha(a.availability),'item_count':len(rows),'pre_scene_count':sum(x['window']=='pre' for x in rows),'post_scene_count':sum(x['window']=='post' for x in rows),'items':rows,'pixel_bytes_read':False,'asset_href_requested':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'item_count':len(rows),'asset_hosts':sorted({a['href_host'] for x in rows for a in x['assets']})},sort_keys=True))
if __name__=='__main__':main()
