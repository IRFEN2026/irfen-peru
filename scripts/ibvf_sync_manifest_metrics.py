#!/usr/bin/env python3
"""Sync verified blind observational metrics into the IBVF map manifest."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True,type=Path); ap.add_argument('--features',required=True,type=Path); ap.add_argument('--timebasis',required=True,type=Path); ap.add_argument('--sampling-contract',required=True,type=Path); ap.add_argument('--sentinel-r1',required=True,type=Path); a=ap.parse_args()
    m=json.loads(a.manifest.read_text(encoding='utf-8')); f=json.loads(a.features.read_text(encoding='utf-8')); t=json.loads(a.timebasis.read_text(encoding='utf-8')); s=json.loads(a.sampling_contract.read_text(encoding='utf-8')); r=json.loads(a.sentinel_r1.read_text(encoding='utf-8'))
    assert f['feature_status']=='FROZEN_BLIND_OBSERVATIONAL_FEATURES' and f['raw_identity']['match'] is True
    assert t['source_raw_identity']['match'] is True and t['event_time_used'] is False
    assert r['r1_status']=='COMPLETE_BOTH_DATES_NO_COMPARISON'
    assert r['comparison_performed'] is False and r['terrain_correction_performed'] is False and r['common_support_established'] is False
    assert r['pre']['status']=='R1_NATIVE_RADIOMETRIC_COMPLETE' and r['post']['status']=='R1_NATIVE_RADIOMETRIC_COMPLETE'
    assert r['pre']['diagnostics']['valid_sigma0_fraction']==1.0 and r['post']['diagnostics']['valid_sigma0_fraction']==1.0
    objs=(m,f,t,s,r)
    assert all(x.get('production_use') is False for x in objs)
    assert all(x.get('production_ready') is False for x in objs)
    assert all(x.get('operational_alerting_enabled') is False for x in objs)
    assert all(x.get('uses_operational_event_none_labels') is False for x in objs)
    assert r['territorial_activation_evidence_blinded'] is True
    local=t['peru_local_calendar_features']; ant=local['antecedent_ending_local_00']
    m['version']='irfen-independent-basin-validation-map-v1.5'
    m['generated_at']=now()
    m['blind_sampling_contract_path']='data/validation/ibvf_blind_sampling_contract.json'
    ac=m.setdefault('acquisition_contract',{})
    ac['imerg_basin_features_script']='scripts/ibvf_imerg_basin_features_v02.py'
    ac['imerg_timebasis_audit_script']='scripts/ibvf_imerg_timebasis_audit.py'
    ac['blind_sampling_contract']='site/data/validation/ibvf_blind_sampling_contract.json'
    ac['sentinel1_r1_script']='scripts/ibvf_sentinel1_r1_radiometric.py'
    ac['sentinel1_r1_report']='site/data/validation/cashahuacra_sentinel1_r1.json'
    lv=ac.setdefault('local_validation',{})
    lv['github_actions_imerg_basin_features']='SUCCESS_432_OF_432_RAW_IDENTITY_MATCH_AREA_WEIGHTED'
    lv['github_actions_imerg_timebasis_audit']='SUCCESS_UTC_AND_PERU_LOCAL_NO_EVENT_TIME_USED'
    lv['blind_sampling_contract']='PREREGISTERED_BEFORE_PARALLEL_WINDOW_UNBLINDING'
    lv['github_actions_sentinel1_a4_r1']='SUCCESS_BOTH_DATES_NATIVE_RADIOMETRIC_NO_COMPARISON'
    c=next(x for x in m['cases'] if x.get('unit_id')=='cashahuacra')
    c['framework_stage']='A4_R1_NATIVE_RADIOMETRIC_COMPLETE_R2_PENDING'
    c['geometry_area_km2']=15.088
    c['imerg_status']=f"FROZEN_LOCAL_P3H_{local['p3h_max']['depth_mm']:.2f}_P24H_{local['p24h_total_mm']:.2f}_ANT7D_{ant['p7d_mm']:.2f}_MM"
    c['imerg_basin_features_path']='data/validation/cashahuacra_imerg_basin_features.json'
    c['imerg_timebasis_audit_path']='data/validation/cashahuacra_imerg_timebasis_audit.json'
    c['imerg_observational_metrics']={
      'time_basis':'PERU_LOCAL_CALENDAR_DAY_UTC_MINUS_5',
      'p30m_max_mm':local['p30m_max_mm'],
      'p1h_max_mm':local['p1h_max']['depth_mm'],
      'p3h_max_mm':local['p3h_max']['depth_mm'],
      'p6h_max_mm':local['p6h_max']['depth_mm'],
      'p12h_max_mm':local['p12h_max']['depth_mm'],
      'p24h_mm':local['p24h_total_mm'],
      'antecedent_24h_mm':ant['p24h_mm'],
      'antecedent_72h_mm':ant['p72h_mm'],
      'antecedent_7d_mm':ant['p7d_mm']
    }
    c['imerg_timebasis_sensitivity']={'utc_p24h_mm':t['utc_calendar_features']['p24h_total_mm'],'peru_local_p24h_mm':local['p24h_total_mm'],'local_minus_utc_mm':t['comparison']['p24h_local_minus_utc_mm'],'event_time_used':False}
    c['blind_sampling_contract_status']='PREREGISTERED_FOR_PARALLEL_WINDOWS'
    c['remote_sensing_status']='S1_A4_R1_COMPLETE_NO_COMPARISON_R2_COMMON_GRID_PENDING_LANDSAT_QA_DIAGNOSTIC_ONLY'
    c['sentinel1_r1_path']='data/validation/cashahuacra_sentinel1_r1.json'
    c['sentinel1_r1_status']=r['r1_status']
    c['sentinel1_r1_comparison_performed']=False
    c['sentinel1_r1_common_support_established']=False
    c['sentinel1_r1_pre_valid_fraction']=r['pre']['diagnostics']['valid_sigma0_fraction']
    c['sentinel1_r1_post_valid_fraction']=r['post']['diagnostics']['valid_sigma0_fraction']
    ev=r.get('execution_evidence',{})
    c['sentinel1_r1_workflow_run_id']=ev.get('workflow_run_id')
    c['sentinel1_r1_artifact_id']=ev.get('artifact_id')
    c['sentinel1_r1_artifact_digest_sha256']=ev.get('artifact_digest_sha256')
    a.manifest.write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'version':m['version'],'stage':c['framework_stage'],'imerg_status':c['imerg_status'],'sentinel1_r1_status':c['sentinel1_r1_status'],'comparison_performed':False,'gate':m['serious_modeling_gate']},indent=2,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
