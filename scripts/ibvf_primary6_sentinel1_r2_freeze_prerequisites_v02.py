#!/usr/bin/env python3
"""Freeze PRIMARY6 R2 prerequisites using the frozen SNAP14-compatible POEORB selector v0.2.

RESEARCH_ONLY / TEST_ONLY. This supersedes v0.1 only for R2 orbit resource identity.
It does not read SAR response pixels, rainfall magnitudes, territorial outcomes,
known event dates, case/control roles, R3/R4 values, or model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from ibvf_primary6_sentinel1_r2_prerequisites import (
    archive_for,
    guards,
    load_exact_freeze,
    satellite_code,
)
from ibvf_sentinel1_r2_freeze_prerequisites import (
    HREF_RE,
    download,
    filename_interval,
    freeze_vertical,
    get,
    parse_utc,
    sha_file,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def month_triplet(t: datetime) -> list[tuple[int,int]]:
    idx=t.year*12+(t.month-1)
    out=[]
    for delta in (-1,0,1):
        k=idx+delta
        out.append((k//12,k%12+1))
    return out


def freeze_orbit_v02(root: str, acquisition: str, side: str, tmp: Path) -> dict[str,Any]:
    t=parse_utc(acquisition)
    inventories=[]
    candidates: dict[str,dict[str,Any]]={}
    for year,month in month_triplet(t):
        month_url=f"{root.rstrip('/')}/{year:04d}/{month:02d}/"
        try:
            html=get(month_url).text
        except Exception as exc:
            return {
                'side':side,'acquisition_utc':acquisition,'status':'TRANSPORT_BLOCKED',
                'scientific_data_status':'UNKNOWN_NOT_MISSING','failed_directory_url':month_url,
                'error':repr(exc),'selector_version':'SNAP14_POEORB_V02'
            }
        hrefs=sorted(set(HREF_RE.findall(html)))
        inventories.append({'directory_url':month_url,'aux_poeorb_zip_count':len(hrefs)})
        for href in hrefs:
            name=Path(href).name
            iv=filename_interval(name)
            if not iv or not (iv[0] <= t <= iv[1]):
                continue
            url=urljoin(month_url,href)
            # Deduplicate the same filename if exposed by more than one index page.
            prev=candidates.get(name)
            rec={'filename':name,'url':url,'validity_start':iv[0],'validity_stop':iv[1]}
            if prev is None or url < prev['url']:
                candidates[name]=rec
    covering=sorted(candidates.values(),key=lambda r:(r['validity_start'],r['filename'],r['url']))
    if not covering:
        return {
            'side':side,'acquisition_utc':acquisition,'status':'MISSING',
            'scientific_data_status':'UNKNOWN_NOT_MISSING','directory_inventories':inventories,
            'covering_count':0,'selector_version':'SNAP14_POEORB_V02'
        }
    chosen=covering[0]
    zpath=tmp/f"{side}.EOF.zip"
    dl=download(chosen['url'],zpath)
    if dl['status']!='SUCCESS':
        return {
            'side':side,'acquisition_utc':acquisition,'directory_inventories':inventories,
            'covering_count':len(covering),'covering_files':[r['filename'] for r in covering],
            'selection_rule':'EARLIEST_VALIDITY_START_AMONG_ALL_COVERING_AUX_POEORB_CANDIDATES_THEN_FILENAME_ASCENDING_TIEBREAK',
            'selector_version':'SNAP14_POEORB_V02',**dl
        }
    try:
        with zipfile.ZipFile(zpath) as zf:
            members=sorted(n for n in zf.namelist() if n.upper().endswith('.EOF'))
            if not members:
                raise ValueError('expected at least one EOF member')
            payloads=[(n,zf.read(n)) for n in members]
            payload_hashes={hashlib.sha256(b).hexdigest() for _,b in payloads}
            if len(payload_hashes)!=1:
                raise ValueError(f'multiple EOF members differ: {members}')
            root_members=[n for n,_ in payloads if '/' not in n]
            chosen_member=sorted(root_members or members)[0]
            payload=next(b for n,b in payloads if n==chosen_member)
            eof=tmp/f"{side}.EOF"; eof.write_bytes(payload)
        eof_sha,eof_bytes=sha_file(eof)
        text=eof.read_text(encoding='utf-8',errors='replace')
        product_ok='AUX_POEORB' in text or 'AUX_POEORB' in chosen['filename']
        validity_ok=chosen['validity_start'] <= t <= chosen['validity_stop']
        return {
            'side':side,'acquisition_utc':acquisition,'status':'PASS' if product_ok and validity_ok else 'INTEGRITY_BLOCK_R2',
            'selector_version':'SNAP14_POEORB_V02',
            'selection_rule':'EARLIEST_VALIDITY_START_AMONG_ALL_COVERING_AUX_POEORB_CANDIDATES_THEN_FILENAME_ASCENDING_TIEBREAK',
            'directory_inventories':inventories,'covering_count':len(covering),
            'covering_files':[r['filename'] for r in covering],
            'filename':chosen['filename'],'url':chosen['url'],
            'validity_start':chosen['validity_start'].isoformat(),'validity_stop':chosen['validity_stop'].isoformat(),
            'zip_sha256':dl['sha256'],'zip_bytes':dl['bytes'],
            'inner_eof_member':chosen_member,'inner_eof_member_count':len(members),
            'inner_eof_duplicate_payloads_identical':len(members)>1,
            'inner_eof_sha256':eof_sha,'inner_eof_bytes':eof_bytes,
            'product_class_aux_poeorb_confirmed':product_ok,'validity_covers_acquisition':validity_ok,
        }
    except Exception as exc:
        return {
            'side':side,'acquisition_utc':acquisition,'status':'INTEGRITY_BLOCK_R2',
            'selector_version':'SNAP14_POEORB_V02','directory_inventories':inventories,
            'covering_count':len(covering),'covering_files':[r['filename'] for r in covering],
            'url':chosen['url'],'zip_sha256':dl.get('sha256'),'error':repr(exc)
        }


def assert_amendment(a: dict[str,Any]) -> None:
    guards(a)
    assert a['scope']=='PRIMARY6_SENTINEL1_R2_POEORB_RESOURCE_SELECTION_AND_CONSUMPTION_VERIFICATION_ONLY'
    assert a['scientific_integrity']['amendment_based_on_signal_values'] is False
    assert a['scientific_integrity']['amendment_based_on_outcomes'] is False
    assert a['scientific_integrity']['amendment_changes_selected_windows'] is False
    assert a['scientific_integrity']['amendment_changes_sentinel1_pairs'] is False
    assert a['scientific_integrity']['amendment_changes_r2_graph_operators_or_numeric_parameters'] is False
    assert a['scientific_integrity']['amendment_changes_r3_threshold'] is False
    assert a['scientific_integrity']['amendment_changes_r4_features_or_thresholds'] is False
    assert a['v02_selector']['selection_rule']=='EARLIEST_VALIDITY_START_AMONG_ALL_COVERING_AUX_POEORB_CANDIDATES_THEN_FILENAME_ASCENDING_TIEBREAK'


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--r2-entry',type=Path,required=True)
    ap.add_argument('--base-prereq-contract',type=Path,required=True)
    ap.add_argument('--amendment',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()

    entry=json.loads(args.r2_entry.read_text(encoding='utf-8'))
    base=json.loads(args.base_prereq_contract.read_text(encoding='utf-8'))
    amendment=json.loads(args.amendment.read_text(encoding='utf-8'))
    guards(entry); guards(base); assert_amendment(amendment)
    assert entry['r2_execution_performed'] is False and entry['r2_science_pixels_read'] is False
    assert entry['territorial_outcomes_read'] is False and entry['known_event_dates_read'] is False
    assert entry['case_control_assignment_performed'] is False
    assert entry['activation_inference_allowed'] is False and entry['modeling_allowed'] is False
    assert base['pre_post_difference_allowed'] is False and base['activation_inference_allowed'] is False
    assert base['precise_orbits']['product_class']=='AUX_POEORB'
    assert base['precise_orbits']['same_orbit_quality_class_required'] is True
    assert base['precise_orbits']['automatic_unhashed_orbit_download_allowed'] is False

    rows=[]; missing=[]
    with tempfile.TemporaryDirectory(prefix='ibvf-primary6-r2-prereq-v02-') as td:
        tmp=Path(td)
        vertical=freeze_vertical(base,tmp)
        cache: dict[tuple[str,str],dict[str,Any]]={}
        orbit_counter=0
        for e in entry['entries']:
            if e['r2_entry_status']=='MISSING_COMPATIBLE_PAIR_RETAINED_NO_R2_EXECUTION':
                assert e['pre_item_id'] is None and e['post_item_id'] is None
                missing.append({
                    'case_id':e['case_id'],'unit_id':e['unit_id'],'season_id':e['season_id'],
                    'date_local':e['date_local'],'status':'MISSING_COMPATIBLE_PAIR_RETAINED_NO_R2_EXECUTION',
                    'replacement_allowed':False,'imputation_allowed':False,
                })
                continue
            assert e['r2_entry_status']=='PASS_R2_ENTRY_IDENTITY_FROZEN_EXECUTION_NOT_RUN'
            fp=Path(e['r1_freeze_path'])
            assert fp.exists() and sha256_file(fp)==e['r1_freeze_sha256']
            f=load_exact_freeze(fp,e)
            rec={
                'case_id':e['case_id'],'unit_id':e['unit_id'],'season_id':e['season_id'],
                'date_local':e['date_local'],'source_window_execution_identity_sha256':e['source_window_execution_identity_sha256'],
                'projection':e['projection'],'r1_freeze_path':str(fp),'r1_freeze_sha256':e['r1_freeze_sha256'],
                'r1_partition_binding_mode':e.get('r1_partition_binding_mode'),
                'legacy_pilot_r1_predates_execution_partition':bool(e.get('legacy_pilot_r1_predates_execution_partition')),
                'pre_item_id':e['pre_item_id'],'post_item_id':e['post_item_id'],
                'replacement_allowed':False,'reselection_allowed':False,'imputation_allowed':False,
                'precise_orbits':{},
            }
            for side in ('pre','post'):
                item=f[side]['item_id']; acquisition=f[side]['datetime']; code=satellite_code(item)
                key=(code,acquisition)
                if key not in cache:
                    orbit_counter+=1
                    root=archive_for(base['precise_orbits']['archive_root'],code)
                    cache[key]=freeze_orbit_v02(root,acquisition,f'o{orbit_counter:03d}',tmp)
                o=dict(cache[key]); o['side']=side; o['platform_code']=code
                rec['precise_orbits'][side]=o
            pre_ok=rec['precise_orbits']['pre'].get('status')=='PASS'
            post_ok=rec['precise_orbits']['post'].get('status')=='PASS'
            rec['status']='PASS_SNAP14_CANONICAL_AUX_POEORB_BOTH_DATES_SHA256_FROZEN' if pre_ok and post_ok else 'BLOCK_R2_PRECISE_ORBIT_PREREQUISITE_V02'
            rows.append(rec)

    expected_ready=int(entry['compatible_windows_r2_entry_ready'])
    expected_missing=int(entry['missing_windows_preserved'])
    assert len(rows)==expected_ready and len(missing)==expected_missing
    all_orbits_pass=all(r['status']=='PASS_SNAP14_CANONICAL_AUX_POEORB_BOTH_DATES_SHA256_FROZEN' for r in rows)
    vertical_pass=vertical.get('status')=='PASS'
    stable=[{
        'case_id':r['case_id'],'window':r['source_window_execution_identity_sha256'],'projection':r['projection'],
        'pre_eof':r['precise_orbits']['pre'].get('inner_eof_sha256'),'post_eof':r['precise_orbits']['post'].get('inner_eof_sha256'),
        'pre_filename':r['precise_orbits']['pre'].get('filename'),'post_filename':r['precise_orbits']['post'].get('filename')
    } for r in rows]
    identity=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    status='PASS_ALL_SNAP14_CANONICAL_R2_PREREQUISITES_V02_FROZEN_NO_SCIENCE_VALUES' if vertical_pass and all_orbits_pass else 'BLOCK_R2_PREREQUISITES_V02_UNKNOWN_NOT_MISSING'
    out={
        'schema_version':'irfen-ibvf-primary6-sentinel1-r2-prerequisites-v0.2',
        'generated_at':now(),'framework':'IRFEN Independent Basin Validation Framework',
        'deployment_status':'RESEARCH_ONLY','test_only':True,'production_use':False,'production_ready':False,
        'operational_alerting_enabled':False,'uses_operational_event_none_labels':False,
        'territorial_activation_evidence_blinded':True,
        'serious_modeling_gate':'CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT',
        'cohort_id':'PRIMARY6_CHRONOLOGICAL','season_id':entry['season_id'],
        'source_r2_entry':str(args.r2_entry),'source_r2_entry_sha256':sha256_file(args.r2_entry),
        'source_r2_entry_identity_sha256':entry['r2_entry_identity_sha256'],
        'source_base_prereq_contract':str(args.base_prereq_contract),'source_base_prereq_contract_sha256':sha256_file(args.base_prereq_contract),
        'source_orbit_consumption_amendment':str(args.amendment),'source_orbit_consumption_amendment_sha256':sha256_file(args.amendment),
        'v01_prerequisites_superseded_for_execution':True,
        'selector_version':'SNAP14_POEORB_V02',
        'selector_rule':amendment['v02_selector']['selection_rule'],
        'vertical_transform_resource':vertical,
        'compatible_windows_expected':expected_ready,
        'compatible_windows_prerequisites_pass':sum(r['status'].startswith('PASS_') for r in rows),
        'missing_windows_expected':expected_missing,'missing_windows_preserved':len(missing),
        'unique_acquisition_orbit_resources_checked':len(cache),
        'same_orbit_quality_class':'AUX_POEORB','automatic_unhashed_orbit_download_allowed':False,
        'r2_execution_performed':False,'r2_science_pixels_read':False,'r3_common_support_computed':False,'r4_features_computed':False,
        'territorial_outcomes_read':False,'known_event_dates_read':False,'case_control_assignment_performed':False,
        'activation_inference_allowed':False,'modeling_allowed':False,
        'r2_prerequisite_identity_sha256':identity,'entries':rows,'missing_entries':missing,'status':status,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'season':entry['season_id'],'ready':expected_ready,'orbit_pass':out['compatible_windows_prerequisites_pass'],'missing':len(missing),'unique_orbits':len(cache),'identity':identity},indent=2))
    return 0 if status.startswith('PASS_') else 2


if __name__=='__main__':
    raise SystemExit(main())
