#!/usr/bin/env python3
"""Threshold-free candidate-only Landsat 8 all-scene descriptive composite."""
from __future__ import annotations
import argparse,hashlib,json,tempfile,urllib.parse,warnings
from pathlib import Path
import numpy as np,planetary_computer,rasterio,requests
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling,transform_geom

def sha256(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()
def sign(url,host):
 u=urllib.parse.urlparse(url)
 if u.scheme!='https' or u.hostname!=host or u.query:raise RuntimeError('FAIL_CLOSED_UNSIGNED_ASSET_SCOPE')
 s=planetary_computer.sign_url(url);q=urllib.parse.urlparse(s)
 if q.scheme!='https' or q.hostname!=u.hostname or q.path!=u.path or not q.query:raise RuntimeError('FAIL_CLOSED_SIGNED_URL_INVARIANT')
 return s
def dl(sess,url,p,host):
 h=hashlib.sha512();n=0
 with sess.get(sign(url,host),stream=True,timeout=(20,300),allow_redirects=False) as r:
  if r.status_code!=200 or r.is_redirect or r.is_permanent_redirect:raise RuntimeError('FAIL_CLOSED_ASSET_HTTP')
  with p.open('wb') as f:
   for c in r.iter_content(1<<20):
    if c:f.write(c);h.update(c);n+=len(c)
 if n<=0:raise RuntimeError('FAIL_CLOSED_EMPTY_ASSET')
 return h.hexdigest(),n
def stats(pre,post):
 d=post-pre
 return {k:round(float(v),8) for k,v in {'pre_median':np.median(pre),'post_median':np.median(post),'delta_median':np.median(d),'delta_p10':np.quantile(d,.1),'delta_p25':np.quantile(d,.25),'delta_p75':np.quantile(d,.75),'delta_p90':np.quantile(d,.9)}.items()}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());inv=json.loads(a.inventory.read_text());gj=json.loads(a.geometry.read_text())
 if sha256(a.inventory)!=co['inputs']['inventory']['sha256'] or inv.get('status')!=co['inputs']['inventory']['required_status']:raise SystemExit('FAIL_CLOSED_INVENTORY')
 if sha256(a.geometry)!=co['inputs']['candidate_geometry']['sha256'] or len(gj.get('features',[]))!=co['inputs']['candidate_geometry']['candidate_count']:raise SystemExit('FAIL_CLOSED_GEOMETRY')
 for k in ('pixel_bytes_read','asset_href_requested','surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
  if inv.get(k) is not False:raise SystemExit('FAIL_CLOSED_INPUT_GUARD_'+k)
 items=sorted(inv['items'],key=lambda x:(0 if x['window']=='pre' else 1,x['datetime'],x['mirror_item_id']));pre=[x for x in items if x['window']=='pre'];post=[x for x in items if x['window']=='post']
 if len(pre)!=2 or len(post)!=3:raise SystemExit('FAIL_CLOSED_SCENE_COUNT')
 sess=requests.Session();sess.headers.update({'User-Agent':'IRFEN-research-cleanroom/l8-allscene-descriptive-0.1'});paths={};prov={}
 with tempfile.TemporaryDirectory(prefix='irfen_l8desc_') as raw:
  td=Path(raw)
  for x in items:
   amap={z['asset_key']:z for z in x['assets']}
   for key in ('qa_pixel','red','nir08','swir22'):
    z=amap.get(key)
    if z is None:raise SystemExit('FAIL_CLOSED_ASSET_'+key)
    p=td/f"{x['mirror_item_id']}_{key}.tif";dig,n=dl(sess,z['href'],p,co['transport']['unsigned_asset_host']);paths[(x['mirror_item_id'],key)]=p;prov[f"{x['mirror_item_id']}::{key}"]={'sha512':dig,'bytes':n,'full_file_hash_completed_before_raster_read':True,'signed_url_persisted':False,'signed_url_logged':False}
  refid=pre[0]['mirror_item_id']
  with rasterio.open(paths[(refid,'qa_pixel')]) as ref:
   ref_crs=ref.crs;ref_transform=ref.transform;ref_width=ref.width;ref_height=ref.height
  rows=[];invalid=sum(1<<int(b) for b in co['qa_pixel']['invalid_bits']);scale=float(co['reflectance']['landsat_collection2_level2_scale']);offset=float(co['reflectance']['landsat_collection2_level2_offset']);eps=float(co['indices']['denominator_absolute_minimum'])
  for f in sorted(gj['features'],key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
   code=(f.get('properties') or {}).get('candidate_code');geom=transform_geom('EPSG:4326',ref_crs,f['geometry'],precision=3);coords=geom['coordinates'];
   def flat(c):
    if isinstance(c,(list,tuple)) and len(c)>=2 and isinstance(c[0],(int,float)):return [c]
    out=[]
    for z in c:out.extend(flat(z))
    return out
   pts=flat(coords);xs=[p[0] for p in pts];ys=[p[1] for p in pts];w=from_bounds(min(xs),min(ys),max(xs),max(ys),ref_transform).round_offsets().round_lengths();w=w.intersection(rasterio.windows.Window(0,0,ref_width,ref_height));h=int(w.height);ww=int(w.width)
   if h<=0 or ww<=0:raise SystemExit('FAIL_CLOSED_EMPTY_WINDOW_'+code)
   wt=rasterio.windows.transform(w,ref_transform);cm=geometry_mask([geom],out_shape=(h,ww),transform=wt,all_touched=False,invert=True);cand_n=int(cm.sum())
   period={}
   for wn,scene_list in [('pre',pre),('post',post)]:
    bands={k:[] for k in ('red','nir08','swir22')};obs=[]
    for sc in scene_list:
     iid=sc['mirror_item_id']
     with rasterio.open(paths[(iid,'qa_pixel')]) as ds, WarpedVRT(ds,crs=ref_crs,transform=ref_transform,width=ref_width,height=ref_height,resampling=Resampling.nearest) as vrt:qa=vrt.read(1,window=w)
     valid=(np.bitwise_and(qa.astype('uint32'),invalid)==0)&cm
     rawbands={}
     for key in ('red','nir08','swir22'):
      with rasterio.open(paths[(iid,key)]) as ds, WarpedVRT(ds,crs=ref_crs,transform=ref_transform,width=ref_width,height=ref_height,resampling=Resampling.bilinear) as vrt:arr=vrt.read(1,window=w).astype('float32')
      valid &= np.isfinite(arr)&(arr!=0);rawbands[key]=arr
     obs.append(valid.astype('uint8'))
     for key,arr in rawbands.items():bands[key].append(np.where(valid,arr*scale+offset,np.nan))
    count=np.sum(np.stack(obs),axis=0,dtype='uint8');comp={}
    with warnings.catch_warnings():
     warnings.simplefilter('ignore',category=RuntimeWarning)
     for key in bands:comp[key]=np.nanmedian(np.stack(bands[key]),axis=0)
    period[wn]={'count':count,'bands':comp}
   common=(period['pre']['count']>=1)&(period['post']['count']>=1)&cm
   for key in ('red','nir08','swir22'):common &= np.isfinite(period['pre']['bands'][key])&np.isfinite(period['post']['bands'][key])
   idx=np.flatnonzero(common);common_n=int(idx.size);frac=float(common_n/cand_n) if cand_n else 0.
   entry={'candidate_code':code,'candidate_pixel_count':cand_n,'pre_composite_pixel_count':int(((period['pre']['count']>=1)&cm).sum()),'post_composite_pixel_count':int(((period['post']['count']>=1)&cm).sum()),'common_composite_pixel_count':common_n,'common_composite_fraction':round(frac,6),'status':'DESCRIPTIVE_COMPOSITE_AVAILABLE' if common_n else 'NO_COMMON_VALID_COMPOSITE_PIXELS_OUTCOME_UNKNOWN'}
   if common_n:
    entry['median_valid_observation_count_pre_on_common_pixels']=round(float(np.median(period['pre']['count'].ravel()[idx])),3);entry['median_valid_observation_count_post_on_common_pixels']=round(float(np.median(period['post']['count'].ravel()[idx])),3);metrics={'bands':{},'indices':{}}
    for key in ('red','nir08','swir22'):
     metrics['bands'][key]=stats(period['pre']['bands'][key].ravel()[idx],period['post']['bands'][key].ravel()[idx])
    rp=period['pre']['bands']['red'].ravel()[idx];rq=period['post']['bands']['red'].ravel()[idx];np_=period['pre']['bands']['nir08'].ravel()[idx];nq=period['post']['bands']['nir08'].ravel()[idx];sp=period['pre']['bands']['swir22'].ravel()[idx];sq=period['post']['bands']['swir22'].ravel()[idx]
    def ndi(a,b):
     den=a+b;out=np.full(a.shape,np.nan);m=np.abs(den)>=eps;out[m]=(a[m]-b[m])/den[m];return out
    for name,pv,qv in [('NDVI',ndi(np_,rp),ndi(nq,rq)),('NBR',ndi(np_,sp),ndi(nq,sq))]:
     m=np.isfinite(pv)&np.isfinite(qv);metrics['indices'][name]=dict(stats(pv[m],qv[m]),pixel_count=int(m.sum())) if m.any() else {'pixel_count':0}
    entry['metrics']=metrics
   rows.append(entry)
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_LANDSAT8_ALL_SCENE_THRESHOLD_FREE_DESCRIPTIVE_COMPOSITE','guards':co['guards'],'contract_sha256':sha256(a.contract),'inventory_sha256':sha256(a.inventory),'candidate_geometry_sha256':sha256(a.geometry),'asset_provenance':prov,'candidate_count':len(rows),'candidates':rows,'all_frozen_scenes_used':True,'candidate_level_coverage_threshold_used':False,'classification_thresholds_used':False,'outcome_labels_assigned':False,'no_change_interpreted_as_control':False,'large_change_interpreted_as_activation':False,'mirror_bytes_independently_matched_to_usgs_origin_for_all_items':False,'target_names_or_ids_read':False,'target_outcomes_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'feedback_to_matching_performed':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'candidate_count':len(rows),'with_common_pixels':sum(x['common_composite_pixel_count']>0 for x in rows),'outcome_labels_assigned':False},sort_keys=True))
if __name__=='__main__':main()
