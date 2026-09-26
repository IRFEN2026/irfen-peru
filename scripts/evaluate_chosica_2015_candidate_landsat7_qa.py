#!/usr/bin/env python3
"""Evaluate preregistered Landsat 7 QA for blinded candidates.

Only QA_PIXEL and QA_RADSAT are transferred. Each file is fully downloaded and SHA-512
hashed before rasterio may open it. Signed URLs are ephemeral and never emitted.
"""
from __future__ import annotations
import argparse, hashlib, json, tempfile, urllib.parse
from importlib.metadata import version as pkg_version
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
def signed_url(unsigned: str, host: str) -> str:
    u=urllib.parse.urlparse(unsigned)
    if u.scheme!='https' or u.hostname!=host or u.query: raise RuntimeError('FAIL_CLOSED_UNSIGNED_ASSET_SCOPE')
    s=planetary_computer.sign_url(unsigned);q=urllib.parse.urlparse(s)
    if q.scheme!='https' or q.hostname!=u.hostname or q.path!=u.path or not q.query: raise RuntimeError('FAIL_CLOSED_SIGNED_URL_INVARIANTS')
    return s
def download_hash(session,unsigned,path,host):
    signed=signed_url(unsigned,host);h=hashlib.sha512();n=0
    with session.get(signed,stream=True,timeout=(20,300),allow_redirects=False) as r:
        if r.is_redirect or r.is_permanent_redirect: raise RuntimeError('FAIL_CLOSED_ASSET_REDIRECT')
        if r.status_code!=200: raise RuntimeError(f'FAIL_CLOSED_ASSET_HTTP_{r.status_code}')
        with path.open('wb') as f:
            for c in r.iter_content(1<<20):
                if c: f.write(c);h.update(c);n+=len(c)
    if n<=0: raise RuntimeError('FAIL_CLOSED_EMPTY_ASSET')
    return h.hexdigest(),n
