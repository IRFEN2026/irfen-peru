#!/usr/bin/env python3
"""Validate separately ingested candidate-only ground-truth responses.

An affirmative claim is never promoted directly to an outcome label. It is placed in a
pending-independent-source-verification state. Documentary silence remains OUTCOME_UNKNOWN.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

FORBIDDEN_KEYS = {
    'target_name','target_names','target_id','target_ids','target_code','target_codes',
    'target_outcome','target_outcomes','a6680','official_outcome_evidence',
    'contaminated_adjudication','matching_score','matching_rank','replacement_candidate'
}
FORBIDDEN_TEXT = ('a6680','official_outcome_evidence','contaminated_do_not_use','contaminated adjudication')

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def nonempty(v) -> bool:
    return isinstance(v,str) and bool(v.strip())

def walk_keys(x):
    if isinstance(x,dict):
        for k,v in x.items():
            yield str(k).lower()
            yield from walk_keys(v)
    elif isinstance(x,list):
        for v in x: yield from walk_keys(v)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--request',type=Path,required=True);ap.add_argument('--responses',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'));req=json.loads(a.request.read_text(encoding='utf-8'));raw=a.responses.read_bytes()
    if sha(a.request)!=co['request_packet']['sha256']: raise SystemExit('FAIL_CLOSED_REQUEST_HASH')
    if req.get('status')!='FROZEN_CANDIDATE_ONLY_EXTERNAL_GROUND_TRUTH_REQUEST_PACKET': raise SystemExit('FAIL_CLOSED_REQUEST_STATUS')
    if any(req.get(k) is not False for k in ('target_names_or_ids_included','target_outcomes_included','a6680_included','contaminated_adjudication_included','candidate_selection_modified','candidate_ranking_used_for_request','external_message_sent','sealed_target_unblind_allowed')): raise SystemExit('FAIL_CLOSED_REQUEST_GUARDS')
    try: inp=json.loads(raw)
    except Exception: raise SystemExit('FAIL_CLOSED_RESPONSE_NON_JSON')
    if not isinstance(inp,dict) or not isinstance(inp.get('responses'),list): raise SystemExit('FAIL_CLOSED_RESPONSE_SCHEMA')
    if any(k in FORBIDDEN_KEYS for k in walk_keys(inp)): raise SystemExit('FAIL_CLOSED_FORBIDDEN_KEY')
    low=raw.decode('utf-8','replace').lower()
    if any(x in low for x in FORBIDDEN_TEXT): raise SystemExit('FAIL_CLOSED_FORBIDDEN_TEXT')
    allowed=set(co['request_packet']['candidate_codes']); seen=set(); rows=[]
    for i,r in enumerate(inp['responses']):
        if not isinstance(r,dict): raise SystemExit(f'FAIL_CLOSED_RESPONSE_ROW_{i}')
        code=r.get('candidate_code'); disp=r.get('evidence_disposition')
        if code not in allowed: raise SystemExit('FAIL_CLOSED_UNKNOWN_CANDIDATE')
        if code in seen: raise SystemExit('FAIL_CLOSED_DUPLICATE_CANDIDATE_RESPONSE')
        seen.add(code)
        if disp not in co['allowed_dispositions']: raise SystemExit('FAIL_CLOSED_DISPOSITION')
        if disp.startswith('AFFIRMATIVE_'):
            for f in co['affirmative_requirements']['required_nonempty_fields']:
                if not nonempty(r.get(f)): raise SystemExit('FAIL_CLOSED_AFFIRMATIVE_REQUIRED_'+f)
            prov=[f for f in co['affirmative_requirements']['require_at_least_one_provenance_field'] if nonempty(r.get(f))]
            if not prov: raise SystemExit('FAIL_CLOSED_AFFIRMATIVE_NO_PROVENANCE')
            h=r.get('attachment_sha256')
            if h is not None and not re.fullmatch(co['affirmative_requirements']['attachment_sha256_pattern'],str(h)): raise SystemExit('FAIL_CLOSED_ATTACHMENT_SHA256')
        state=co['output_states'][disp]
        rows.append({'candidate_code':code,'submitted_disposition':disp,'intake_state':state,'source_verification_required':disp.startswith('AFFIRMATIVE_'),'institution':r.get('institution'),'source_reference':r.get('source_reference'),'source_date':r.get('source_date'),'spatial_scope_statement':r.get('spatial_scope_statement'),'event_scope_statement':r.get('event_scope_statement'),'verbatim_or_structured_statement':r.get('verbatim_or_structured_statement'),'attachment_sha256':r.get('attachment_sha256'),'provenance_url_or_archive_locator':r.get('provenance_url_or_archive_locator')})
    rows.sort(key=lambda x:x['candidate_code'])
    pending=[x['candidate_code'] for x in rows if x['source_verification_required']]
    unknown=sorted((allowed-seen)|{x['candidate_code'] for x in rows if x['intake_state']=='OUTCOME_UNKNOWN'})
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_CANDIDATE_ONLY_GROUND_TRUTH_RESPONSE_INTAKE','guards':co['guards'],'contract_sha256':sha(a.contract),'request_sha256':sha(a.request),'response_file_sha256':hashlib.sha256(raw).hexdigest(),'submitted_response_count':len(rows),'responses':rows,'pending_independent_source_verification':pending,'control_confirmed':[],'excluded_active':[],'outcome_unknown':unknown,'affirmative_claim_promoted_without_verification':False,'documentary_silence_used_as_nonactivation':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'matching_recalculated':False,'selection_feedback_performed':False,'target_names_or_ids_read':False,'target_outcomes_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'free_web_search_used':False,'automatic_target_unblind_performed':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'submitted_response_count':len(rows),'pending_verification_count':len(pending),'confirmed_controls':0,'excluded_active':0},sort_keys=True))
if __name__=='__main__': main()
