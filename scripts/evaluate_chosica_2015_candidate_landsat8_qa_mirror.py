#!/usr/bin/env python3
"""Run the frozen Landsat QA science through a checksum-locked transport mirror.
The mirror is transport only. Every full QA_PIXEL file must match the canonical
USGS STAC SHA-512 before rasterio is allowed to open it.
"""
from __future__ import annotations
import argparse, hashlib, json, tempfile, urllib.parse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import reproject, Resampling, transform_geom
import requests

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

def git_blob_sha(p: Path) -> str:
    b=p.read_bytes(); return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def expected_sha512(multihash: str) -> str:
    if not isinstance(multihash,str) or len(multihash)!=132 or not multihash.lower().startswith('1340'):
        raise RuntimeError('FAIL_CLOSED_UNSUPPORTED_CHECKSUM_FORMAT')
    return multihash[4:].lower()

def download_exact_mirror(session,url,checksum,path,allowed_host):
    u=urllib.parse.urlparse(url)
    if u.scheme!='https' or u.hostname!=allowed_host: raise RuntimeError('FAIL_CLOSED_MIRROR_ASSET_HOST')
    h=hashlib.sha512(); n=0
    with session.get(url,stream=True,timeout=(20,300),allow_redirects=False) as r:
        if r.is_redirect or r.is_permanent_redirect: raise RuntimeError('FAIL_CLOSED_MIRROR_ASSET_REDIRECT')
        if r.status_code!=200: raise RuntimeError(f'FAIL_CLOSED_MIRROR_ASSET_HTTP_{r.status_code}')
        with path.open('wb') as f:
            for c in r.iter_content(1<<20):
                if c: f.write(c); h.update(c); n+=len(c)
    got=h.hexdigest(); expected=expected_sha512(checksum)
    if got!=expected: raise RuntimeError(f'FAIL_CLOSED_MIRROR_ASSET_SHA512_MISMATCH expected={expected} got={got}')
    return got,n

