#!/usr/bin/env python3
"""Build a target-blind external ground-truth request packet from frozen candidate geometry only."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from shapely.geometry import shape

def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--json-output',type=Path,required=True);ap.add_argument('--md-output',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());raw=a.geometry.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=co['candidate_geometry']['sha256']:raise SystemExit('FAIL_CLOSED_GEOMETRY_HASH')
 gj=json.loads(raw);feats=gj.get('features',[])
 if len(feats)!=co['candidate_geometry']['candidate_count']:raise SystemExit('FAIL_CLOSED_CANDIDATE_COUNT')
 rows=[]
 for f in sorted(feats,key=lambda z:str((z.get('properties') or {}).get('candidate_code',''))):
  code=(f.get('properties') or {}).get('candidate_code');g=shape(f['geometry']);c=g.centroid;rows.append({'candidate_code':code,'centroid_wgs84':{'lon':round(c.x,7),'lat':round(c.y,7)},'bbox_wgs84':[round(x,7) for x in g.bounds],'geometry':f['geometry'],'requested_disposition_values':co['response_schema']['evidence_disposition']})
 out={'schema_version':'0.1','batch_id':co['batch_id'],'status':'FROZEN_CANDIDATE_ONLY_EXTERNAL_GROUND_TRUTH_REQUEST_PACKET','guards':co['guards'],'contract_sha256':sha(a.contract),'candidate_geometry_sha256':hashlib.sha256(raw).hexdigest(),'event_scope':co['event_scope'],'eligible_evidence_holders':co['eligible_evidence_holders'],'requested_evidence_classes':co['requested_evidence_classes'],'response_schema':co['response_schema'],'acceptance_policy':co['acceptance_policy'],'candidate_count':len(rows),'candidates':rows,'target_names_or_ids_included':False,'target_outcomes_included':False,'a6680_included':False,'contaminated_adjudication_included':False,'candidate_selection_modified':False,'candidate_ranking_used_for_request':False,'external_message_sent':False,'sealed_target_unblind_allowed':False};a.json_output.parent.mkdir(parents=True,exist_ok=True);a.json_output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
 lines=['# Chosica 2015 — candidate-only ground-truth request packet','','**RESEARCH_ONLY / TEST_ONLY. This packet contains no target identities or target outcomes.**','',f"Event date: {co['event_scope']['event_date_local']}  ",f"Frozen anchor: {co['event_scope']['event_anchor_local']}  ",'','Requested response for each candidate: explicitly confirm activation, explicitly confirm nonactivation, or state unable to determine. Documentary silence or absence of a database hit is not evidence of nonactivation.','', '| Candidate | Centroid lon | Centroid lat | Bounding box WGS84 |','|---|---:|---:|---|']
 for r in rows:lines.append(f"| {r['candidate_code']} | {r['centroid_wgs84']['lon']} | {r['centroid_wgs84']['lat']} | {', '.join(map(str,r['bbox_wgs84']))} |")
 lines += ['','For any affirmative response, provide an official source identifier, explicit spatial/event scope, the structured or verbatim statement supporting the disposition, and an attachment SHA-256 when a file is supplied.','', 'This packet must not be used to change candidate membership, matching, ranking, or target shortlists.']
 a.md_output.write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps({'status':out['status'],'candidate_count':len(rows),'external_message_sent':False},sort_keys=True))
if __name__=='__main__':main()
