#!/usr/bin/env python3
"""Fail-closed candidate-only adjudication from frozen non-contaminated evidence records.
No target outcomes, A6680, free web, or contaminated adjudication are accessible by design.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p:Path): return json.loads(p.read_text(encoding='utf-8'))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--root',type=Path,default=Path('.'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    co=load(a.contract)
    if co['guards']!=GUARDS: raise SystemExit('FAIL_CLOSED_GUARDS')
    mp=a.root/co['candidate_membership']['matching_path'];m=load(mp)
    if sha(mp)!=co['candidate_membership']['matching_sha256'] or m.get('status')!='PASS_CLEANROOM_MATCHING': raise SystemExit('FAIL_CLOSED_MATCHING_HASH_OR_STATUS')
    if m.get('outcomes_used_for_matching') is not False or m.get('target_names_read') is not False or m.get('free_web_search_used') is not False: raise SystemExit('FAIL_CLOSED_MATCHING_GUARDS')
    codes=sorted(m.get('selected_candidate_codes',[]))
    if len(codes)!=co['candidate_membership']['candidate_count'] or len(set(codes))!=len(codes): raise SystemExit('FAIL_CLOSED_MEMBERSHIP')
    source_audit=[]
    for spec in co['allowed_frozen_evidence_records']:
        p=a.root/spec['path'];d=load(p)
        if d.get('status')!=spec['required_status'] or d.get('guards')!=GUARDS: raise SystemExit('FAIL_CLOSED_SOURCE_STATUS_'+p.name)
        raw=p.read_text(encoding='utf-8').lower()
        if 'control_confirmed": true' in raw or 'excluded_active": true' in raw: raise SystemExit('FAIL_CLOSED_UNPREREGISTERED_AFFIRMATIVE_LABEL_'+p.name)
        source_audit.append({'path':spec['path'],'sha256':sha(p),'status':d['status'],'label_capability':spec['label_capability']})
    rows=[{'candidate_code':c,'label':'OUTCOME_UNKNOWN','basis':'NO_AFFIRMATIVE_LABEL_CAPABLE_CANDIDATE_LOCAL_EVIDENCE_IN_FROZEN_ALLOWED_SOURCES'} for c in codes]
    out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_CANDIDATE_ONLY_ADJUDICATION_ALL_UNKNOWN','guards':GUARDS,'contract_sha256':sha(a.contract),'matching_sha256':sha(mp),'candidate_count':len(rows),'candidates':rows,'confirmed_controls':[],'excluded_active':[],'outcome_unknown':codes,'source_audit':source_audit,'candidate_selection_modified':False,'candidate_ranking_modified':False,'matching_recalculated':False,'selection_feedback_performed':False,'target_names_or_ids_read':False,'target_outcomes_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'free_web_search_used':False,'sealed_target_unblind_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'candidate_count':len(rows),'confirmed_controls':0,'excluded_active':0,'outcome_unknown':len(rows)},sort_keys=True))
if __name__=='__main__': main()
