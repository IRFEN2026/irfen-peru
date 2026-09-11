#!/usr/bin/env python3
"""Compute frozen descriptive Landsat 7 surface-reflectance changes for QA-usable blinded candidates only."""
from __future__ import annotations
import argparse, hashlib, json, tempfile, urllib.parse
from pathlib import Path
import numpy as np
import planetary_computer
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import reproject, Resampling, transform_geom
import requests

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()
def signed_url(unsigned,host):
    u=urllib.parse.urlparse(unsigned)
    if u.scheme!='https' or u.hostname!=host or u.query: raise RuntimeError('FAIL_CLOSED_UNSIGNED_ASSET_SCOPE')
    s=planetary_computer.sign_url(unsigned);q=urllib.parse.urlparse(s)
    if q.scheme!='https' or q.hostname!=u.hostname or q.path!=u.path or not q.query: raise RuntimeError('FAIL_CLOSED_SIGNED_URL_INVARIANTS')
    return s
def download_hash(session,unsigned,path,host):
    h=hashlib.sha512();n=0;s=signed_url(unsigned,host)
    with session.get(s,stream=True,timeout=(20,300),allow_redirects=False) as r:
        if r.is_redirect or r.is_permanent_redirect: raise RuntimeError('FAIL_CLOSED_ASSET_REDIRECT')
        if r.status_code!=200: raise RuntimeError(f'FAIL_CLOSED_ASSET_HTTP_{r.status_code}')
        with path.open('wb') as f:
            for c in r.iter_content(1<<20):
                if c: f.write(c);h.update(c);n+=len(c)
    if n<=0: raise RuntimeError('FAIL_CLOSED_EMPTY_ASSET')
    return h.hexdigest(),n
def qstats(pre,post):
    d=post-pre
    return {'pre_median':float(np.median(pre)),'post_median':float(np.median(post)),'delta_median':float(np.median(d)),'delta_p10':float(np.quantile(d,.10)),'delta_p25':float(np.quantile(d,.25)),'delta_p75':float(np.quantile(d,.75)),'delta_p90':float(np.quantile(d,.90))}
