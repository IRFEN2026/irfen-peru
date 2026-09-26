#!/usr/bin/env python3
"""Inspect the second transport hop for frozen Landsat QA assets without reading bodies."""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse
from pathlib import Path
import requests, urllib3
from urllib3.exceptions import InsecureRequestWarning
urllib3.disable_warnings(InsecureRequestWarning)

def shaf(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()
def shab(s:str): return hashlib.sha256(s.encode()).hexdigest()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--freeze',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 co=json.loads(a.contract.read_text()); inv=json.loads(a.inventory.read_text()); fr=json.loads(a.freeze.read_text())
 if shaf(a.inventory)!=co['inputs']['asset_inventory_sha256']: raise SystemExit('FAIL_CLOSED_INVENTORY_HASH')
 if fr.get('status')!='FROZEN_TRANSPORT_FIRST_HOP_PATTERN_HEADERS_ONLY': raise SystemExit('FAIL_CLOSED_FIRST_HOP_FREEZE_STATUS')
 if inv.get('status')!='FROZEN_LANDSAT8_FROZEN_ITEM_ASSET_METADATA_INVENTORY': raise SystemExit('FAIL_CLOSED_INVENTORY_STATUS')
 for k in ('asset_href_requested','pixel_bytes_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','free_web_search_used','sealed_target_unblind_allowed'):
  if inv.get(k) is not False: raise SystemExit('FAIL_CLOSED_INVENTORY_GUARD_'+k)
 s=requests.Session();s.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.3'});rows=[]
 req=co['transport']['required_first_hop']
 for item in inv['items']:
  ms=[x for x in item['assets'] if x['asset_key']==co['inputs']['asset_key']]
  if len(ms)!=1: raise SystemExit('FAIL_CLOSED_QA_ASSET_CARDINALITY')
  origin=ms[0]['href'];u=urllib.parse.urlparse(origin)
  if u.scheme!='https' or u.hostname!='landsatlook.usgs.gov': raise SystemExit('FAIL_CLOSED_ORIGIN_SCOPE')
  with s.get(origin,stream=True,timeout=(20,120),allow_redirects=False,verify=False) as r1:
   loc1=r1.headers.get('Location')
   if not loc1 or int(r1.status_code) not in (301,302,303,307,308): raise SystemExit('FAIL_CLOSED_FIRST_HOP_NOT_REDIRECT')
   p1=urllib.parse.urlparse(loc1)
   if not (p1.scheme==req['scheme'] and p1.hostname==req['host'] and p1.path==req['path'] and bool(p1.query)==req['query_present']): raise SystemExit('FAIL_CLOSED_FIRST_HOP_PATTERN_CHANGED')
   with s.get(loc1,stream=True,timeout=(20,120),allow_redirects=False,verify=True) as r2:
    loc2=r2.headers.get('Location'); p2=urllib.parse.urlparse(loc2) if loc2 else None
    row={'item_id':item['id'],'origin_status':int(r1.status_code),'first_hop_host':p1.hostname,'first_hop_path':p1.path,'first_hop_query_present':bool(p1.query),'first_hop_location_sha256':shab(loc1),'second_status':int(r2.status_code),'second_is_redirect':bool(r2.is_redirect or r2.is_permanent_redirect),'second_tls_verification':True,'second_location_sha256':shab(loc2) if loc2 else None,'second_redirect_scheme':p2.scheme if p2 else None,'second_redirect_host':p2.hostname if p2 else None,'second_redirect_path':p2.path if p2 else None,'second_redirect_query_present':bool(p2.query) if p2 else False}
    rows.append(row)
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_TRANSPORT_SECOND_HOP_HEADERS_ONLY','guards':co['guards'],'contract_sha256':shaf(a.contract),'inventory_sha256':shaf(a.inventory),'first_hop_freeze_sha256':shaf(a.freeze),'response_body_read':False,'pixel_bytes_read':False,'free_web_search_used':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'qa_bits_or_thresholds_modified':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'asset_acceptance_authorized':False,'responses':rows}
 if len(rows)!=3 or any(not x['second_is_redirect'] or x['second_redirect_scheme']!='https' or not x['second_redirect_host'] for x in rows): out['status']='FAIL_CLOSED_UNEXPECTED_SECOND_HOP'
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'second_hosts':sorted({x['second_redirect_host'] for x in rows if x['second_redirect_host']})},sort_keys=True))
 if out['status'].startswith('FAIL_CLOSED'): raise SystemExit(2)
if __name__=='__main__':main()
