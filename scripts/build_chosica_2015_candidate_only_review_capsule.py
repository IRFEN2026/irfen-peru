#!/usr/bin/env python3
"""Build a detached candidate-only territorial review capsule with no repository access required."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--contract',type=Path,required=True)
    ap.add_argument('--bundle',type=Path,required=True)
    ap.add_argument('--geometry',type=Path,required=True)
    ap.add_argument('--template',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'))
    guards={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}
    assert co['guards']==guards
    assert sha(a.bundle)==co['inputs']['reviewer_bundle_sha256']
    assert sha(a.geometry)==co['inputs']['reviewer_geometry_sha256']
    bundle=json.loads(a.bundle.read_text(encoding='utf-8'))
    template=json.loads(a.template.read_text(encoding='utf-8'))
    geometry=json.loads(a.geometry.read_text(encoding='utf-8'))
    assert bundle['guards']==template['guards']==guards
    assert bundle['candidate_count']==len(template['candidates'])==len(geometry['features'])==7
    bcodes=[x['candidate_code'] for x in bundle['candidates']]
    tcodes=[x['candidate_code'] for x in template['candidates']]
    gcodes=[x['properties']['candidate_code'] for x in geometry['features']]
    assert bcodes==tcodes
    assert sorted(bcodes)==sorted(gcodes)
    assert bundle['candidate_membership_sha256']==co['inputs']['candidate_membership_sha256']
    a.output_dir.mkdir(parents=True,exist_ok=True)
    mapping={
      'review_bundle.json':a.bundle,
      'candidate_geometry.geojson':a.geometry,
      'adjudication_template.json':a.template,
    }
    for name,src in mapping.items(): shutil.copyfile(src,a.output_dir/name)
    manifest={
      'schema_version':'0.1',
      'status':'PASS_CANDIDATE_ONLY_REVIEW_CAPSULE',
      'guards':guards,
      'candidate_count':7,
      'candidate_codes':bcodes,
      'candidate_membership_sha256':co['inputs']['candidate_membership_sha256'],
      'event_anchor_utc':bundle['frozen_event_anchor']['utc'],
      'files':{name:sha(a.output_dir/name) for name in mapping},
      'review_scope':co['review_scope'],
      'return_rule':co['return_rule'],
      'repository_access_required':False,
      'target_identifiers_included':False,
      'target_outcomes_included':False,
      'contaminated_stage_material_included':False,
      'external_reference_morphometry_included':False,
      'matching_feedback_included':False,
      'candidate_replacement_allowed':False,
      'matching_recalculation_allowed':False,
      'selection_feedback_allowed':False,
      'target_unblind_allowed':False
    }
    mp=a.output_dir/'capsule_manifest.json'
    mp.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    for p in a.output_dir.iterdir():
        text=p.read_text(encoding='utf-8').lower()
        for token in co['forbidden_tokens_case_insensitive']:
            assert token.lower() not in text, f'FAIL_CLOSED_FORBIDDEN_TOKEN:{token}:{p.name}'
    print(json.dumps({'status':manifest['status'],'candidate_count':7,'files':{p.name:sha(p) for p in sorted(a.output_dir.iterdir())}},sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