def clean_stats(x):
    return {k:round(v,8) for k,v in x.items()}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--qa',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=json.loads(a.contract.read_text());qa=json.loads(a.qa.read_text());inv=json.loads(a.inventory.read_text());gj=json.loads(a.geometry.read_text())
    if sha256(a.qa)!=co['inputs']['qa']['sha256'] or qa.get('status')!=co['inputs']['qa']['required_status']: raise SystemExit('FAIL_CLOSED_QA_INPUT')
    if sha256(a.inventory)!=co['inputs']['asset_inventory']['sha256'] or inv.get('status')!='FROZEN_LANDSAT7_FROZEN_PAIR_ASSET_METADATA_INVENTORY': raise SystemExit('FAIL_CLOSED_INVENTORY_INPUT')
    if sha256(a.geometry)!=co['inputs']['candidate_geometry']['sha256']: raise SystemExit('FAIL_CLOSED_GEOMETRY_INPUT')
    usable=sorted(co['inputs']['qa']['usable_candidate_codes'])
    if sorted(x['candidate_code'] for x in qa['candidates'] if x['qa_status']=='QA_USABLE_FOR_LANDSAT7_EVENT_CHANGE')!=usable: raise SystemExit('FAIL_CLOSED_QA_USABLE_SET')
    if any(x['candidate_code'] in usable and x['qa_status']!='QA_USABLE_FOR_LANDSAT7_EVENT_CHANGE' for x in qa['candidates']): raise SystemExit('FAIL_CLOSED_QA_STATUS')
    for k in ('surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
        if qa.get(k) is not False: raise SystemExit('FAIL_CLOSED_QA_GUARD_'+k)
    imap={x['item_id']:x for x in inv['items']};featmap={(f.get('properties') or {}).get('candidate_code'):f for f in gj['features']};session=requests.Session();session.headers.update({'User-Agent':'IRFEN-research-cleanroom/l7-change-0.1'});paths={};prov={}
    qa_expected={k:v['sha512'] for k,v in qa['asset_provenance'].items()}
    with tempfile.TemporaryDirectory(prefix='irfen_l7change_') as raw:
        td=Path(raw)
        for role in ('pre','post'):
            iid=co['inputs']['frozen_items'][role];item=imap.get(iid)
            if item is None: raise SystemExit('FAIL_CLOSED_ITEM_'+role)
            amap={x['asset_key']:x for x in item['assets']}
            for key in ('qa_pixel','qa_radsat')+tuple(co['reflectance']['asset_keys']):
                if key not in amap: raise SystemExit('FAIL_CLOSED_ASSET_'+key)
                p=td/f'{role}_{key}.tif';digest,n=download_hash(session,amap[key]['href'],p,co['transport']['unsigned_asset_host'])
                if key in ('qa_pixel','qa_radsat') and digest!=qa_expected[f'{role}_{key}']: raise SystemExit('FAIL_CLOSED_QA_ASSET_SHA512_REPLAY')
                paths[(role,key)]=p;prov[f'{role}_{key}']={'item_id':iid,'asset_key':key,'sha512':digest,'bytes':n,'full_file_hash_completed_before_raster_read':True,'signed_url_persisted':False,'signed_url_logged':False}
        with rasterio.open(paths[('pre','qa_pixel')]) as ds:
            ref={'crs':ds.crs,'transform':ds.transform,'width':ds.width,'height':ds.height};pre_qp=ds.read(1)
        shape=(ref['height'],ref['width'])
        def aligned(path,resampling,dtype=None,fill=0):
            with rasterio.open(path) as ds:
                if ds.crs==ref['crs'] and ds.transform==ref['transform'] and ds.width==ref['width'] and ds.height==ref['height']:
                    return ds.read(1)
                src=ds.read(1);out=np.full(shape,fill,dtype=dtype or src.dtype);reproject(source=src,destination=out,src_transform=ds.transform,src_crs=ds.crs,src_nodata=ds.nodata,dst_transform=ref['transform'],dst_crs=ref['crs'],dst_nodata=fill,resampling=resampling);return out
        pre_qr=aligned(paths[('pre','qa_radsat')],Resampling.nearest,fill=1);post_qp=aligned(paths[('post','qa_pixel')],Resampling.nearest,fill=1);post_qr=aligned(paths[('post','qa_radsat')],Resampling.nearest,fill=1)
        invalid_mask=sum(1<<int(b) for b in qa['invalid_qa_pixel_bits']);common=((np.bitwise_and(pre_qp.astype('uint32'),invalid_mask)==0)&(pre_qr.astype('uint32')==0)&(np.bitwise_and(post_qp.astype('uint32'),invalid_mask)==0)&(post_qr.astype('uint32')==0))
        indices={};spectral={c:{} for c in usable};scale=float(co['reflectance']['landsat_collection2_level2_scale']);offset=float(co['reflectance']['landsat_collection2_level2_offset'])
        for code in usable:
            f=featmap.get(code)
            if f is None: raise SystemExit('FAIL_CLOSED_MISSING_GEOMETRY_'+code)
            geom=transform_geom('EPSG:4326',ref['crs'],f['geometry'],precision=3);cm=geometry_mask([geom],out_shape=shape,transform=ref['transform'],all_touched=False,invert=True);idx=np.flatnonzero(common&cm)
            if idx.size<1: raise SystemExit('FAIL_CLOSED_NO_COMMON_QA_PIXELS_'+code)
            indices[code]=idx
        for key in co['reflectance']['asset_keys']:
            pre=aligned(paths[('pre',key)],Resampling.bilinear,dtype='float32',fill=0).astype('float32');post=aligned(paths[('post',key)],Resampling.bilinear,dtype='float32',fill=0).astype('float32')
            for code,idx in indices.items():
                pr=pre.ravel()[idx];po=post.ravel()[idx];spectral[code][key]=(pr,po)
            del pre,post
        rows=[];eps=float(co['indices']['denominator_absolute_minimum'])
        for code in usable:
            valid=np.ones(indices[code].size,dtype=bool)
            scaled={}
            for key,(pr,po) in spectral[code].items():
                valid &= (pr!=0)&(po!=0)&np.isfinite(pr)&np.isfinite(po);scaled[key]=(pr*scale+offset,po*scale+offset)
            if not valid.any(): raise SystemExit('FAIL_CLOSED_NO_SPECTRAL_PIXELS_'+code)
            for key in scaled: scaled[key]=(scaled[key][0][valid],scaled[key][1][valid])
            redp,redq=scaled['red'];nirp,nirq=scaled['nir08'];s2p,s2q=scaled['swir22']
            def nd(a,b):
                den=a+b;out=np.full(a.shape,np.nan,dtype='float64');m=np.abs(den)>=eps;out[m]=(a[m]-b[m])/den[m];return out
            ndvi_p,ndvi_q=nd(nirp,redp),nd(nirq,redq);nbr_p,nbr_q=nd(nirp,s2p),nd(nirq,s2q)
            metrics={'bands':{k:clean_stats(qstats(v[0],v[1])) for k,v in scaled.items()},'indices':{}}
            for name,pv,qv in [('NDVI',ndvi_p,ndvi_q),('NBR',nbr_p,nbr_q)]:
                m=np.isfinite(pv)&np.isfinite(qv)
                if not m.any(): raise SystemExit('FAIL_CLOSED_NO_INDEX_PIXELS_'+code+'_'+name)
                metrics['indices'][name]=clean_stats(qstats(pv[m],qv[m]));metrics['indices'][name]['pixel_count']=int(m.sum())
            rows.append({'candidate_code':code,'status':'DESCRIPTIVE_METRICS_COMPUTED_NOT_OUTCOME_LABEL','qa_common_pixel_count':int(indices[code].size),'spectral_common_pixel_count':int(valid.sum()),'metrics':metrics})
        excluded=[x['candidate_code'] for x in qa['candidates'] if x['qa_status']!='QA_USABLE_FOR_LANDSAT7_EVENT_CHANGE']
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_LANDSAT7_DESCRIPTIVE_CHANGE_METRICS','guards':co['guards'],'contract_sha256':sha256(a.contract),'qa_sha256':sha256(a.qa),'asset_inventory_sha256':sha256(a.inventory),'candidate_geometry_sha256':sha256(a.geometry),'reflectance_asset_provenance':{k:v for k,v in prov.items() if not k.endswith('qa_pixel') and not k.endswith('qa_radsat')},'qa_asset_replay_provenance':{k:v for k,v in prov.items() if k.endswith('qa_pixel') or k.endswith('qa_radsat')},'qa_usable_candidate_count':len(usable),'computed_candidates':rows,'qa_insufficient_candidates':[{'candidate_code':x,'status':'NOT_COMPUTED_QA_INSUFFICIENT_OUTCOME_UNKNOWN'} for x in sorted(excluded)],'surface_signal_observed':True,'descriptive_metrics_only':True,'classification_thresholds_used':False,'outcome_labels_assigned':False,'no_change_interpreted_as_control':False,'large_change_interpreted_as_activation':False,'mirror_bytes_independently_matched_to_usgs_origin':False,'target_names_or_ids_read':False,'target_outcome_evidence_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'feedback_to_matching_performed':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8');print(json.dumps({'status':out['status'],'computed_candidate_count':len(rows),'qa_insufficient_count':len(excluded),'outcome_labels_assigned':False},sort_keys=True))
if __name__=='__main__': main()
