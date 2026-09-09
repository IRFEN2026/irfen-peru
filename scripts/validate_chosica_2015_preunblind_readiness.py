#!/usr/bin/env python3
"""Validate Chosica-2015 pre-unblind frozen assets without reading any outcome source."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GUARDS={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}

def load(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=load(a.contract)
    rep={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PENDING','guards':GUARDS,'outcome_evidence_read':False,
         'candidate_outcome_evidence_read':False,'a6680_outcome_narrative_read':False,'a6680_numeric_reference_read':False,
         'post_anchor_predictor_read':False,'sealed_target_unblind_performed':False,'contract_sha256':sha(a.contract),'checks':{}}
    try:
        if co['guards']!=GUARDS: raise RuntimeError('FAIL_CLOSED_CONTRACT_GUARDS')
        paths={k:ROOT/v for k,v in co['required_records'].items()}
        docs={k:load(p) for k,p in paths.items()}
        val=docs['validation_set']; reg=docs['outlet_geometry_freeze']; morph=docs['morphometry_freeze']; imerg=docs['imerg_freeze']; pool=docs['negative_control_pool_freeze']; match=docs['negative_control_matching_freeze']; hand=docs['blinding_recovery_handoff']
        for name,d in docs.items():
            g=d.get('guards',{})
            if name=='validation_set':
                if g!=GUARDS: raise RuntimeError(f'FAIL_CLOSED_GUARDS {name}')
            elif name=='outlet_geometry_freeze':
                if g!=GUARDS: raise RuntimeError(f'FAIL_CLOSED_GUARDS {name}')
            elif name in {'morphometry_freeze','imerg_freeze','negative_control_pool_freeze','negative_control_matching_freeze','blinding_recovery_handoff'}:
                if g!=GUARDS: raise RuntimeError(f'FAIL_CLOSED_GUARDS {name}')
        gate=reg['batch_gate']
        if gate['frozen_outlet_count']!=6 or gate['required_frozen_outlet_count']!=6: raise RuntimeError('FAIL_CLOSED_OUTLET_COUNT')
        if gate['frozen_geometry_count']!=6 or gate['required_frozen_geometry_count']!=6: raise RuntimeError('FAIL_CLOSED_GEOMETRY_COUNT')
        if gate['unblind_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_LEGACY_UNBLIND_GATE_OPEN')
        if any(t['outlet_status']!='FROZEN' or t['geometry_status']!='FROZEN_BY_REPRODUCIBLE_D8_HASH' for t in reg['targets'].values()): raise RuntimeError('FAIL_CLOSED_TARGET_FREEZE')
        if morph['phase1_frozen'] is not True or morph['expected_report']['outcome_evidence_read'] is not False or morph['expected_report']['a6680_numeric_reference_read'] is not False or morph['expected_report']['post_anchor_predictor_read'] is not False: raise RuntimeError('FAIL_CLOSED_MORPHOMETRY_FREEZE')
        if imerg['predictors_frozen'] is not True or imerg['expected_report']['target_count']!=6 or imerg['expected_report']['coverage_fraction_per_target']!=1.0: raise RuntimeError('FAIL_CLOSED_IMERG_FREEZE')
        if imerg['expected_report']['outcome_evidence_read'] is not False or imerg['expected_report']['a6680_numeric_reference_read'] is not False or imerg['expected_report']['post_anchor_predictor_read'] is not False: raise RuntimeError('FAIL_CLOSED_IMERG_BLIND_GUARD')
        if pool['status']!='NEGATIVE_CONTROL_CANDIDATE_POOL_FROZEN_BY_COMMITTED_HASH' or pool['candidate_count']!=29: raise RuntimeError('FAIL_CLOSED_CONTROL_POOL_FREEZE')
        if any(pool['anti_leakage'].values()): raise RuntimeError('FAIL_CLOSED_CONTROL_POOL_LEAKAGE')
        if match['status']!='NEGATIVE_CONTROL_MATCHING_FROZEN_BEFORE_OUTCOME_ADJUDICATION': raise RuntimeError('FAIL_CLOSED_CONTROL_MATCH_FREEZE')
        if match['execution_result']['candidate_count']!=29 or match['execution_result']['eligible_candidate_count']!=29: raise RuntimeError('FAIL_CLOSED_CONTROL_MATCH_COUNTS')
        if set(match['execution_result']['shortlists'])!={'cashahuacra','quirio','pedregal_san_antonio','la_libertad','carossio','rayos_de_sol'}: raise RuntimeError('FAIL_CLOSED_SHORTLIST_TARGETS')
        if not all(len(v)==3 for v in match['execution_result']['shortlists'].values()): raise RuntimeError('FAIL_CLOSED_SHORTLIST_LENGTH')
        if any(match['anti_leakage'].values()): raise RuntimeError('FAIL_CLOSED_CONTROL_MATCH_LEAKAGE')
        if hand['status']!='BLINDING_RECOVERY_HANDOFF_ACTIVE' or hand['recovery_decision']['choice']!='PRESERVE_STRICT_BLIND_VALIDATION_SEMANTICS_WITH_FRESH_PROCESS': raise RuntimeError('FAIL_CLOSED_RECOVERY_HANDOFF')
        if hand['process_separation']['fresh_process_outcome_evidence_read'] is not False or hand['process_separation']['fresh_process_candidate_outcome_evidence_read'] is not False: raise RuntimeError('FAIL_CLOSED_RECOVERY_LEAKAGE')
        if hand['current_gate']['sealed_target_outcome_unblind_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_RECOVERY_UNBLIND_OPEN')
        targets=val['targets']
        if len(targets)!=6 or any(t['outcome_label']!='SEALED' for t in targets): raise RuntimeError('FAIL_CLOSED_TARGET_OUTCOMES_NOT_SEALED')
        hashes={k:sha(p) for k,p in paths.items()}
        rep['checks']={'outlets_frozen':6,'geometries_frozen':6,'morphometry_frozen':True,'imerg_frozen':True,'imerg_coverage_fraction':1.0,
                       'negative_control_candidate_pool_frozen':True,'negative_control_candidate_count':29,'negative_control_matching_frozen':True,
                       'shortlist_per_target':3,'fresh_blind_recovery_active':True,'target_outcomes_sealed':True,'record_sha256':hashes}
        rep['status']='PASS_PREUNBLIND_CORE_FREEZES_PENDING_CONTROL_OUTCOME_ADJUDICATION'
        rep['next_gate']='CONTROL_OUTCOME_ADJUDICATION_ON_FROZEN_SHORTLIST_ONLY'
        rep['sealed_target_outcome_unblind_allowed']=False
    except Exception as e:
        rep['status']='FAIL_CLOSED_PREUNBLIND_READINESS'; rep['error']=str(e); rep['sealed_target_outcome_unblind_allowed']=False
        a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 2
    a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
