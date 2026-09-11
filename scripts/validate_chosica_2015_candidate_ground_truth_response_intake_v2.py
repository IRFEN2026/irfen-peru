#!/usr/bin/env python3
"""Strict sanitized-envelope intake. Never reads evidence attachments or target-aware sources."""
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path

def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--responses',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());raw=a.responses.read_bytes()
 try:d=json.loads(raw)
 except Exception:raise SystemExit('FAIL_CLOSED_NON_JSON')
 if not isinstance(d,dict) or set(d)!= {'responses'} or not isinstance(d['responses'],list):raise SystemExit('FAIL_CLOSED_TOP_LEVEL_SCHEMA')
 allowed_codes=set(co['allowed_candidate_codes']);fields=set(co['allowed_response_fields']);seen=set();rows=[]
 for i,r in enumerate(d['responses']):
  if not isinstance(r,dict) or not set(r).issubset(fields):raise SystemExit(f'FAIL_CLOSED_RESPONSE_FIELDS_{i}')
  code=r.get('candidate_code');inst=r.get('institution_id');disp=r.get('evidence_disposition')
  if code not in allowed_codes or re.fullmatch(co['patterns']['candidate_code'],str(code)) is None:raise SystemExit('FAIL_CLOSED_CANDIDATE')
  if code in seen:raise SystemExit('FAIL_CLOSED_DUPLICATE');seen.add(code)
  if inst not in co['allowed_institution_ids']:raise SystemExit('FAIL_CLOSED_INSTITUTION')
  if disp not in co['allowed_dispositions']:raise SystemExit('FAIL_CLOSED_DISPOSITION')
  aff=disp.startswith('AFFIRMATIVE_')
  if aff:
   for k in ('candidate_polygon_explicitly_covered','event_date_explicitly_covered','institution_attests_disposition'):
    if r.get(k) is not True:raise SystemExit('FAIL_CLOSED_AFFIRMATIVE_SCOPE_'+k)
   for k in ('source_reference','source_date','attachment_sha256'):
    if not isinstance(r.get(k),str) or re.fullmatch(co['patterns'][k],r[k]) is None:raise SystemExit('FAIL_CLOSED_AFFIRMATIVE_'+k)
  else:
   for k in ('source_reference','source_date','attachment_sha256'):
    if k in r and r[k] is not None and (not isinstance(r[k],str) or re.fullmatch(co['patterns'][k],r[k]) is None):raise SystemExit('FAIL_CLOSED_OPTIONAL_'+k)
  rows.append({'candidate_code':code,'institution_id':inst,'submitted_disposition':disp,'intake_state':co['output_states'][disp],'source_reference_sha256':hashlib.sha256(str(r.get('source_reference','')).encode()).hexdigest() if r.get('source_reference') else None,'source_date':r.get('source_date'),'attachment_sha256':r.get('attachment_sha256'),'candidate_polygon_explicitly_covered':r.get('candidate_polygon_explicitly_covered') is True,'event_date_explicitly_covered':r.get('event_date_explicitly_covered') is True,'institution_attests_disposition':r.get('institution_attests_disposition') is True,'source_verification_required':aff})
 rows.sort(key=lambda x:x['candidate_code']);pending=[x['candidate_code'] for x in rows if x['source_verification_required']];unknown=sorted((allowed_codes-seen)|{x['candidate_code'] for x in rows if x['intake_state']=='OUTCOME_UNKNOWN'})
 out={'schema_version':'0.2','batch_id':co['batch_id'],'status':'PASS_SANITIZED_CANDIDATE_GROUND_TRUTH_RESPONSE_INTAKE','guards':co['guards'],'contract_sha256':sha(a.contract),'response_file_sha256':hashlib.sha256(raw).hexdigest(),'submitted_response_count':len(rows),'responses':rows,'pending_independent_source_verification':pending,'control_confirmed':[],'excluded_active':[],'outcome_unknown':unknown,'attachment_bytes_read':False,'free_text_response_fields_read':False,'affirmative_claim_promoted_without_verification':False,'documentary_silence_used_as_nonactivation':False,'candidate_selection_modified':False,'candidate_ranking_modified':False,'matching_recalculated':False,'selection_feedback_performed':False,'target_names_or_ids_read':False,'target_outcomes_read':False,'a6680_read':False,'contaminated_adjudication_used':False,'free_web_search_used':False,'automatic_target_unblind_performed':False,'sealed_target_unblind_allowed':False};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({'status':out['status'],'submitted_response_count':len(rows),'pending_verification_count':len(pending),'control_confirmed':0},sort_keys=True))
if __name__=='__main__':main()
