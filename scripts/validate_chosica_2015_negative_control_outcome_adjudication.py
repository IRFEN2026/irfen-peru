#!/usr/bin/env python3
"""Validate blinded negative-control outcome adjudication without reading target outcomes."""
from __future__ import annotations
import argparse, json
from pathlib import Path

GUARDS={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}
IDS={'NC_001','NC_007','NC_017','NC_019','NC_023','NC_024','NC_027'}
DISP={'CONTROL_AFFIRMATIVE_NO_ACTIVATION','NOT_CONTROL_AFFIRMATIVE_ACTIVATION','OUTCOME_UNKNOWN'}
EVIDENCE_FIELDS={'source_id','institution_or_author','title_or_description','locator','publication_or_observation_date','evidence_type','temporal_coverage','spatial_linkage','affirmative_statement_class','source_sha256_or_archival_id_if_available'}
FORBIDDEN_KEYS={'target_id','target_name','target_outcome','target_activation','matching_rank','matching_score','target_predictor','a6680_outcome'}

def load(p): return json.loads(p.read_text(encoding='utf-8'))

def walk_keys(x):
    if isinstance(x,dict):
        for k,v in x.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(x,list):
        for v in x: yield from walk_keys(v)

def nonempty(v): return isinstance(v,str) and bool(v.strip())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,required=True); ap.add_argument('--input',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=load(a.contract); d=load(a.input)
    rep={'schema_version':'0.1','batch_id':co.get('batch_id'),'guards':GUARDS,'status':'PENDING','sealed_target_outcomes_read':False,'target_names_read_for_candidate_adjudication':False,'a6680_target_outcome_narrative_read':False,'checks':{}}
    try:
        if co.get('guards')!=GUARDS or d.get('guards')!=GUARDS: raise RuntimeError('FAIL_CLOSED_GUARD_MISMATCH')
        if co.get('status')!='FROZEN_BLIND_NEGATIVE_CONTROL_OUTCOME_ADJUDICATION_CONTRACT': raise RuntimeError('FAIL_CLOSED_CONTRACT_STATUS')
        if d.get('batch_id')!=co.get('batch_id'): raise RuntimeError('FAIL_CLOSED_BATCH_MISMATCH')
        rb=d.get('review_blinding') or {}
        if any(rb.get(k) is not False for k in ('sealed_target_outcomes_read','target_names_read_for_candidate_adjudication','target_matching_ranks_read_for_candidate_adjudication','target_predictor_values_read_for_candidate_adjudication','a6680_target_outcome_narrative_read')): raise RuntimeError('FAIL_CLOSED_REVIEWER_BLINDING')
        forbidden=sorted(FORBIDDEN_KEYS.intersection(set(walk_keys(d))))
        if forbidden: raise RuntimeError('FAIL_CLOSED_FORBIDDEN_REVIEW_FIELD '+','.join(forbidden))
        rows=d.get('candidates') or []
        if len(rows)!=7 or {r.get('candidate_id') for r in rows}!=IDS: raise RuntimeError('FAIL_CLOSED_CANDIDATE_SET')
        counts={x:0 for x in DISP}; evidence_total=0
        for r in rows:
            cid=r['candidate_id']; disp=r.get('disposition')
            if disp not in DISP: raise RuntimeError(f'FAIL_CLOSED_DISPOSITION {cid}')
            counts[disp]+=1
            sources=r.get('evidence_sources')
            if not isinstance(sources,list): raise RuntimeError(f'FAIL_CLOSED_EVIDENCE_LIST {cid}')
            if disp=='OUTCOME_UNKNOWN':
                if sources and not nonempty(r.get('reviewer_rationale')): raise RuntimeError(f'FAIL_CLOSED_UNKNOWN_RATIONALE {cid}')
            else:
                if not sources: raise RuntimeError(f'FAIL_CLOSED_AFFIRMATIVE_WITHOUT_EVIDENCE {cid}')
                if not nonempty(r.get('reviewer_rationale')): raise RuntimeError(f'FAIL_CLOSED_AFFIRMATIVE_WITHOUT_RATIONALE {cid}')
                for i,s in enumerate(sources):
                    if not isinstance(s,dict) or not EVIDENCE_FIELDS.issubset(s): raise RuntimeError(f'FAIL_CLOSED_EVIDENCE_FIELDS {cid} {i}')
                    required=[k for k in EVIDENCE_FIELDS if k!='source_sha256_or_archival_id_if_available']
                    if any(not nonempty(s.get(k)) for k in required): raise RuntimeError(f'FAIL_CLOSED_EMPTY_EVIDENCE_FIELD {cid} {i}')
                    if disp=='CONTROL_AFFIRMATIVE_NO_ACTIVATION' and s.get('affirmative_statement_class')!='AFFIRMATIVE_NO_ACTIVATION': raise RuntimeError(f'FAIL_CLOSED_CONTROL_NOT_AFFIRMATIVE {cid} {i}')
                    if disp=='NOT_CONTROL_AFFIRMATIVE_ACTIVATION' and s.get('affirmative_statement_class')!='AFFIRMATIVE_ACTIVATION': raise RuntimeError(f'FAIL_CLOSED_ACTIVATION_NOT_AFFIRMATIVE {cid} {i}')
                    evidence_total+=1
        expected_control=counts['CONTROL_AFFIRMATIVE_NO_ACTIVATION']; expected_act=counts['NOT_CONTROL_AFFIRMATIVE_ACTIVATION']; expected_unknown=counts['OUTCOME_UNKNOWN']
        summary=d.get('summary') or {}
        if summary.get('affirmative_control_count')!=expected_control or summary.get('affirmative_activation_count')!=expected_act or summary.get('unknown_count')!=expected_unknown: raise RuntimeError('FAIL_CLOSED_SUMMARY_COUNT_MISMATCH')
        gate=expected_control>=int(co['minimum_sufficiency_for_next_gate']['require_at_least_one_affirmative_control'])
        # Boolean True in JSON intentionally means minimum count 1; reject any inconsistent claimed gate.
        if summary.get('control_gate_satisfied') is not gate: raise RuntimeError('FAIL_CLOSED_CONTROL_GATE_CLAIM')
        if summary.get('sealed_target_unblind_allowed') is not False: raise RuntimeError('FAIL_CLOSED_TARGET_UNBLIND_CLAIM')
        rep['checks']={'candidate_count':7,'affirmative_control_count':expected_control,'affirmative_activation_count':expected_act,'unknown_count':expected_unknown,'affirmative_evidence_source_count':evidence_total,'control_gate_satisfied':gate,'target_outcomes_remain_sealed':True}
        rep['status']='PASS_BLIND_CONTROL_ADJUDICATION_READY_FOR_SEPARATE_UNBLIND_DECISION' if gate else 'PASS_BLIND_CONTROL_ADJUDICATION_PENDING_AFFIRMATIVE_CONTROL'
        rep['sealed_target_unblind_allowed_by_this_validator']=False
    except Exception as e:
        rep['status']='FAIL_CLOSED_BLIND_CONTROL_ADJUDICATION'; rep['error']=str(e); rep['sealed_target_unblind_allowed_by_this_validator']=False
        a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 2
    a.output.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(rep,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
