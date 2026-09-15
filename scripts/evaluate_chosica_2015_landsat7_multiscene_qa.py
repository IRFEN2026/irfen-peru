#!/usr/bin/env python3
"""Evaluate precommitted all-scene Landsat 7 redundant QA for blinded candidates."""
from __future__ import annotations
import argparse,hashlib,json,tempfile,urllib.parse
from pathlib import Path
import numpy as np, planetary_computer, rasterio, requests
from rasterio.features import geometry_mask
from rasterio.warp import reproject,Resampling,transform_geom

def sha256(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()
def sign(unsigned,host):
 u=urllib.parse.urlparse(unsigned)
 if u.scheme!='https' or u.hostname!=host or u.query: raise RuntimeError('FAIL_CLOSED_UNSIGNED_URL')
 s=planetary_computer.sign_url(unsigned);q=urllib.parse.urlparse(s)
 if q.scheme!='https' or q.hostname!=u.hostname or q.path!=u.path or not q.query: raise RuntimeError('FAIL_CLOSED_SIGNED_URL')
 return s
def dl(sess,url,p,host):
 h=hashlib.sha512();n=0
 with sess.get(sign(url,host),stream=True,timeout=(20,300),allow_redirects=False) as r:
  if r.status_code!=200 or r.is_redirect or r.is_permanent_redirect: raise RuntimeError('FAIL_CLOSED_ASSET_HTTP')
  with p.open('wb') as f:
   for c in r.iter_content(1<<20):
    if c:f.write(c);h.update(c);n+=len(c)
 if n<=0:raise RuntimeError('FAIL_CLOSED_EMPTY_ASSET')
 return h.hexdigest(),n
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());inv=json.loads(a.inventory.read_text());gj=json.loads(a.geometry.read_text())
 if sha256(a.inventory)!=co['inputs']['inventory']['sha256'] or inv.get('status')!=co['inputs']['inventory']['required_status']: raise SystemExit('FAIL_CLOSED_INVENTORY')
 if sha256(a.geometry)!=co['inputs']['candidate_geometry']['sha256'] or len(gj.get('features',[]))!=7: raise SystemExit('FAIL_CLOSED_GEOMETRY')
 for k in ('asset_href_requested','pixel_bytes_read','surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
  if inv.get(k) is not False: raise SystemExit('FAIL_CLOSED_INPUT_GUARD_'+k)
 items=sorted(inv['items'],key=lambda x:(0 if x['window']=='pre' else 1,x['datetime'],x['item_id']));pre=[x for x in items if x['window']=='pre'];post=[x for x in items if x['window']=='post']
 if len(pre)!=3 or len(post)!=4:raise SystemExit('FAIL_CLOSED_SCENE_COUNT')
 sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/l7-allscene-qa-0.1'});prov={};paths={}
 with tempfile.TemporaryDirectory(prefix='irfen_l7multiqa_') as raw:
  td=Path(raw)
  for x in items:
   amap={z['asset_key']:z for z in x['assets']}
   for key in co['allowed_asset_keys']:
    z=amap[key];p=td/f"{x['item_id']}_{key}.tif";dig,n=dl(sess,z['href'],p,co['transport']['unsigned_asset_host']);paths[(x['item_id'],key)]=p;prov[f"{x['item_id']}::{key}"]={'sha512':dig,'bytes':n,'full_file_hash_completed_before_raster_read':True,'signed_url_persisted':False,'signed_url_logged':False}
  refitem=pre[0]
  with rasterio.open(paths[(refitem['item_id'],'qa_pixel')]) as ds:ref={'crs':ds.crs,'transform':ds.transform,'width':ds.width,'height':ds.height}
  shape=(ref['height'],ref['width']);invalid=sum(1<<b for b in co['qa_pixel_invalid_bits']);valids={'pre':[],'post':[]}
  for x in items:
   arrs={}
   for key in co['allowed_asset_keys']:
    with rasterio.open(paths[(x['item_id'],key)]) as ds:
     src=ds.read(1)
     if ds.crs==ref['crs'] and ds.transform==ref['transform'] and ds.width==ref['width'] and ds.height==ref['height']:arr=src
     else:
      arr=np.full(shape,1,dtype=src.dtype);reproject(source=src,destination=arr,src_transform=ds.transform,src_crs=ds.crs,src_nodata=ds.nodata,dst_transform=ref['transform'],dst_crs=ref['crs'],dst_nodata=1,resampling=Resampling.nearest)
    arrs[key]=arr
   v=(np.bitwise_and(arrs['qa_pixel'].astype('uint32'),invalid)==0)&(arrs['qa_radsat'].astype('uint32')==0);valids[x['window']].append(v)
  pc=np.sum(np.stack(valids['pre']),axis=0,dtype='uint8');qc=np.sum(np.stack(valids['post']),axis=0,dtype='uint8');rule=co['composite_quality_rule'];rows=[]
  for f in sorted(gj['features'],key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
   code=(f.get('properties') or {}).get('candidate_code');geom=transform_geom('EPSG:4326',ref['crs'],f['geometry'],precision=3);cm=geometry_mask([geom],out_shape=shape,transform=ref['transform'],all_touched=False,invert=True);tot=int(cm.sum());preok=(pc>=int(rule['minimum_valid_observations_per_pixel_pre']))&cm;postok=(qc>=int(rule['minimum_valid_observations_per_pixel_post']))&cm;both=preok&postok;pf=float(preok.sum()/tot) if tot else 0.;qf=float(postok.sum()/tot) if tot else 0.;bf=float(both.sum()/tot) if tot else 0.;passed=tot>=int(rule['minimum_candidate_pixels']) and pf>=float(rule['minimum_fraction_with_required_pre_redundancy']) and qf>=float(rule['minimum_fraction_with_required_post_redundancy']) and bf>=float(rule['minimum_fraction_with_required_redundancy_both_periods']);rows.append({'candidate_code':code,'candidate_pixel_count':tot,'fraction_required_pre_redundancy':round(pf,6),'fraction_required_post_redundancy':round(qf,6),'fraction_required_both_periods':round(bf,6),'qa_status':co['candidate_status_if_pass'] if passed else co['candidate_status_if_fail']})
 usable=sum(x['qa_status']==co['candidate_status_if_pass'] for x in rows);out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_LANDSAT7_ALL_SCENE_REDUNDANT_QA' if usable>=co['minimum_usable_candidates_to_continue'] else 'FAIL_CLOSED_LANDSAT7_ALL_SCENE_NO_USABLE_CANDIDATES','guards':co['guards'],'contract_sha256':sha256(a.contract),'inventory_sha256':sha256(a.inventory),'candidate_geometry_sha256':sha256(a.geometry),'asset_provenance':prov,'candidate_count':len(rows),'usable_candidate_count':usable,'candidates':rows,'all_fixed_scenes_used':True,'scene_dropping_performed':False,'scene_replacement_performed':False,'slc_off_gap_imputation_used':False,'reflectance_asset_bytes_read':False,'surface_signal_observed':False,'outcome_labels_assigned':False,'target_names_or_ids_read':False,'target_outcomes_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'usable_candidate_count':usable,'candidate_count':len(rows)},sort_keys=True));raise SystemExit(0 if usable>=co['minimum_usable_candidates_to_continue'] else 3)
if __name__=='__main__': main()
