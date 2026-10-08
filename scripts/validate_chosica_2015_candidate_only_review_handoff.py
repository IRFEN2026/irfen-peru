#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

FORBIDDEN = {
    'cashahuacra','quirio','pedregal','san antonio','san_antonio','la libertad','la_libertad',
    'carossio','carosio','rayos de sol','rayos_de_sol','corrales','official_outcome_evidence','a6680'
}
GUARDS={
    'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,
    'production_ready':False,'operational_alerting_enabled':False
}

def fail(msg: str) -> None:
    raise SystemExit('FAIL_CLOSED_REVIEW_HANDOFF:' + msg)

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--handoff',type=Path,required=True)
    ap.add_argument('--capsule-freeze',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    h=json.loads(a.handoff.read_text(encoding='utf-8'))
    f=json.loads(a.capsule_freeze.read_text(encoding='utf-8'))
    if h.get('guards') != GUARDS or f.get('guards') != GUARDS: fail('GUARD_MISMATCH')
    if h.get('status') != 'FROZEN_CANDIDATE_ONLY_INDEPENDENT_REVIEW_HANDOFF': fail('STATUS')
    d=h['detached_capsule']; ff=f['frozen_files']; pr=f['prerequisites']; prov=f['provenance']
    checks={
        'artifact_id': (d['artifact_id'], prov['artifact_id']),
        'artifact_zip_sha256': (d['artifact_zip_sha256'], prov['artifact_zip_sha256']),
        'reviewer_bundle_sha256': (d['reviewer_bundle_sha256'], pr['reviewer_bundle_sha256']),
        'candidate_geometry_sha256': (d['candidate_geometry_sha256'], ff['candidate_geometry.geojson']),
        'adjudication_template_sha256': (d['adjudication_template_sha256'], ff['adjudication_template.json']),
        'capsule_manifest_sha256': (d['capsule_manifest_sha256'], ff['capsule_manifest.json']),
        'candidate_membership_sha256': (d['candidate_membership_sha256'], pr['candidate_membership_sha256']),
    }
    bad=[k for k,(x,y) in checks.items() if x != y]
    if bad: fail('CAPSULE_LINKAGE_MISMATCH:' + ','.join(bad))
    codes=h.get('candidate_codes',[])
    if len(codes)!=7 or len(set(codes))!=7 or any(not c.startswith('C_') for c in codes): fail('CANDIDATE_MEMBERSHIP')
    req=h['external_review_request']
    if req.get('reviewer_repository_access_required') is not False: fail('REPO_ACCESS_REQUIRED')
    if not req.get('reviewer_must_use_detached_capsule_only'): fail('DETACHED_CAPSULE_NOT_REQUIRED')
    if not req.get('reviewer_must_not_browse_repository_targets'): fail('TARGET_BROWSE_NOT_FORBIDDEN')
    if req.get('reviewer_must_not_use_matching_feedback') is not True: fail('MATCHING_FEEDBACK_GUARD')
    if req.get('reviewer_must_not_replace_candidates') is not True: fail('REPLACEMENT_GUARD')
    ret=h['allowed_return']
    if ret.get('candidate_replacement_allowed') is not False or ret.get('matching_recalculation_allowed') is not False or ret.get('selection_feedback_allowed') is not False or ret.get('target_unblind_allowed') is not False:
        fail('RETURN_GUARDS')
    # The handoff file itself must not carry target identifiers or sealed-source tokens.
    text=a.handoff.read_text(encoding='utf-8').lower()
    hits=sorted(t for t in FORBIDDEN if t in text)
    if hits: fail('FORBIDDEN_TOKEN_IN_HANDOFF:' + ','.join(hits))
    out={
        'schema_version':'0.1',
        'status':'PASS_CANDIDATE_ONLY_INDEPENDENT_REVIEW_HANDOFF',
        'guards':GUARDS,
        'candidate_count':7,
        'detached_capsule_only':True,
        'target_identifiers_present':False,
        'target_unblind_allowed':False,
        'scientific_use_allowed':False,
        'next_gate':'WAIT_FOR_INDEPENDENT_V0_2_ADJUDICATION_RETURN'
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps(out,sort_keys=True))
    return 0

if __name__=='__main__':
    sys.exit(main())
