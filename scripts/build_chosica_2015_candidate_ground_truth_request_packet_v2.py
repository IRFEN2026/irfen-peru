#!/usr/bin/env python3
"""Build sanitized target-blind ground-truth request packet with no free-text response fields."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from shapely.geometry import shape

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--json-output',type=Path,required=True);ap.add_argument('--md-output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());raw=a.geometry.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=co['candidate_geometry']['sha256']:raise SystemExit('FAIL_CLOSED_GEOMETRY_HASH')
 gj=json.loads(raw);feats=gj.get('features',[])
 if len(feats)!=co['candidate_geometry']['candidate_count']:raise SystemExit('FAIL_CLOSED_CANDIDATE_COUNT')
 rows=[]
 for f in sorted(feats,key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
  code=(f.get('properties') or {}).get('candidate_code');g=shape(f['geometry']);c=g.centroid;rows.append({'candidate_code':code,'centroid_wgs84':{'lon':round(c.x,7),'lat':round(c.y,7)},'bbox_wgs84':[round(x,7) for x in g.bounds],'geometry':f['geometry']})
 out={'schema_version':'0.2','batch_id':co['batch_id'],'status':'FROZEN_CANDIDATE_ONLY_EXTERNAL_GROUND_TRUTH_REQUEST_SANITIZED_ENVELOPE','guards':co['guards'],'contract_sha256':sha(a.contract),'candidate_geometry_sha256':hashlib.sha256(raw).hexdigest(),'event_scope':co['event_scope'],'eligible_institution_ids':co['eligible_institution_ids'],'requested_evidence_classes':co['requested_evidence_classes'],'response_envelope':co['response_envelope'],'attachment_policy':co['attachment_policy'],'acceptance_policy':co['acceptance_policy'],'candidate_count':len(rows),'candidates':rows,'target_names_or_ids_included':False,'target_outcomes_included':False,'a6680_included':False,'contaminated_adjudication_included':False,'free_text_response_fields_requested':False,'candidate_selection_modified':False,'candidate_ranking_used_for_request':False,'external_message_sent':False,'sealed_target_unblind_allowed':False};a.json_output.parent.mkdir(parents=True,exist_ok=True);a.json_output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
 lines=['# Chosica 2015 — candidate-only ground-truth request v0.2','','**RESEARCH_ONLY / TEST_ONLY. No target identities or target outcomes are included.**','',f"Event date: {co['event_scope']['event_date_local']}  ",f"Frozen anchor: {co['event_scope']['event_anchor_local']}  ",'','For each candidate, return only the structured response envelope defined in the JSON packet. Do not include narrative place names, sector names, basin names, damage descriptions, or other free text in the envelope. Any source attachment is supplied separately and referenced only by SHA-256.','', '| Candidate | Centroid lon | Centroid lat | Bounding box WGS84 |','|---|---:|---:|---|']
 for r in rows: lines.append(f"| {r['candidate_code']} | {r['centroid_wgs84']['lon']} | {r['centroid_wgs84']['lat']} | {', '.join(map(str,r['bbox_wgs84']))} |")
 lines += ['','Affirmative records require an opaque source reference, source date, explicit booleans confirming candidate-polygon and event-date coverage, an institutional attestation boolean, and a separately supplied attachment SHA-256.','', 'UNABLE_TO_DETERMINE remains outcome unknown. No response or documentary silence is never interpreted as nonactivation.','', 'This packet does not authorize candidate replacement, rematching, target unblind, production use, or operational alerting.']
 a.md_output.write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps({'status':out['status'],'candidate_count':len(rows),'free_text_response_fields_requested':False,'external_message_sent':False},sort_keys=True))
if __name__=='__main__':main()
