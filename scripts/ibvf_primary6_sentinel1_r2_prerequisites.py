#!/usr/bin/env python3
"""Freeze PRIMARY6 Sentinel-1 R2 prerequisites without reading SAR response.

RESEARCH_ONLY / TEST_ONLY. Uses the already-frozen R2 entry manifest and the
pre-registered Cashahuacra prerequisite resource rules. The EGM2008 vertical
grid is frozen once per run. Exact AUX_POEORB resources are enumerated from
the authoritative STEP archive for each unique pre/post acquisition and are
SHA256-frozen before R2. No terrain-corrected pixels, pre/post differences,
outcomes, known event dates, case/control roles, or activation inference are
read or produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ibvf_sentinel1_r2_freeze_prerequisites import freeze_orbit, freeze_vertical


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guards(d: dict[str, Any]) -> None:
    assert d['deployment_status']=='RESEARCH_ONLY'
    assert d['test_only'] is True
    assert d['production_use'] is False
    assert d['production_ready'] is False
    assert d['operational_alerting_enabled'] is False
    assert d['uses_operational_event_none_labels'] is False
    assert d['territorial_activation_evidence_blinded'] is True


def satellite_code(item_id: str) -> str:
    code=item_id[:3].upper()
    if code not in {'S1A','S1B'}:
        raise ValueError(f'unsupported Sentinel-1 platform prefix: {item_id}')
    return code


def archive_for(base_root: str, code: str) -> str:
    parent=base_root.rstrip('/').rsplit('/',1)[0]
    return f'{parent}/{code}/'


def load_exact_freeze(path: Path, entry: dict[str,Any]) -> dict[str,Any]:
    d=json.loads(path.read_text(encoding='utf-8'))
    guards(d)
    assert d['case_id']==entry['case_id']
    assert d.get('unit_id', entry['unit_id'])==entry['unit_id']
    assert d['pre']['item_id']==entry['pre_item_id'] and d['post']['item_id']==entry['post_item_id']

    legacy=bool(entry.get('legacy_pilot_r1_predates_execution_partition'))
    if legacy:
        # These three engineering pilots predate season/date fields in the later
        # exact-window freeze schema. Their admissibility was already frozen by
        # ibvf_primary6_sentinel1_r2_entry_freeze.py before R2 science values.
        # Re-assert that bridge here instead of inventing missing provenance.
        assert entry.get('r1_partition_binding_mode')=='LEGACY_PILOT_EXACT_CASE_PAIR_AND_SELECTED_WINDOW_IDENTITY_BRIDGE_BEFORE_R2_VALUES'
        assert entry.get('legacy_bridge_source_freeze_sha256_verified') is True
        assert entry.get('legacy_bridge_selected_window_identity_verified') is True
        assert entry.get('legacy_bridge_uses_rainfall_magnitude') is False
        assert entry.get('legacy_bridge_uses_sar_response') is False
        assert entry.get('legacy_bridge_uses_known_event_dates') is False
        assert entry.get('legacy_bridge_uses_territorial_outcomes') is False
        assert entry.get('legacy_bridge_changes_selected_window') is False
        assert entry.get('legacy_bridge_changes_compatible_pair') is False
        assert d.get('engineering_pilot_only') is True
        assert d.get('engineering_pilot_selection_changes_scientific_window_set') is False
        assert d.get('all_104_compatible_pairs_remain_required') is True
        assert d.get('rainfall_values_read_for_pilot_selection') is False
        assert d.get('sar_change_values_read_for_pilot_selection') is False
        assert d.get('territorial_outcomes_read') is False
        assert d.get('known_event_dates_read') is False
        assert d.get('case_control_role_assigned') is False
        assert d.get('activation_inference_allowed') is False
        assert d.get('modeling_allowed') is False
        assert d.get('freeze_status')=='ALL_REQUESTED_ASSETS_SHA256_FROZEN'
    else:
        assert d['season_id']==entry['season_id']
        assert d['date_local']==entry['date_local']
        assert d['territorial_outcomes_read'] is False and d['known_event_dates_read'] is False
        assert d['replacement_window_allowed'] is False and d['pair_reselection_allowed'] is False
    return d


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--r2-entry',type=Path,required=True)
    ap.add_argument('--base-prereq-contract',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()

    entry=json.loads(args.r2_entry.read_text(encoding='utf-8'))
    base=json.loads(args.base_prereq_contract.read_text(encoding='utf-8'))
    guards(entry); guards(base)
    assert entry['r2_execution_performed'] is False and entry['r2_science_pixels_read'] is False
    assert entry['territorial_outcomes_read'] is False and entry['known_event_dates_read'] is False
    assert entry['case_control_assignment_performed'] is False
    assert entry['activation_inference_allowed'] is False and entry['modeling_allowed'] is False
    assert base['pre_post_difference_allowed'] is False and base['activation_inference_allowed'] is False
    assert base['precise_orbits']['product_class']=='AUX_POEORB'
    assert base['precise_orbits']['same_orbit_quality_class_required'] is True
    assert base['precise_orbits']['automatic_unhashed_orbit_download_allowed'] is False

    rows=[]; missing=[]
    with tempfile.TemporaryDirectory(prefix='ibvf-primary6-r2-prereq-') as td:
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
                    cache[key]=freeze_orbit(root,acquisition,f'o{orbit_counter:03d}',tmp)
                o=dict(cache[key]); o['side']=side; o['platform_code']=code
                o['selection_rule']='EXACTLY_ONE_AUX_POEORB_VALIDITY_INTERVAL_COVERS_FROZEN_ACQUISITION_UTC'
                rec['precise_orbits'][side]=o
            pre_ok=rec['precise_orbits']['pre'].get('status')=='PASS'
            post_ok=rec['precise_orbits']['post'].get('status')=='PASS'
            rec['status']='PASS_EXACT_AUX_POEORB_BOTH_DATES_SHA256_FROZEN' if pre_ok and post_ok else 'BLOCK_R2_PRECISE_ORBIT_PREREQUISITE'
            rows.append(rec)

    expected_ready=int(entry['compatible_windows_r2_entry_ready'])
    expected_missing=int(entry['missing_windows_preserved'])
    assert len(rows)==expected_ready and len(missing)==expected_missing
    all_orbits_pass=all(r['status']=='PASS_EXACT_AUX_POEORB_BOTH_DATES_SHA256_FROZEN' for r in rows)
    vertical_pass=vertical.get('status')=='PASS'
    stable=[{
        'case_id':r['case_id'],'window':r['source_window_execution_identity_sha256'],'projection':r['projection'],
        'pre_eof':r['precise_orbits']['pre'].get('inner_eof_sha256'),'post_eof':r['precise_orbits']['post'].get('inner_eof_sha256')
    } for r in rows]
    identity=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    status='PASS_ALL_R2_PREREQUISITES_FROZEN_NO_SCIENCE_VALUES' if vertical_pass and all_orbits_pass else 'BLOCK_R2_PREREQUISITES_UNKNOWN_NOT_MISSING'
    out={
        'schema_version':'irfen-ibvf-primary6-sentinel1-r2-prerequisites-v0.1',
        'generated_at':now(),'framework':'IRFEN Independent Basin Validation Framework',
        'deployment_status':'RESEARCH_ONLY','test_only':True,'production_use':False,'production_ready':False,
        'operational_alerting_enabled':False,'uses_operational_event_none_labels':False,
        'territorial_activation_evidence_blinded':True,
        'serious_modeling_gate':'CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT',
        'cohort_id':'PRIMARY6_CHRONOLOGICAL','season_id':entry['season_id'],
        'source_r2_entry':str(args.r2_entry),'source_r2_entry_sha256':sha256_file(args.r2_entry),
        'source_r2_entry_identity_sha256':entry['r2_entry_identity_sha256'],
        'source_base_prereq_contract':str(args.base_prereq_contract),'source_base_prereq_contract_sha256':sha256_file(args.base_prereq_contract),
        'vertical_transform_resource':vertical,
        'compatible_windows_expected':expected_ready,'compatible_windows_prerequisites_pass':sum(r['status'].startswith('PASS_') for r in rows),
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
    return 0


if __name__=='__main__':
    raise SystemExit(main())
