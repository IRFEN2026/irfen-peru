#!/usr/bin/env python3
"""Sync verified blind observational metrics into the IBVF map manifest."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True,type=Path); ap.add_argument('--features',required=True,type=Path); ap.add_argument('--timebasis',required=True,type=Path); ap.add_argument('--sampling-contract',required=True,type=Path); a=ap.parse_args()
    m=json.loads(a.manifest.read_text(encoding='utf-8')); f=json.loads(a.features.read_text(encoding='utf-8')); t=json.loads(a.timebasis.read_text(encoding='utf-8')); s=json.loads(a.sampling_contract.read_text(encoding='utf-8'))
    assert f['feature_status']=='FROZEN_BLIND_OBSERVATIONAL_FEATURES' and f['raw_identity']['match'] is True
    assert t['source_raw_identity']['match'] is True and t['event_time_used'] is False
    assert all(x.get('production_use') is False for x in (m,f,t,s))
    assert all(x.get('production_ready') is False for x in (m,f,t,s))
    assert all(x.get('operational_alerting_enabled') is False for x in (m,f,t,s))
    assert all(x.get('uses_operational_event_none_labels') is False for x in (m,f,t,s))
    local=t['peru_local_calendar_features']; ant=local['antecedent_ending_local_00']
    m['version']='irfen-independent-basin-validation-map-v1.4'
    m['generated_at']=now()
    m['blind_sampling_contract_path']='data/validation/ibvf_blind_sampling_contract.json'
    ac=m.setdefault('acquisition_contract',{})
    ac['imerg_basin_features_script']='scripts/ibvf_imerg_basin_features_v02.py'
    ac['imerg_timebasis_audit_script']='scripts/ibvf_imerg_timebasis_audit.py'
    ac['blind_sampling_contract']='site/data/validation/ibvf_blind_sampling_contract.json'
    lv=ac.setdefault('local_validation',{})
    lv['github_actions_imerg_basin_features']='SUCCESS_432_OF_432_RAW_IDENTITY_MATCH_AREA_WEIGHTED'
    lv['github_actions_imerg_timebasis_audit']='SUCCESS_UTC_AND_PERU_LOCAL_NO_EVENT_TIME_USED'
    lv['blind_sampling_contract']='PREREGISTERED_BEFORE_PARALLEL_WINDOW_UNBLINDING'
    c=next(x for x in m['cases'] if x.get('unit_id')=='cashahuacra')
    c['framework_stage']='A3_PRECIPITATION_FROZEN_A4_PENDING'
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
    a.manifest.write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'version':m['version'],'stage':c['framework_stage'],'imerg_status':c['imerg_status'],'metrics':c['imerg_observational_metrics']},indent=2,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
