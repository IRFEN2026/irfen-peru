#!/usr/bin/env python3
"""Recover alternate Landsat asset metadata using exact previously frozen STAC response hashes.
No asset href is requested; no pixel content is read.
"""
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
def shab(b:bytes): return hashlib.sha256(b).hexdigest()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 co=json.loads(a.contract.read_text());inv=json.loads(a.inventory.read_text())
 if shaf(a.inventory)!=co['input']['asset_inventory_sha256']: raise SystemExit('FAIL_CLOSED_INVENTORY_HASH')
 if inv.get('status')!='FROZEN_LANDSAT8_FROZEN_ITEM_ASSET_METADATA_INVENTORY': raise SystemExit('FAIL_CLOSED_INVENTORY_STATUS')
 for k in ('asset_href_requested','pixel_bytes_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','free_web_search_used','sealed_target_unblind_allowed'):
  if inv.get(k) is not False: raise SystemExit('FAIL_CLOSED_INVENTORY_GUARD_'+k)
 keep=set(co['retention']['asset_keys']);tpl=co['source']['item_endpoint_template'];sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.4'})
 items=[]
 for frozen in inv['items']:
  iid=frozen['id'];url=tpl.replace('{item_id}',urllib.parse.quote(iid,safe=''));u=urllib.parse.urlparse(url)
  if u.scheme!='https' or u.hostname!=co['source']['endpoint_host']: raise SystemExit('FAIL_CLOSED_ENDPOINT_SCOPE')
  r=sess.get(url,timeout=(20,120),allow_redirects=False,verify=False)
  if r.is_redirect or r.is_permanent_redirect or r.status_code!=200: raise SystemExit(f'FAIL_CLOSED_METADATA_HTTP_{r.status_code}_{iid}')
  rb=r.content;digest=shab(rb)
  if digest!=frozen['item_metadata_response_sha256']: raise SystemExit(f'FAIL_CLOSED_METADATA_RESPONSE_HASH_{iid}_{digest}')
  try:doc=json.loads(rb)
  except Exception: raise SystemExit('FAIL_CLOSED_METADATA_JSON_'+iid)
  if doc.get('id')!=iid or doc.get('collection')!='landsat-c2l2-sr': raise SystemExit('FAIL_CLOSED_METADATA_IDENTITY')
  out_assets=[]
  for key in sorted(keep):
   x=(doc.get('assets') or {}).get(key)
   if not isinstance(x,dict): raise SystemExit(f'FAIL_CLOSED_MISSING_ASSET_{iid}_{key}')
   alt=x.get('alternate')
   normalized={}
   if isinstance(alt,dict):
    for name,v in sorted(alt.items()):
     if not isinstance(v,dict): continue
     normalized[name]={k:v.get(k) for k in co['retention']['alternate_subfields'] if k in v}
   out_assets.append({'asset_key':key,'canonical_href':x.get('href'),'file:checksum':x.get('file:checksum'),'alternate':normalized})
  items.append({'id':iid,'item_metadata_response_sha256':digest,'assets':out_assets})
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_FROZEN_LANDSAT8_ALTERNATE_ASSET_METADATA_INVENTORY','guards':co['guards'],'contract_sha256':shaf(a.contract),'prior_inventory_sha256':shaf(a.inventory),'item_count':len(items),'items':items,'metadata_response_hashes_verified_exact':True,'origin_tls_certificate_verification':False,'asset_href_requested':False,'pixel_bytes_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'alternate_names':sorted({n for i in items for x in i['assets'] for n in x['alternate']})},sort_keys=True))
if __name__=='__main__':main()