def fail(base,out,error,transfer):
    d=dict(base);d.update({'status':'FAIL_CLOSED_LANDSAT7_QA','error':str(error),'asset_transfer_started':bool(transfer),'full_file_sha512_completed_before_any_raster_read':False,'qa_raster_read':False,'reflectance_asset_bytes_read':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False});out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(d,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'));inv=json.loads(a.inventory.read_text(encoding='utf-8'));gj=json.loads(a.geometry.read_text(encoding='utf-8'))
    base={'schema_version':'0.1','batch_id':co['batch_id'],'guards':co['guards'],'contract_sha256':sha256(a.contract),'asset_inventory_sha256':sha256(a.inventory),'candidate_geometry_sha256':sha256(a.geometry),'signing_library':'planetary-computer','signing_library_version':pkg_version('planetary-computer'),'transport_mirror_role':co['transport']['role'],'canonical_usgs_byte_checksum_available':False}
    try:
        if sha256(a.inventory)!=co['inputs']['asset_inventory']['sha256']: raise RuntimeError('FAIL_CLOSED_INVENTORY_HASH')
        if sha256(a.geometry)!=co['inputs']['candidate_geometry']['sha256']: raise RuntimeError('FAIL_CLOSED_GEOMETRY_HASH')
        if inv.get('status')!='FROZEN_LANDSAT7_FROZEN_PAIR_ASSET_METADATA_INVENTORY': raise RuntimeError('FAIL_CLOSED_INVENTORY_STATUS')
        for k in ('asset_href_requested','pixel_bytes_read','surface_signal_observed','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed'):
            if inv.get(k) is not False: raise RuntimeError('FAIL_CLOSED_INVENTORY_GUARD_'+k)
        if inv.get('asset_href_metadata_read') is not True: raise RuntimeError('FAIL_CLOSED_NO_FROZEN_ASSET_METADATA')
        if len(gj.get('features',[]))!=co['inputs']['candidate_geometry']['candidate_count']: raise RuntimeError('FAIL_CLOSED_GEOMETRY_COUNT')
    except Exception as e:
        fail(base,a.output,e,False);raise SystemExit(2)
    imap={x['item_id']:x for x in inv['items']};session=requests.Session();session.headers.update({'User-Agent':'IRFEN-research-cleanroom/l7-qa-0.1'});transfer=False
    arrays={};meta={};prov={};verified=set()
    with tempfile.TemporaryDirectory(prefix='irfen_l7qa_') as raw:
        td=Path(raw)
        try:
            for role in ('pre','post'):
                iid=co['inputs']['frozen_items'][role];item=imap.get(iid)
                if item is None: raise RuntimeError('FAIL_CLOSED_ITEM_'+role)
                for key in co['allowed_asset_keys']:
                    rows=[x for x in item['assets'] if x['asset_key']==key]
                    if len(rows)!=1: raise RuntimeError('FAIL_CLOSED_ASSET_CARDINALITY_'+role+'_'+key)
                    asset=rows[0];p=td/f'{role}_{key}.tif';transfer=True;digest,n=download_hash(session,asset['href'],p,co['transport']['unsigned_asset_host']);verified.add(str(p));prov[f'{role}_{key}']={'item_id':iid,'asset_key':key,'sha512':digest,'bytes':n,'transport_host':asset['href_host'],'full_file_hash_completed_before_raster_read':True,'signed_url_persisted':False,'signed_url_logged':False}
            for role in ('pre','post'):
                for key in co['allowed_asset_keys']:
                    p=td/f'{role}_{key}.tif'
                    if str(p) not in verified: raise RuntimeError('FAIL_CLOSED_RASTER_BEFORE_FULL_HASH')
                    with rasterio.open(p) as ds:
                        arr=ds.read(1);m={'crs':ds.crs,'transform':ds.transform,'width':ds.width,'height':ds.height,'dtype':str(arr.dtype)}
                    arrays[(role,key)]=arr;meta[(role,key)]=m
        except Exception as e:
            fail(base,a.output,e,transfer);raise SystemExit(2)
        pre_q=arrays[('pre','qa_pixel')];pm=meta[('pre','qa_pixel')];shape=(pm['height'],pm['width'])
        aligned={('pre','qa_pixel'):pre_q,('pre','qa_radsat'):arrays[('pre','qa_radsat')]}
        for key in ('qa_pixel','qa_radsat'):
            src=arrays[('post',key)];sm=meta[('post',key)];dst=np.full(shape,1,dtype=src.dtype)
            reproject(source=src,destination=dst,src_transform=sm['transform'],src_crs=sm['crs'],src_nodata=None,dst_transform=pm['transform'],dst_crs=pm['crs'],dst_nodata=1,resampling=Resampling.nearest);aligned[('post',key)]=dst
        invalid_mask=sum(1<<int(b) for b in co['qa_pixel']['invalid_bits'])
        valid={}
        for role in ('pre','post'):
            qp=aligned[(role,'qa_pixel')].astype('uint32');qr=aligned[(role,'qa_radsat')].astype('uint32');valid[role]=(np.bitwise_and(qp,invalid_mask)==0)&(qr==0)
        gate=co['quality_gate'];outrows=[]
        for f in sorted(gj['features'],key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
            code=(f.get('properties') or {}).get('candidate_code');geom=transform_geom('EPSG:4326',pm['crs'],f['geometry'],precision=3);cm=geometry_mask([geom],out_shape=shape,transform=pm['transform'],all_touched=False,invert=True);total=int(cm.sum());fracs={r:(float((valid[r]&cm).sum())/total if total else 0.0) for r in ('pre','post')};common=(valid['pre']&valid['post']&cm);common_n=int(common.sum());common_frac=float(common_n/total) if total else 0.0;passed=(total>=int(gate['minimum_candidate_pixels']) and all(fracs[r]>=float(gate['minimum_valid_land_fraction_each_scene']) for r in ('pre','post')) and common_frac>=float(gate['minimum_two_scene_common_valid_land_fraction']))
            outrows.append({'candidate_code':code,'candidate_pixel_count':total,'valid_land_fraction':{k:round(v,6) for k,v in fracs.items()},'two_scene_common_valid_land_pixels':common_n,'two_scene_common_valid_land_fraction':round(common_frac,6),'qa_status':gate['candidate_status_if_pass'] if passed else gate['candidate_status_if_fail']})
    usable=sum(x['qa_status']==gate['candidate_status_if_pass'] for x in outrows);out=dict(base);out.update({'status':'PASS_LANDSAT7_CANDIDATE_QA_GATE' if usable>=int(gate['minimum_usable_candidates_to_continue']) else 'FAIL_CLOSED_LANDSAT7_QA_NO_USABLE_CANDIDATES','asset_provenance':prov,'candidate_count':len(outrows),'usable_candidate_count':usable,'candidates':outrows,'invalid_qa_pixel_bits':[int(x) for x in co['qa_pixel']['invalid_bits']],'qa_radsat_valid_rule':'value_equals_zero','asset_transfer_started':True,'full_file_sha512_completed_before_any_raster_read':True,'qa_raster_read':True,'reflectance_asset_bytes_read':False,'surface_signal_observed':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False,'mirror_no_change_can_confirm_control':False})
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8');print(json.dumps({'status':out['status'],'candidate_count':len(outrows),'usable_candidate_count':usable,'full_file_sha512_before_raster':True},sort_keys=True));raise SystemExit(0 if usable>=int(gate['minimum_usable_candidates_to_continue']) else 3)
if __name__=='__main__': main()
