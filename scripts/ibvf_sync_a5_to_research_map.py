#!/usr/bin/env python3
"""Project frozen A5 status into the RESEARCH_ONLY map manifest.

No scientific values are recomputed. This is a pure status/provenance mirror.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path


def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def guard(d):
    assert d['deployment_status']=='RESEARCH_ONLY'
    assert d.get('test_only') is True
    assert d['production_use'] is False and d['production_ready'] is False
    assert d['operational_alerting_enabled'] is False
    assert d['uses_operational_event_none_labels'] is False
    assert d['territorial_activation_evidence_blinded'] is True
    assert d['serious_modeling_gate']=='CLOSED_MINIMUM_DATASET_NOT_REACHED'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--map',type=Path,default=Path('site/data/validation/independent_basin_validation_map.json')); ap.add_argument('--a5',type=Path,default=Path('site/data/validation/cashahuacra_a5_feature_vector.json')); args=ap.parse_args()
    m=load(args.map); a5=load(args.a5); guard(m); guard(a5)
    assert a5['case_id']=='cashahuacra_2015-03-23'
    assert a5['a5_status']=='PASS_A5_BLIND_FEATURE_VECTOR_HASHED_WITH_EXPLICIT_MISSING_NO_UNBLIND_NO_MODELING'
    assert a5['case_control_role_assigned'] is False and a5['activation_inference_allowed'] is False and a5['modeling_allowed'] is False
    cases=[c for c in m['cases'] if c.get('case_id')==a5['case_id']]; assert len(cases)==1; c=cases[0]
    assert c['blind_status']=='TERRITORIAL_EVIDENCE_SEALED'
    ac=m.setdefault('acquisition_contract',{})
    ac['a5_feature_vector_contract']='site/data/validation/ibvf_a5_feature_vector_contract.json'
    ac['cashahuacra_a5_feature_vector_report']='site/data/validation/cashahuacra_a5_feature_vector.json'
    ac['cashahuacra_a5_status']=a5['a5_status']
    ac['cashahuacra_a5_feature_vector_sha256']=a5['feature_vector_sha256']
    ac['cashahuacra_a5_numeric_feature_count']=a5['numeric_feature_count']
    ac['cashahuacra_a5_explicit_missing_or_unknown_feature_count']=a5['explicit_missing_or_unknown_feature_count']
    c['framework_stage']='A5_BLIND_FEATURE_VECTOR_FROZEN_NO_UNBLIND_SERIOUS_MODELING_BLOCKED'
    c['a5_status']=a5['a5_status']; c['a5_feature_vector_path']='data/validation/cashahuacra_a5_feature_vector.json'; c['a5_feature_vector_sha256']=a5['feature_vector_sha256']; c['a5_numeric_feature_count']=a5['numeric_feature_count']; c['a5_explicit_missing_or_unknown_feature_count']=a5['explicit_missing_or_unknown_feature_count']; c['case_control_role']='UNASSIGNED_BLIND'; c['activation_inference_allowed']=False; c['modeling_allowed']=False
    m['generated_at']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    guard(m); args.map.write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print({'case_id':c['case_id'],'framework_stage':c['framework_stage'],'a5_sha256':c['a5_feature_vector_sha256'],'serious_modeling_gate':m['serious_modeling_gate']})
if __name__=='__main__': main()
