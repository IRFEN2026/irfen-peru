#!/usr/bin/env python3
"""Validate Chosica-2015 pre-unblind frozen assets after clean-room recovery, without reading outcomes."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GUARDS={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}
CONTROL_IDS={'NC_001','NC_007','NC_017','NC_019','NC_023','NC_024','NC_027'}

def load(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def code(cid): return 'C_'+hashlib.sha256(cid.encode('utf-8')).hexdigest()[:12]

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
        val=docs['validation_set']; reg=docs['outlet_geometry_freeze']; morph=docs['morphometry_freeze']; imerg=docs['imerg_freeze']
        pool=docs['negative_control_pool_freeze']; oldmatch=docs['negative_control_matching_freeze_preincident']
        geom=docs['negative_control_shortlist_geometry_freeze']; ctrl_imerg=docs['negative_control_imerg_freeze']; hand=docs['blinding_recovery_handoff']
        contam=docs['contamination_registry']; clean=docs['cleanroom_recovery_freeze']; territorial=docs['candidate_only_territorial_contract']; packet=docs['candidate_only_review_packet']
        ingest=docs['candidate_only_adjudication_ingest_contract']; target_ready=docs['target_unblind_readiness_contract']
        for name,d in docs.items():
            if d.get('guards',{})!=GUARDS: raise RuntimeError(f'FAIL_CLOSED_GUARDS {name}')

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

        if oldmatch['status']!='NEGATIVE_CONTROL_MATCHING_FROZEN_BEFORE_OUTCOME_ADJUDICATION': raise RuntimeError('FAIL_CLOSED_PREINCIDENT_MATCH_FREEZE')
        if oldmatch['execution_result']['candidate_count']!=29 or oldmatch['execution_result']['eligible_candidate_count']!=29: raise RuntimeError('FAIL_CLOSED_PREINCIDENT_MATCH_COUNTS')
        if any(oldmatch['anti_leakage'].values()): raise RuntimeError('FAIL_CLOSED_PREINCIDENT_MATCH_LEAKAGE')

        if geom['status']!='NEGATIVE_CONTROL_SHORTLIST_GEOMETRY_FROZEN_BY_EXACT_HASH': raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_FREEZE')
        if geom['frozen_outputs']['candidate_count']!=7 or geom['frozen_outputs']['catchment_touches_dem_boundary'] is not False: raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_COUNTS')
        if set(geom['frozen_inputs']['shortlisted_candidate_ids'])!=CONTROL_IDS: raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_IDS')
        if geom['frozen_inputs']['candidate_pool_sha256']!=oldmatch['candidate_pool_sha256']: raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_POOL_HASH')
        if geom['frozen_inputs']['matching_freeze_record_sha256']!=sha(paths['negative_control_matching_freeze_preincident']): raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_MATCH_HASH')
        if any(geom['anti_leakage'].values()): raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_LEAKAGE')
        geom_contract=ROOT/geom['contract']['path']
        if sha(geom_contract)!=geom['contract']['sha256']: raise RuntimeError('FAIL_CLOSED_CONTROL_GEOMETRY_CONTRACT_HASH')

        if ctrl_imerg['status']!='NEGATIVE_CONTROL_PREUNBLIND_IMERG_FROZEN_BY_EXACT_REPORT_HASH' or ctrl_imerg['predictors_frozen'] is not True: raise RuntimeError('FAIL_CLOSED_CONTROL_IMERG_FREEZE')
        e=ctrl_imerg['expected_report']
        if e['candidate_count']!=7 or set(e['candidate_ids'])!=CONTROL_IDS or e['slot_count_per_candidate']!=720 or e['valid_slot_count_per_candidate']!=720 or e['coverage_fraction_per_candidate']!=1.0: raise RuntimeError('FAIL_CLOSED_CONTROL_IMERG_DIMENSIONS')
        if e['geometry_geojson_sha256']!=geom['frozen_outputs']['geojson_sha256']: raise RuntimeError('FAIL_CLOSED_CONTROL_IMERG_GEOMETRY_HASH')
        for key in ('outcome_evidence_read','candidate_outcome_evidence_read','a6680_numeric_reference_read','post_anchor_predictor_read','sealed_target_unblind_performed','control_outcome_adjudication_performed','geometry_or_pour_point_modified','candidate_replaced','window_shifted','zero_imputation_used'):
            if e[key] is not False: raise RuntimeError(f'FAIL_CLOSED_CONTROL_IMERG_FLAG {key}')

        if hand['status']!='BLINDING_RECOVERY_HANDOFF_ACTIVE' or hand['recovery_decision']['choice']!='PRESERVE_STRICT_BLIND_VALIDATION_SEMANTICS_WITH_FRESH_PROCESS': raise RuntimeError('FAIL_CLOSED_RECOVERY_HANDOFF')
        if hand['process_separation']['fresh_process_outcome_evidence_read'] is not False or hand['process_separation']['fresh_process_candidate_outcome_evidence_read'] is not False: raise RuntimeError('FAIL_CLOSED_RECOVERY_LEAKAGE')
        if hand['current_gate']['sealed_target_outcome_unblind_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_RECOVERY_UNBLIND_OPEN')

        if contam['status']!='CONTAMINATED_DO_NOT_USE': raise RuntimeError('FAIL_CLOSED_CONTAMINATION_TOMBSTONE')
        for k in ('eligible_for_matching','eligible_for_calibration','eligible_for_validation','eligible_for_control_label','eligible_for_unblind_gate'):
            if contam['disposition'].get(k) is not False: raise RuntimeError(f'FAIL_CLOSED_CONTAMINATED_STAGE_ELIGIBLE {k}')

        if clean['status']!='CLEANROOM_RECOVERY_FROZEN_BY_EXACT_HASH' or clean['contaminated_adjudication_excluded'] is not True: raise RuntimeError('FAIL_CLOSED_CLEANROOM_FREEZE')
        auth=co['authoritative_postincident_matching']
        if clean['frozen_outputs']['cleanroom_matching']['sha256']!=auth['matching_sha256']: raise RuntimeError('FAIL_CLOSED_CLEANROOM_MATCH_HASH')
        clean_codes=set(auth['selected_candidate_codes'])
        expected_codes={code(cid) for cid in CONTROL_IDS}
        if clean_codes!=expected_codes or clean['frozen_outputs']['cleanroom_matching']['selected_candidate_count']!=7: raise RuntimeError('FAIL_CLOSED_CLEANROOM_TO_PRESERVED_CONTROL_ID_ALIGNMENT')
        pol=clean['territorial_unblind_policy']
        if pol['selection_feedback_allowed'] is not False or pol['candidate_replacement_after_outcome_review_allowed'] is not False or pol['target_outcomes_allowed'] is not False or pol['a6680_numeric_morphometry_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_CLEANROOM_UNBLIND_POLICY')

        if territorial['status']!='FROZEN_CANDIDATE_ONLY_TERRITORIAL_UNBLIND_CONTRACT': raise RuntimeError('FAIL_CLOSED_TERRITORIAL_CONTRACT')
        if territorial['cleanroom_matching_sha256']!=auth['matching_sha256'] or set(territorial['selected_candidate_codes'])!=clean_codes or territorial['selected_candidate_count']!=7: raise RuntimeError('FAIL_CLOSED_TERRITORIAL_MATCH_ALIGNMENT')
        if territorial['adjudication']['selection_feedback_allowed'] is not False or territorial['adjudication']['candidate_replacement_after_review'] is not False or territorial['adjudication']['matching_recalculation_after_review'] is not False or territorial['adjudication']['target_unblind_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_TERRITORIAL_FEEDBACK_POLICY')

        if sha(paths['candidate_only_review_packet'])!=territorial['review_packet_sha256']: raise RuntimeError('FAIL_CLOSED_REVIEW_PACKET_HASH')
        if packet['status']!='FROZEN_CANDIDATE_ONLY_TERRITORIAL_REVIEW_PACKET' or packet['cleanroom_matching_sha256']!=auth['matching_sha256']: raise RuntimeError('FAIL_CLOSED_REVIEW_PACKET_STATUS')
        packet_codes=[x['candidate_code'] for x in packet['candidates']]
        if packet_codes!=territorial['selected_candidate_codes'] or len(packet_codes)!=7 or len(set(packet_codes))!=7: raise RuntimeError('FAIL_CLOSED_REVIEW_PACKET_MEMBERSHIP')
        if any(x['adjudication'] is not None for x in packet['candidates']): raise RuntimeError('FAIL_CLOSED_REVIEW_PACKET_PREMATURE_ADJUDICATION')
        if packet['sealed_target_outcomes_allowed'] is not False or packet['selection_feedback_allowed'] is not False or packet['candidate_replacement_allowed'] is not False or packet['a6680_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_REVIEW_PACKET_POLICY')

        if ingest['status']!='FROZEN_CANDIDATE_ONLY_ADJUDICATION_INGEST_CONTRACT': raise RuntimeError('FAIL_CLOSED_ADJUDICATION_INGEST_CONTRACT')
        if ingest['prerequisites']['candidate_review_packet_sha256']!=territorial['review_packet_sha256'] or ingest['prerequisites']['cleanroom_matching_sha256']!=auth['matching_sha256']: raise RuntimeError('FAIL_CLOSED_ADJUDICATION_INGEST_HASH_LINK')
        if ingest['selected_candidate_codes']!=packet_codes: raise RuntimeError('FAIL_CLOSED_ADJUDICATION_INGEST_MEMBERSHIP')
        ria=ingest['review_attestation']
        if ria['candidate_replacement_allowed'] is not False or ria['matching_recalculation_allowed'] is not False or ria['selection_feedback_allowed'] is not False or ria['target_unblind_allowed'] is not False or ria['a6680_allowed'] is not False or ria['post_event_target_evidence_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_ADJUDICATION_INGEST_POLICY')

        if target_ready['status']!='FROZEN_TARGET_UNBLIND_READINESS_CONTRACT': raise RuntimeError('FAIL_CLOSED_TARGET_READINESS_CONTRACT')
        if target_ready['prerequisites']['cleanroom_matching_sha256']!=auth['matching_sha256']: raise RuntimeError('FAIL_CLOSED_TARGET_READINESS_MATCH_HASH')
        if target_ready['eligibility_rule']['automatic_target_outcome_unblind'] is not False or target_ready['eligibility_rule']['candidate_replacement_allowed'] is not False or target_ready['eligibility_rule']['matching_recalculation_allowed'] is not False or target_ready['eligibility_rule']['selection_feedback_allowed'] is not False: raise RuntimeError('FAIL_CLOSED_TARGET_READINESS_POLICY')
        if len(target_ready['frozen_target_shortlists'])!=6 or any(len(v)!=3 for v in target_ready['frozen_target_shortlists'].values()): raise RuntimeError('FAIL_CLOSED_TARGET_READINESS_SHORTLISTS')
        if set(c for v in target_ready['frozen_target_shortlists'].values() for c in v)!=clean_codes: raise RuntimeError('FAIL_CLOSED_TARGET_READINESS_CANDIDATE_SET')

        targets=val['targets']
        if len(targets)!=6 or any(t['outcome_label']!='SEALED' for t in targets): raise RuntimeError('FAIL_CLOSED_TARGET_OUTCOMES_NOT_SEALED')
        hashes={k:sha(p) for k,p in paths.items()}
        rep['checks']={'outlets_frozen':6,'geometries_frozen':6,'morphometry_frozen':True,'imerg_frozen':True,'imerg_coverage_fraction':1.0,
                       'negative_control_candidate_pool_frozen':True,'negative_control_candidate_count':29,
                       'preincident_control_geometry_and_predictors_preserved':True,'negative_control_shortlist_geometry_count':7,
                       'negative_control_imerg_frozen':True,'negative_control_imerg_count':7,'negative_control_imerg_coverage_fraction':1.0,
                       'contaminated_adjudication_tombstoned':True,'cleanroom_matching_frozen':True,'cleanroom_selected_candidate_count':7,
                       'cleanroom_matches_preserved_candidate_geometry_set':True,'candidate_only_review_packet_frozen':True,
                       'candidate_only_adjudication_ingest_contract_frozen':True,'target_unblind_readiness_contract_frozen':True,
                       'fresh_blind_recovery_active':True,'target_outcomes_sealed':True,'record_sha256':hashes}
        rep['status']='PASS_PREUNBLIND_CORE_FREEZES_CLEANROOM_RECOVERED_PENDING_CANDIDATE_ONLY_TERRITORIAL_ADJUDICATION'
        rep['next_gate']='INDEPENDENT_CANDIDATE_ONLY_TERRITORIAL_ADJUDICATION'
        rep['candidate_only_territorial_review_allowed']=True
        rep['sealed_target_outcome_unblind_allowed']=False
    except Exception as e:
        rep['status']='FAIL_CLOSED_PREUNBLIND_READINESS'; rep['error']=str(e); rep['candidate_only_territorial_review_allowed']=False; rep['sealed_target_outcome_unblind_allowed']=False
        a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 2
    a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