def fail_report(base, output: Path, error: Exception, transfer_started: bool):
    d=dict(base); d.update({'status':'FAIL_CLOSED_LANDSAT8_QA_MIRROR_TRANSPORT','error':str(error),'qa_pixel_asset_transfer_started':bool(transfer_started),'qa_pixel_asset_checksum_verified_all':False,'qa_pixel_raster_read':False,'reflectance_asset_bytes_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False})
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(d,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();
    ap.add_argument('--overlay',type=Path,required=True);ap.add_argument('--scientific-contract',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--mirror',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();ov=json.loads(a.overlay.read_text());co=json.loads(a.scientific_contract.read_text());inv=json.loads(a.inventory.read_text());mir=json.loads(a.mirror.read_text());gj=json.loads(a.geometry.read_text())
    base={'schema_version':'0.2','batch_id':co['batch_id'],'guards':co['guards'],'transport_overlay_sha256':sha256(a.overlay),'scientific_contract_git_blob_sha':git_blob_sha(a.scientific_contract),'asset_inventory_sha256':sha256(a.inventory),'transport_mirror_sha256':sha256(a.mirror),'candidate_geometry_sha256':sha256(a.geometry),'transport_mirror_role':'TRANSPORT_ONLY_NOT_SCIENTIFIC_SOURCE'}
    try:
        if ov['guards']!=co['guards']: raise RuntimeError('FAIL_CLOSED_GUARD_MISMATCH')
        if git_blob_sha(a.scientific_contract)!=ov['scientific_contract']['git_blob_sha']: raise RuntimeError('FAIL_CLOSED_SCIENTIFIC_CONTRACT_BLOB')
        if sha256(a.inventory)!=ov['canonical_integrity_source']['sha256']: raise RuntimeError('FAIL_CLOSED_INVENTORY_HASH')
        if sha256(a.mirror)!=ov['transport_mirror']['artifact_file_sha256']: raise RuntimeError('FAIL_CLOSED_MIRROR_HASH')
        if sha256(a.geometry)!=co['inputs']['candidate_geometry']['sha256']: raise RuntimeError('FAIL_CLOSED_GEOMETRY_HASH')
        if inv.get('status')!='FROZEN_LANDSAT8_FROZEN_ITEM_ASSET_METADATA_INVENTORY': raise RuntimeError('FAIL_CLOSED_INVENTORY_STATUS')
        if mir.get('status')!='PASS_LANDSAT8_TRANSPORT_MIRROR_EXACT_ITEM_IMMUTABLE_METADATA_ONLY': raise RuntimeError('FAIL_CLOSED_MIRROR_STATUS')
        if mir.get('mirror_role')!='TRANSPORT_ONLY_NOT_SCIENTIFIC_SOURCE': raise RuntimeError('FAIL_CLOSED_MIRROR_ROLE')
        for k in ('outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','candidate_selection_modified','candidate_ranking_modified','free_web_search_used','control_labels_assigned','sealed_target_unblind_allowed','asset_acceptance_authorized'):
            if mir.get(k) is not False: raise RuntimeError('FAIL_CLOSED_MIRROR_GUARD_'+k)
        for k in ('asset_href_requested','pixel_bytes_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','free_web_search_used','sealed_target_unblind_allowed'):
            if inv.get(k) is not False: raise RuntimeError('FAIL_CLOSED_INVENTORY_GUARD_'+k)
    except Exception as e:
        fail_report(base,a.output,e,False); raise SystemExit(2)
    imap={x['id']:x for x in inv['items']}; mmap={x['usgs_item_id']:x for x in mir['items']}; roles=('reference','pre','post');items=co['inputs']['frozen_items']
    session=requests.Session();session.headers.update({'User-Agent':'IRFEN-research-cleanroom/qa-mirror-0.1'})
    invalid_bits=[int(x) for x in co['qa_pixel']['invalid_bits'].keys()];invalid_mask=sum(1<<b for b in invalid_bits)
    provenance={};arrays={};transfer_started=False
    with tempfile.TemporaryDirectory(prefix='irfen_l8qa_mirror_') as raw:
        td=Path(raw);verified=set()
        try:
            for role in roles:
                iid=items[role];item=imap.get(iid);mi=mmap.get(iid)
                if item is None or mi is None: raise RuntimeError('FAIL_CLOSED_ITEM_IDENTITY_'+role)
                ca=[x for x in item['assets'] if x['asset_key']==co['asset_policy']['allowed_asset_key']]
                ma=[x for x in mi['assets'] if x['asset_key']==co['asset_policy']['allowed_asset_key']]
                if len(ca)!=1 or len(ma)!=1: raise RuntimeError('FAIL_CLOSED_QA_ASSET_CARDINALITY_'+role)
                canonical=ca[0];mirror=ma[0]
                if Path(urllib.parse.urlparse(canonical['href']).path).name != Path(urllib.parse.urlparse(mirror['href']).path).name: raise RuntimeError('FAIL_CLOSED_ASSET_BASENAME_'+role)
                p=td/f'{role}_qa.tif';transfer_started=True
                digest,n=download_exact_mirror(session,mirror['href'],canonical.get('file:checksum'),p,ov['transport_mirror']['allowed_host']);verified.add(str(p))
                provenance[role]={'item_id':iid,'mirror_item_id':mi['mirror_item_id'],'asset_key':'qa_pixel','sha512':digest,'bytes':n,'canonical_usgs_multihash':canonical.get('file:checksum'),'transport_host':urllib.parse.urlparse(mirror['href']).hostname,'checksum_verified_before_raster_read':True}
            for role in roles:
                p=td/f'{role}_qa.tif'
                if str(p) not in verified: raise RuntimeError('FAIL_CLOSED_RASTER_BEFORE_CHECKSUM_'+role)
                with rasterio.open(p) as ds:
                    arr=ds.read(1);meta={'crs':ds.crs,'transform':ds.transform,'width':ds.width,'height':ds.height,'dtype':str(arr.dtype)}
                arrays[role]=(arr,meta)
        except Exception as e:
            fail_report(base,a.output,e,transfer_started); raise SystemExit(2)
        pre,pm=arrays['pre'];target_shape=(pm['height'],pm['width']);aligned={'pre':pre}
        for role in ('reference','post'):
            src,sm=arrays[role];dst=np.full(target_shape,1,dtype=src.dtype)
            reproject(source=src,destination=dst,src_transform=sm['transform'],src_crs=sm['crs'],src_nodata=None,dst_transform=pm['transform'],dst_crs=pm['crs'],dst_nodata=1,resampling=Resampling.nearest)
            aligned[role]=dst
        valid={r:(np.bitwise_and(aligned[r].astype('uint32'),invalid_mask)==0) for r in roles}
        feats=gj.get('features',[]);outrows=[];gate=co['quality_gate']
        for f in sorted(feats,key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
            code=(f.get('properties') or {}).get('candidate_code');geom=transform_geom('EPSG:4326',pm['crs'],f['geometry'],precision=3)
            cm=geometry_mask([geom],out_shape=target_shape,transform=pm['transform'],all_touched=False,invert=True);total=int(cm.sum())
            fracs={r:(float((valid[r]&cm).sum())/total if total else 0.0) for r in roles};common=valid['reference']&valid['pre']&valid['post']&cm;common_n=int(common.sum());common_frac=float(common_n/total) if total else 0.0
            passed=(total>=int(gate['minimum_candidate_pixels']) and all(fracs[r]>=float(gate['minimum_clear_land_fraction_each_scene']) for r in roles) and common_frac>=float(gate['minimum_three_scene_common_clear_land_fraction']))
            outrows.append({'candidate_code':code,'candidate_pixel_count':total,'clear_land_fraction':{k:round(v,6) for k,v in fracs.items()},'three_scene_common_clear_land_pixels':common_n,'three_scene_common_clear_land_fraction':round(common_frac,6),'qa_status':gate['candidate_status_if_pass'] if passed else gate['candidate_status_if_fail']})
    usable=sum(x['qa_status']==co['quality_gate']['candidate_status_if_pass'] for x in outrows)
    out=dict(base);out.update({'status':'PASS_LANDSAT8_CANDIDATE_QA_GATE' if usable>=int(co['quality_gate']['minimum_usable_candidates_to_continue']) else 'FAIL_CLOSED_LANDSAT8_QA_NO_USABLE_CANDIDATES','invalid_qa_bits':invalid_bits,'alignment':co['alignment'],'asset_provenance':provenance,'candidate_count':len(outrows),'usable_candidate_count':usable,'candidates':outrows,'qa_pixel_asset_transfer_started':True,'qa_pixel_asset_checksum_verified_all':True,'qa_pixel_raster_read':True,'reflectance_asset_bytes_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False})
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'candidate_count':len(outrows),'usable_candidate_count':usable,'all_qa_sha512_exact':True},sort_keys=True))
    if usable<int(co['quality_gate']['minimum_usable_candidates_to_continue']): raise SystemExit(3)
if __name__=='__main__': main()
