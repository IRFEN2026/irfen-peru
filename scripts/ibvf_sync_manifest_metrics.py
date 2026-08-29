#!/usr/bin/env python3
"""Sync verified blind scientific state into the IBVF map manifest."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',required=True,type=Path)
    ap.add_argument('--features',required=True,type=Path)
    ap.add_argument('--timebasis',required=True,type=Path)
    ap.add_argument('--sampling-contract',required=True,type=Path)
    ap.add_argument('--sentinel-r1',required=True,type=Path)
    ap.add_argument('--sentinel-r2-contract',required=True,type=Path)
    ap.add_argument('--sentinel-r2-prereq-contract',required=True,type=Path)
    ap.add_argument('--parallel-a0-pool',required=True,type=Path)
    ap.add_argument('--meteorological-ranking-contract',required=True,type=Path)
    a=ap.parse_args()
    m=json.loads(a.manifest.read_text(encoding='utf-8'))
    f=json.loads(a.features.read_text(encoding='utf-8'))
    t=json.loads(a.timebasis.read_text(encoding='utf-8'))
    s=json.loads(a.sampling_contract.read_text(encoding='utf-8'))
    r=json.loads(a.sentinel_r1.read_text(encoding='utf-8'))
    r2=json.loads(a.sentinel_r2_contract.read_text(encoding='utf-8'))
    rp=json.loads(a.sentinel_r2_prereq_contract.read_text(encoding='utf-8'))
    pool=json.loads(a.parallel_a0_pool.read_text(encoding='utf-8'))
    rank=json.loads(a.meteorological_ranking_contract.read_text(encoding='utf-8'))
    assert f['feature_status']=='FROZEN_BLIND_OBSERVATIONAL_FEATURES' and f['raw_identity']['match'] is True
    assert t['source_raw_identity']['match'] is True and t['event_time_used'] is False
    assert r['r1_status']=='COMPLETE_BOTH_DATES_NO_COMPARISON'
    assert r['comparison_performed'] is False and r['terrain_correction_performed'] is False and r['common_support_established'] is False
    assert r['pre']['status']=='R1_NATIVE_RADIOMETRIC_COMPLETE' and r['post']['status']=='R1_NATIVE_RADIOMETRIC_COMPLETE'
    assert r['pre']['diagnostics']['valid_sigma0_fraction']==1.0 and r['post']['diagnostics']['valid_sigma0_fraction']==1.0
    assert r2['status']=='PREREGISTERED_R2_BLOCKED_ON_VERTICAL_DATUM_AND_ORBIT_AUX_IDENTITY'
    assert r2['r4_difference_gate']['pre_post_difference_computed_at_contract_time'] is False
    assert rp['status']=='PREREGISTERED_EXECUTABLE_PREREQUISITE_FREEZE_PENDING'
    assert rp['pre_post_difference_allowed'] is False and rp['activation_inference_allowed'] is False
    assert pool['pool_role']=='UNASSIGNED_BLIND_WINDOW' and pool['case_control_assignment_allowed'] is False
    assert pool['summary']['unique_calendar_days_per_track']==2907 and pool['summary']['track_day_windows']==11628
    assert pool['summary']['track_count']==4 and set(pool['tracks'])=={'shingolay','pedregal','huaycoloro','san_ildefonso'}
    assert pool['summary']['days_removed_for_sensor_missing']==0 and pool['summary']['days_removed_for_outcome']==0
    assert rank['execution_status']=='PREREGISTERED_NOT_YET_EXECUTED'
    assert rank['inputs_allowed']['cashahuacra_remote_magnitudes'] is False and rank['inputs_allowed']['territorial_outcomes'] is False
    assert rank['role_semantics']['case_control_assignment_only_after_independent_territorial_unblind'] is True
    objs=(m,f,t,s,r,r2,rp,pool,rank)
    assert all(x.get('production_use') is False for x in objs)
    assert all(x.get('production_ready') is False for x in objs)
    assert all(x.get('operational_alerting_enabled') is False for x in objs)
    assert all(x.get('uses_operational_event_none_labels') is False for x in objs)
    assert all(x.get('territorial_activation_evidence_blinded') is True for x in (m,r,r2,rp,pool,rank))
    local=t['peru_local_calendar_features']; ant=local['antecedent_ending_local_00']
    m['version']='irfen-independent-basin-validation-map-v1.8'
    m['generated_at']=now()
    m['blind_sampling_contract_path']='data/validation/ibvf_blind_sampling_contract.json'
    m['parallel_a0_pool_path']='data/validation/ibvf_parallel_a0_pool_inventory.json'
    m['parallel_a0_pool_status']='FROZEN_EXHAUSTIVE_FOUR_TRACK_CALENDAR_NO_WINDOW_SELECTED'
    m['meteorological_ranking_contract_path']='data/validation/ibvf_meteorological_ranking_contract.json'
    m['meteorological_ranking_status']='PREREGISTERED_NOT_EXECUTED_NO_WINDOW_SELECTED'
    m['parallel_a0_pool_summary']={
      'tracks':pool['tracks'],'season_count':pool['summary']['season_count'],
      'unique_calendar_days_per_track':pool['summary']['unique_calendar_days_per_track'],
      'track_day_windows':pool['summary']['track_day_windows'],'case_control_assignment_allowed':False,
      'meteorological_ranking_status':m['meteorological_ranking_status'],
      'maximum_primary_stratified_windows':rank['primary_selection']['maximum_primary_windows']
    }
    ac=m.setdefault('acquisition_contract',{})
    ac['imerg_basin_features_script']='scripts/ibvf_imerg_basin_features_v02.py'; ac['imerg_timebasis_audit_script']='scripts/ibvf_imerg_timebasis_audit.py'
    ac['blind_sampling_contract']='site/data/validation/ibvf_blind_sampling_contract.json'; ac['parallel_a0_pool']='site/data/validation/ibvf_parallel_a0_pool_inventory.json'
    ac['meteorological_ranking_contract']='site/data/validation/ibvf_meteorological_ranking_contract.json'
    ac['sentinel1_r1_script']='scripts/ibvf_sentinel1_r1_radiometric.py'; ac['sentinel1_r1_report']='site/data/validation/cashahuacra_sentinel1_r1.json'
    ac['sentinel1_r2_contract']='site/data/validation/cashahuacra_sentinel1_r2_contract.json'; ac['sentinel1_r2_prerequisites_contract']='site/data/validation/cashahuacra_sentinel1_r2_prerequisites_contract.json'; ac['sentinel1_r2_prerequisites_script']='scripts/ibvf_sentinel1_r2_freeze_prerequisites.py'
    lv=ac.setdefault('local_validation',{})
    lv['github_actions_imerg_basin_features']='SUCCESS_432_OF_432_RAW_IDENTITY_MATCH_AREA_WEIGHTED'; lv['github_actions_imerg_timebasis_audit']='SUCCESS_UTC_AND_PERU_LOCAL_NO_EVENT_TIME_USED'
    lv['blind_sampling_contract']='PREREGISTERED_BEFORE_PARALLEL_WINDOW_UNBLINDING'
    lv['parallel_a0_pool']='FROZEN_2907_DAYS_PER_TRACK_4_TRACKS_11628_TRACK_DAY_WINDOWS_NO_SELECTION'
    lv['meteorological_ranking_contract']='PREREGISTERED_6_FIXED_PERCENTILE_STRATA_PER_TRACK_SEASON_NO_EXECUTION'
    lv['github_actions_sentinel1_a4_r1']='SUCCESS_BOTH_DATES_NATIVE_RADIOMETRIC_NO_COMPARISON'; lv['sentinel1_a4_r2_contract']='PREREGISTERED_BLOCKED_VERTICAL_DATUM_AND_ORBIT_AUX_IDENTITY'; lv['sentinel1_a4_r2_prerequisite_freezer']='IMPLEMENTED_EXECUTION_PENDING'
    c=next(x for x in m['cases'] if x.get('unit_id')=='cashahuacra')
    c['framework_stage']='A4_R1_COMPLETE_R2_PREREQUISITE_FREEZER_IMPLEMENTED_GATE_PENDING'; c['geometry_area_km2']=15.088
    c['imerg_status']=f"FROZEN_LOCAL_P3H_{local['p3h_max']['depth_mm']:.2f}_P24H_{local['p24h_total_mm']:.2f}_ANT7D_{ant['p7d_mm']:.2f}_MM"
    c['imerg_basin_features_path']='data/validation/cashahuacra_imerg_basin_features.json'; c['imerg_timebasis_audit_path']='data/validation/cashahuacra_imerg_timebasis_audit.json'
    c['imerg_observational_metrics']={'time_basis':'PERU_LOCAL_CALENDAR_DAY_UTC_MINUS_5','p30m_max_mm':local['p30m_max_mm'],'p1h_max_mm':local['p1h_max']['depth_mm'],'p3h_max_mm':local['p3h_max']['depth_mm'],'p6h_max_mm':local['p6h_max']['depth_mm'],'p12h_max_mm':local['p12h_max']['depth_mm'],'p24h_mm':local['p24h_total_mm'],'antecedent_24h_mm':ant['p24h_mm'],'antecedent_72h_mm':ant['p72h_mm'],'antecedent_7d_mm':ant['p7d_mm']}
    c['imerg_timebasis_sensitivity']={'utc_p24h_mm':t['utc_calendar_features']['p24h_total_mm'],'peru_local_p24h_mm':local['p24h_total_mm'],'local_minus_utc_mm':t['comparison']['p24h_local_minus_utc_mm'],'event_time_used':False}
    c['blind_sampling_contract_status']='PREREGISTERED_FOR_PARALLEL_WINDOWS'; c['remote_sensing_status']='S1_A4_R1_COMPLETE_R2_PREREQUISITE_RESOURCE_FREEZE_PENDING_LANDSAT_QA_DIAGNOSTIC_ONLY'
    c['sentinel1_r1_path']='data/validation/cashahuacra_sentinel1_r1.json'; c['sentinel1_r1_status']=r['r1_status']; c['sentinel1_r1_comparison_performed']=False; c['sentinel1_r1_common_support_established']=False
    c['sentinel1_r1_pre_valid_fraction']=r['pre']['diagnostics']['valid_sigma0_fraction']; c['sentinel1_r1_post_valid_fraction']=r['post']['diagnostics']['valid_sigma0_fraction']
    ev=r.get('execution_evidence',{}); c['sentinel1_r1_workflow_run_id']=ev.get('workflow_run_id'); c['sentinel1_r1_artifact_id']=ev.get('artifact_id'); c['sentinel1_r1_artifact_digest_sha256']=ev.get('artifact_digest_sha256')
    c['sentinel1_r2_contract_path']='data/validation/cashahuacra_sentinel1_r2_contract.json'; c['sentinel1_r2_prerequisites_contract_path']='data/validation/cashahuacra_sentinel1_r2_prerequisites_contract.json'; c['sentinel1_r2_prerequisites_status']=rp['status']; c['sentinel1_r2_status']=r2['status']; c['sentinel1_r2_vertical_datum_gate']=r2['vertical_datum_gate']['status']; c['sentinel1_r2_orbit_gate']=r2['orbit_gate']['status']
    for unit in pool['tracks']:
        pc=next(x for x in m['cases'] if x.get('unit_id')==unit)
        pc['framework_stage']='A0_EXHAUSTIVE_POOL_AND_RANKING_CONTRACT_FROZEN_NO_WINDOW_SELECTED'; pc['blind_window']='NOT_YET_SELECTED_FROM_FROZEN_POOL'
        pc['a0_pool_status']='FROZEN_2907_UNASSIGNED_LOCAL_DAYS'; pc['a0_pool_path']='data/validation/ibvf_parallel_a0_pool_inventory.json'; pc['a0_case_control_role']='UNASSIGNED'; pc['meteorological_ranking_status']='PREREGISTERED_NOT_EXECUTED'; pc['blind_status']='TERRITORIAL_EVIDENCE_SEALED'
    a.manifest.write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'version':m['version'],'cashahuacra_stage':c['framework_stage'],'parallel_pool':m['parallel_a0_pool_status'],'track_day_windows':pool['summary']['track_day_windows'],'ranking':m['meteorological_ranking_status'],'gate':m['serious_modeling_gate']},indent=2,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
