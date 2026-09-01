#!/usr/bin/env python3
"""Freeze PRIMARY6 R1->R2 entry identity without reading R2 science values.

RESEARCH_ONLY / TEST_ONLY. Every compatible selected window in the requested
frozen track-season shard must have a completed R1 artifact and asset freeze
that bind to the preassigned window. Missing compatible-pair windows remain
explicit MISSING and never execute, replace, reselect, or impute.

Three engineering pilots were frozen before the later deterministic execution
partition existed. They may enter R2 only through a fail-closed legacy bridge:
the exact blind case/date and exact pre/post pair must match the partition, the
R1 report must cryptographically reference its original freeze, and that freeze
must reference the same already-frozen selected-window identity while proving
that rainfall, SAR response, event dates and territorial outcomes were not used
for pilot selection. The bridge is created before any R2 science values exist.

The output only binds R1 identities to the already-audited R2 graph family. It
does not execute SNAP, read terrain-corrected pixels, compare pre/post data,
assign case/control, read territorial outcomes, or infer activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def load_if_case(path: Path, case_id: str) -> bool:
    if not path.exists():
        return False
    try:
        d=json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return False
    return d.get('case_id')==case_id


def find_artifact(root: Path, unit: str, date_local: str, kind: str) -> Path:
    case_id=f'primary6_{unit}_{date_local}'
    if kind=='r1':
        candidates=[
            root/f'ibvf_primary6_{unit}_{date_local}_s1_r1_v01.json',
            root/f'ibvf_primary6_{unit}_s1_r1_pilot_v01.json',
        ]
        patterns=[f'ibvf_primary6_{unit}*s1*r1*pilot*v01.json']
    elif kind=='freeze':
        candidates=[
            root/f'ibvf_primary6_{unit}_{date_local}_s1_r1_freeze_v01.json',
            root/f'ibvf_primary6_{unit}_s1_r1_pilot_freeze_v01.json',
            # Huaycoloro's first pilot predates the later filename convention.
            root/f'ibvf_primary6_{unit}_s1_pilot_freeze_v01.json',
        ]
        patterns=[f'ibvf_primary6_{unit}*s1*pilot*freeze*v01.json']
    else:
        raise ValueError(kind)
    for path in candidates:
        if load_if_case(path,case_id):
            return path
    seen=set(candidates)
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path in seen:
                continue
            if load_if_case(path,case_id):
                return path
    raise FileNotFoundError(f'No frozen {kind} artifact for {unit}/{date_local}')


def assert_exact_pair(r1: dict[str,Any], fr: dict[str,Any], w: dict[str,Any]) -> None:
    assert fr['pre']['item_id']==w['pre_item_id'] and fr['post']['item_id']==w['post_item_id']
    assert r1['pre']['item_id']==w['pre_item_id'] and r1['post']['item_id']==w['post_item_id']
    if 'pair_rule' in fr:
        assert fr['pair_rule']['pre_item_id']==w['pre_item_id']
        assert fr['pair_rule']['post_item_id']==w['post_item_id']


def legacy_bridge_checks(
    r1: dict[str,Any], fr: dict[str,Any], r1p: Path, frp: Path,
    part: dict[str,Any], w: dict[str,Any], base: dict[str,Any]
) -> None:
    # The original R1 must be byte-bound to the original asset freeze.
    assert r1.get('source_freeze_sha256')==sha256_file(frp)
    # The original blind freeze must stem from the same selected-window set
    # later used by the deterministic partition.
    assert fr.get('source_selected_window_identity_sha256')==part['source_selected_window_identity_sha256']
    assert fr.get('engineering_pilot_only') is True
    assert fr.get('engineering_pilot_selection_changes_scientific_window_set') is False
    assert fr.get('all_104_compatible_pairs_remain_required') is True
    assert fr.get('rainfall_values_read_for_pilot_selection') is False
    assert fr.get('sar_change_values_read_for_pilot_selection') is False
    assert fr.get('territorial_outcomes_read') is False
    assert fr.get('known_event_dates_read') is False
    assert fr.get('case_control_role_assigned') is False
    assert fr.get('activation_inference_allowed') is False
    assert fr.get('modeling_allowed') is False
    assert fr.get('freeze_status')=='ALL_REQUESTED_ASSETS_SHA256_FROZEN'
    assert r1.get('interpretation_forbidden') is True
    assert_exact_pair(r1,fr,w)
    # No later partition provenance is invented. The bridge itself records the
    # exact later window identity and why the older artifact is admissible.
    base['r1_partition_binding_mode']='LEGACY_PILOT_EXACT_CASE_PAIR_AND_SELECTED_WINDOW_IDENTITY_BRIDGE_BEFORE_R2_VALUES'
    base['legacy_pilot_r1_predates_execution_partition']=True
    base['legacy_bridge_source_freeze_sha256_verified']=True
    base['legacy_bridge_selected_window_identity_verified']=True
    base['legacy_bridge_uses_rainfall_magnitude']=False
    base['legacy_bridge_uses_sar_response']=False
    base['legacy_bridge_uses_known_event_dates']=False
    base['legacy_bridge_uses_territorial_outcomes']=False
    base['legacy_bridge_changes_selected_window']=False
    base['legacy_bridge_changes_compatible_pair']=False


def modern_binding_checks(
    r1: dict[str,Any], fr: dict[str,Any], part: dict[str,Any], w: dict[str,Any], base: dict[str,Any]
) -> None:
    assert r1['source_partition_identity_sha256']==part['partition_identity_sha256']
    assert r1['source_window_execution_identity_sha256']==w['window_execution_identity_sha256']
    assert fr['source_partition_identity_sha256']==part['partition_identity_sha256']
    assert fr['source_window_execution_identity_sha256']==w['window_execution_identity_sha256']
    assert fr['freeze_status']=='ALL_REQUESTED_ASSETS_SHA256_FROZEN'
    assert fr['replacement_window_allowed'] is False and fr['pair_reselection_allowed'] is False
    assert fr['territorial_outcomes_read'] is False and fr['known_event_dates_read'] is False
    assert r1['territorial_outcomes_read'] is False and r1['known_event_dates_read'] is False
    assert_exact_pair(r1,fr,w)
    base['r1_partition_binding_mode']='MODERN_EXACT_PARTITION_AND_WINDOW_HASH_BINDING'
    base['legacy_pilot_r1_predates_execution_partition']=False


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--partition',type=Path,required=True)
    ap.add_argument('--handoff-contract',type=Path,required=True)
    ap.add_argument('--validation-root',type=Path,default=Path('site/data/validation'))
    ap.add_argument('--season-id',required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()

    part=json.loads(args.partition.read_text(encoding='utf-8'))
    hand=json.loads(args.handoff_contract.read_text(encoding='utf-8'))
    guards(part); guards(hand)
    assert part['partition_identity_sha256']==hand['source_partition_identity_sha256']
    assert part['selected_window_replacement_allowed'] is False
    assert part['compatible_pair_reselection_allowed'] is False
    assert part['missing_pair_imputation_allowed'] is False
    assert part['territorial_outcomes_read'] is False and part['known_event_dates_read'] is False
    gate=hand['r2_entry_gate']
    assert gate['r1_status_required']=='COMPLETE_BOTH_DATES_NO_COMPARISON'
    assert gate['r1_comparison_performed_required'] is False
    assert gate['replacement_window_allowed'] is False
    assert gate['compatible_pair_reselection_allowed'] is False
    assert gate['missing_pair_imputation_allowed'] is False
    assert hand['decision_timing']['territorial_outcomes_read'] is False
    assert hand['decision_timing']['known_event_dates_read'] is False

    shards=[s for s in part['shards'] if s['season_id']==args.season_id]
    if len(shards)!=3:
        raise ValueError(f'Expected exactly three PRIMARY6 track shards for {args.season_id}; got {len(shards)}')
    entries=[]
    ready=0; missing=0; modern_count=0; legacy_count=0
    graph_family=hand['r2_graph_family']
    for shard in sorted(shards,key=lambda x:x['unit_id']):
        unit=shard['unit_id']
        expected_projection=graph_family['track_projection'][unit]
        assert shard['projection']==expected_projection
        graph_path=graph_family['zone17_graph'] if expected_projection=='EPSG:32717' else graph_family['zone18_graph']
        graph_sha=graph_family['zone17_graph_sha256'] if expected_projection=='EPSG:32717' else graph_family['zone18_graph_sha256']
        gp=Path(graph_path)
        assert gp.exists() and sha256_file(gp)==graph_sha
        for w in shard['windows']:
            base={
                'case_id':f"primary6_{unit}_{w['date_local']}",
                'unit_id':unit,
                'season_id':args.season_id,
                'date_local':w['date_local'],
                'source_window_execution_identity_sha256':w['window_execution_identity_sha256'],
                'projection':expected_projection,
                'r2_graph_path':graph_path,
                'r2_graph_sha256':graph_sha,
                'case_control_role':'UNASSIGNED',
            }
            if w['sar_execution_status'].startswith('MISSING_COMPATIBLE_PAIR'):
                assert w['pre_item_id'] is None and w['post_item_id'] is None
                base.update({
                    'r2_entry_status':'MISSING_COMPATIBLE_PAIR_RETAINED_NO_R2_EXECUTION',
                    'r1_report_path':None,
                    'r1_freeze_path':None,
                    'pre_item_id':None,
                    'post_item_id':None,
                    'replacement_allowed':False,
                    'imputation_allowed':False,
                })
                entries.append(base); missing+=1
                continue
            assert w['sar_execution_status']=='COMPATIBLE_PAIR_FROZEN_PENDING_R1_R4'
            r1p=find_artifact(args.validation_root,unit,w['date_local'],'r1')
            frp=find_artifact(args.validation_root,unit,w['date_local'],'freeze')
            r1=json.loads(r1p.read_text(encoding='utf-8'))
            fr=json.loads(frp.read_text(encoding='utf-8'))
            guards(r1); guards(fr)
            assert r1['case_id']==base['case_id'] and fr['case_id']==base['case_id']
            assert r1['r1_status']=='COMPLETE_BOTH_DATES_NO_COMPARISON'
            assert r1['comparison_performed'] is False
            assert r1['terrain_correction_performed'] is False
            assert r1['common_support_established'] is False

            modern_fields=(
                'source_partition_identity_sha256' in r1 and
                'source_window_execution_identity_sha256' in r1 and
                'source_partition_identity_sha256' in fr and
                'source_window_execution_identity_sha256' in fr
            )
            if modern_fields:
                modern_binding_checks(r1,fr,part,w,base)
                modern_count+=1
            else:
                legacy_bridge_checks(r1,fr,r1p,frp,part,w,base)
                legacy_count+=1

            base.update({
                'r2_entry_status':'PASS_R2_ENTRY_IDENTITY_FROZEN_EXECUTION_NOT_RUN',
                'r1_report_path':str(r1p),
                'r1_report_sha256':sha256_file(r1p),
                'r1_freeze_path':str(frp),
                'r1_freeze_sha256':sha256_file(frp),
                'pre_item_id':w['pre_item_id'],
                'post_item_id':w['post_item_id'],
                'replacement_allowed':False,
                'reselection_allowed':False,
                'imputation_allowed':False,
            })
            entries.append(base); ready+=1

    expected_ready=sum(s['compatible_pair_window_count'] for s in shards)
    expected_missing=sum(s['missing_compatible_pair_count'] for s in shards)
    assert ready==expected_ready and missing==expected_missing
    assert modern_count+legacy_count==ready
    stable=[{k:v for k,v in x.items() if k not in {'r1_report_sha256','r1_freeze_sha256'}} for x in entries]
    identity=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    out={
        'schema_version':'irfen-ibvf-primary6-sentinel1-r2-entry-freeze-v0.2',
        'generated_at':now(),
        'framework':'IRFEN Independent Basin Validation Framework',
        'deployment_status':'RESEARCH_ONLY',
        'test_only':True,
        'production_use':False,
        'production_ready':False,
        'operational_alerting_enabled':False,
        'uses_operational_event_none_labels':False,
        'territorial_activation_evidence_blinded':True,
        'serious_modeling_gate':'CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT',
        'cohort_id':'PRIMARY6_CHRONOLOGICAL',
        'season_id':args.season_id,
        'source_partition_identity_sha256':part['partition_identity_sha256'],
        'source_selected_window_identity_sha256':part['source_selected_window_identity_sha256'],
        'source_handoff_contract':str(args.handoff_contract),
        'source_handoff_contract_sha256':sha256_file(args.handoff_contract),
        'compatible_windows_expected':expected_ready,
        'compatible_windows_r2_entry_ready':ready,
        'modern_exact_partition_bindings':modern_count,
        'legacy_pilot_bridges':legacy_count,
        'legacy_pilot_bridge_created_before_r2_science_values':legacy_count>0,
        'legacy_pilot_bridge_uses_rainfall_magnitude':False,
        'legacy_pilot_bridge_uses_sar_response':False,
        'legacy_pilot_bridge_uses_known_event_dates':False,
        'legacy_pilot_bridge_uses_territorial_outcomes':False,
        'legacy_pilot_bridge_changes_selected_windows_or_pairs':False,
        'missing_windows_expected':expected_missing,
        'missing_windows_preserved':missing,
        'all_compatible_r1_identities_match_partition_or_prepartition_blind_bridge':ready==expected_ready,
        'r2_execution_performed':False,
        'r2_science_pixels_read':False,
        'r3_common_support_computed':False,
        'r4_features_computed':False,
        'territorial_outcomes_read':False,
        'known_event_dates_read':False,
        'case_control_assignment_performed':False,
        'activation_inference_allowed':False,
        'modeling_allowed':False,
        'r2_entry_identity_sha256':identity,
        'entries':entries,
        'status':'PASS_ALL_COMPATIBLE_R1_WINDOWS_BOUND_TO_FROZEN_R2_GRAPH_FAMILY_EXECUTION_NOT_RUN',
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'season':args.season_id,'ready':ready,'modern':modern_count,'legacy_bridge':legacy_count,'missing':missing,'identity':identity},indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
