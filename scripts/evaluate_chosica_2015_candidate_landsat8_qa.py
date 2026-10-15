#!/usr/bin/env python3
"""Evaluate candidate-local clear-land coverage for three frozen Landsat acquisitions.
Reads only QA_PIXEL assets after exact full-file checksum verification.
"""
from __future__ import annotations
import argparse, hashlib, json, tempfile, urllib.parse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import reproject, Resampling, transform_geom
import requests

def sha256(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def expected_sha512(multihash: str) -> str:
    if not isinstance(multihash,str) or len(multihash)!=132 or not multihash.lower().startswith('1340'):
        raise RuntimeError('FAIL_CLOSED_UNSUPPORTED_CHECKSUM_FORMAT')
    return multihash[4:].lower()
def download_exact(session,url,checksum,path):
    u=urllib.parse.urlparse(url)
    if u.scheme!='https' or u.hostname!='landsatlook.usgs.gov': raise RuntimeError('FAIL_CLOSED_ASSET_HOST')
    h=hashlib.sha512(); n=0
    with session.get(url,stream=True,timeout=(20,300),allow_redirects=False) as r:
        if r.is_redirect or r.is_permanent_redirect: raise RuntimeError('FAIL_CLOSED_ASSET_REDIRECT')
        if r.status_code!=200: raise RuntimeError(f'FAIL_CLOSED_ASSET_HTTP_{r.status_code}')
        with path.open('wb') as f:
            for c in r.iter_content(1<<20):
                if c: f.write(c); h.update(c); n+=len(c)
    got=h.hexdigest()
    if got!=expected_sha512(checksum): raise RuntimeError('FAIL_CLOSED_ASSET_SHA512_MISMATCH')
    return got,n

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--inventory',type=Path,required=True); ap.add_argument('--geometry',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text()); inv=json.loads(a.inventory.read_text()); gj=json.loads(a.geometry.read_text())
    if sha256(a.inventory)!=co['inputs']['asset_inventory']['sha256']: raise SystemExit('FAIL_CLOSED_INVENTORY_HASH')
    if sha256(a.geometry)!=co['inputs']['candidate_geometry']['sha256']: raise SystemExit('FAIL_CLOSED_GEOMETRY_HASH')
    if inv.get('status')!='FROZEN_LANDSAT8_FROZEN_ITEM_ASSET_METADATA_INVENTORY': raise SystemExit('FAIL_CLOSED_INVENTORY_STATUS')
    for k in ('asset_href_requested','pixel_bytes_read','outcome_evidence_read','target_names_or_ids_read','a6680_read','contaminated_adjudication_used','scene_selection_modified','free_web_search_used','sealed_target_unblind_allowed'):
        if inv.get(k) is not False: raise SystemExit('FAIL_CLOSED_INVENTORY_GUARD_'+k)
    imap={x['id']:x for x in inv['items']}; roles=('reference','pre','post'); items=co['inputs']['frozen_items']; session=requests.Session(); session.headers.update({'User-Agent':'IRFEN-research-cleanroom/0.1'})
    invalid_bits=[int(x) for x in co['qa_pixel']['invalid_bits'].keys()]; invalid_mask=sum(1<<b for b in invalid_bits)
    provenance={}; arrays={}
    with tempfile.TemporaryDirectory(prefix='irfen_l8qa_') as raw:
        td=Path(raw)
        for role in roles:
            iid=items[role]; item=imap.get(iid)
            if item is None: raise SystemExit('FAIL_CLOSED_ITEM_NOT_IN_INVENTORY_'+role)
            matches=[x for x in item['assets'] if x['asset_key']==co['asset_policy']['allowed_asset_key']]
            if len(matches)!=1: raise SystemExit('FAIL_CLOSED_QA_ASSET_CARDINALITY_'+role)
            asset=matches[0]; p=td/f'{role}_qa.tif'; digest,n=download_exact(session,asset['href'],asset.get('file:checksum'),p)
            provenance[role]={'item_id':iid,'asset_key':'qa_pixel','sha512':digest,'bytes':n,'source_multihash':asset.get('file:checksum')}
            with rasterio.open(p) as ds:
                arr=ds.read(1); meta={'crs':ds.crs,'transform':ds.transform,'width':ds.width,'height':ds.height,'dtype':str(arr.dtype)}
            arrays[role]=(arr,meta)
        pre,pm=arrays['pre']; target_shape=(pm['height'],pm['width']); aligned={'pre':pre}
        for role in ('reference','post'):
            src,sm=arrays[role]; dst=np.full(target_shape,1,dtype=src.dtype)
            reproject(source=src,destination=dst,src_transform=sm['transform'],src_crs=sm['crs'],src_nodata=None,dst_transform=pm['transform'],dst_crs=pm['crs'],dst_nodata=1,resampling=Resampling.nearest)
            aligned[role]=dst
        valid={r:(np.bitwise_and(aligned[r].astype('uint32'),invalid_mask)==0) for r in roles}
        feats=gj.get('features',[]); outrows=[]; gate=co['quality_gate']
        for f in sorted(feats,key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
            code=(f.get('properties') or {}).get('candidate_code'); geom=transform_geom('EPSG:4326',pm['crs'],f['geometry'],precision=3)
            cm=geometry_mask([geom],out_shape=target_shape,transform=pm['transform'],all_touched=False,invert=True)
            total=int(cm.sum())
            fracs={r:(float((valid[r]&cm).sum())/total if total else 0.0) for r in roles}
            common=valid['reference']&valid['pre']&valid['post']&cm; common_n=int(common.sum()); common_frac=float(common_n/total) if total else 0.0
            passed=(total>=int(gate['minimum_candidate_pixels']) and all(fracs[r]>=float(gate['minimum_clear_land_fraction_each_scene']) for r in roles) and common_frac>=float(gate['minimum_three_scene_common_clear_land_fraction']))
            outrows.append({'candidate_code':code,'candidate_pixel_count':total,'clear_land_fraction':{k:round(v,6) for k,v in fracs.items()},'three_scene_common_clear_land_pixels':common_n,'three_scene_common_clear_land_fraction':round(common_frac,6),'qa_status':gate['candidate_status_if_pass'] if passed else gate['candidate_status_if_fail']})
    usable=sum(x['qa_status']==gate['candidate_status_if_pass'] for x in outrows)
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_LANDSAT8_CANDIDATE_QA_GATE' if usable>=int(gate['minimum_usable_candidates_to_continue']) else 'FAIL_CLOSED_LANDSAT8_QA_NO_USABLE_CANDIDATES','guards':co['guards'],'contract_sha256':sha256(a.contract),'asset_inventory_sha256':sha256(a.inventory),'candidate_geometry_sha256':sha256(a.geometry),'invalid_qa_bits':invalid_bits,'alignment':co['alignment'],'asset_provenance':provenance,'candidate_count':len(outrows),'usable_candidate_count':usable,'candidates':outrows,'qa_pixel_asset_bytes_read':True,'reflectance_asset_bytes_read':False,'outcome_evidence_read':False,'target_names_or_ids_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'scene_selection_modified':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'free_web_search_used':False,'control_labels_assigned':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({'status':out['status'],'candidate_count':len(outrows),'usable_candidate_count':usable},sort_keys=True))
    if usable<int(gate['minimum_usable_candidates_to_continue']): raise SystemExit(3)
if __name__=='__main__': main()
