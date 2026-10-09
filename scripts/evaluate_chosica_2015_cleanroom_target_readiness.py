#!/usr/bin/env python3
"""Evaluate pseudonymous target readiness without reading target names or outcomes."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--matching',type=Path,required=True);ap.add_argument('--adjudication',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());m=json.loads(a.matching.read_text());ad=json.loads(a.adjudication.read_text())
 if sha(a.matching)!=co['inputs']['matching']['sha256'] or m.get('status')!=co['inputs']['matching']['required_status']: raise SystemExit('FAIL_CLOSED_MATCHING')
 if sha(a.adjudication)!=co['inputs']['candidate_adjudication']['sha256'] or ad.get('status')!=co['inputs']['candidate_adjudication']['required_status']: raise SystemExit('FAIL_CLOSED_ADJUDICATION')
 if m.get('target_names_read') is not False or m.get('outcomes_used_for_matching') is not False: raise SystemExit('FAIL_CLOSED_MATCHING_GUARDS')
 for k in ('target_names_or_ids_read','target_outcomes_read','a6680_read','contaminated_adjudication_used','selection_feedback_performed'):
  if ad.get(k) is not False: raise SystemExit('FAIL_CLOSED_ADJUDICATION_GUARD_'+k)
 controls=set(ad.get('confirmed_controls',[]));rows=[]
 for t,short in sorted(m['shortlists'].items()):
  codes=[x['candidate_code'] for x in short];hits=sorted(controls.intersection(codes));eligible=len(hits)>=int(co['eligibility_rule']['minimum_confirmed_controls_within_each_frozen_shortlist']);rows.append({'target_code':t,'frozen_shortlist':codes,'confirmed_controls_in_shortlist':hits,'target_unblind_allowed':eligible,'status':'ELIGIBLE_FOR_SEPARATE_EXPLICIT_UNBLIND_RECORD' if eligible else 'BLOCKED_NO_AFFIRMATIVE_CONFIRMED_CONTROL_IN_FROZEN_SHORTLIST'})
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'PASS_CLEANROOM_TARGET_READINESS_EVALUATION','guards':co['guards'],'contract_sha256':sha(a.contract),'matching_sha256':sha(a.matching),'candidate_adjudication_sha256':sha(a.adjudication),'target_count':len(rows),'eligible_target_count':sum(x['target_unblind_allowed'] for x in rows),'targets':rows,'target_names_read':False,'target_outcomes_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'matching_recalculated':False,'candidate_replacement_performed':False,'selection_feedback_performed':False,'automatic_target_outcome_unblind_performed':False,'sealed_target_unblind_allowed':any(x['target_unblind_allowed'] for x in rows)};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'target_count':len(rows),'eligible_target_count':out['eligible_target_count']},sort_keys=True))
if __name__=='__main__': main()
