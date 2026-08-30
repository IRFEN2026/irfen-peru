#!/usr/bin/env python3
"""Project frozen SNAP R2 method gates into the scientific map manifest.

Fail-closed: a compiled graph and staged precise-orbit bytes are still not R2
execution. The map only advances to an execution-pending state; pre/post SAR
comparison, R3, R4 and activation inference remain false/prohibited.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def guard(d):
    assert d['deployment_status']=='RESEARCH_ONLY' and d['test_only'] is True
    assert d['production_use'] is False and d['production_ready'] is False and d['operational_alerting_enabled'] is False
    assert d['uses_operational_event_none_labels'] is False and d['territorial_activation_evidence_blinded'] is True
    assert d['serious_modeling_gate']=='CLOSED_MINIMUM_DATASET_NOT_REACHED'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', required=True)
    ap.add_argument('--operators', required=True)
    ap.add_argument('--orbit-operator', required=True)
    ap.add_argument('--graph-compile', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    m=json.loads(Path(args.map).read_text(encoding='utf-8'))
    o=json.loads(Path(args.operators).read_text(encoding='utf-8'))
    a=json.loads(Path(args.orbit_operator).read_text(encoding='utf-8'))
    g=json.loads(Path(args.graph_compile).read_text(encoding='utf-8'))
    for d in (m,o,a,g): guard(d)
    assert o['r2_operator_schema_gate']=='PASS' and o['all_required_operators_available'] is True
    assert a['status']=='PASS' and a['r2_exact_graph_compile_allowed'] is True
    assert g['status']=='PASS_GRAPH_COMPILED_AND_EXACT_ORBITS_STAGED_EXECUTION_NOT_RUN'
    assert g['orbit_staging_gate']=='PASS_EXACT_FROZEN_BYTES_STAGED_CONSUMPTION_NOT_YET_VERIFIED'
    assert g['graph_sha256'] and len(g['graph_sha256'])==64
    assert len(g['orbit_staging'])==2 and all(x['status']=='PASS_EXACT_AUX_POEORB_STAGED' for x in g['orbit_staging'])
    for d in (o,a,g):
        assert d['pre_post_sar_values_read'] is False and d['comparison_performed'] is False
        assert d['r2_processing_executed'] is False and d['r3_common_support_built'] is False and d['r4_difference_computed'] is False
        assert d['activation_inference_allowed'] is False

    cash=[c for c in m['cases'] if c.get('unit_id')=='cashahuacra']
    assert len(cash)==1
    c=cash[0]
    c['framework_stage']='A4_R1_COMPLETE_R2_EXACT_GRAPH_AND_FROZEN_ORBIT_STAGING_PASS_EXECUTION_PENDING'
    c['remote_sensing_status']='S1_A4_R1_COMPLETE_R2_GRAPH_FROZEN_ORBITS_STAGED_EXECUTION_PENDING_NO_PREPOST_DIFFERENCE'
    c['sentinel1_r2_status']='EXACT_GRAPH_SHA256_FROZEN_AND_EXACT_AUX_POEORB_BYTES_STAGED_SNAP_CONSUMPTION_AND_R2_EXECUTION_NOT_YET_VERIFIED'
    c['sentinel1_r2_operator_schema_path']='data/validation/cashahuacra_sentinel1_r2_operator_schema.json'
    c['sentinel1_r2_operator_schema_gate']='PASS_THERMAL_NOISE_CALIBRATION_TERRAIN_FLATTENING_TERRAIN_CORRECTION'
    c['sentinel1_r2_orbit_operator_schema_path']='data/validation/cashahuacra_sentinel1_r2_orbit_operator_schema.json'
    c['sentinel1_r2_orbit_operator_schema_gate']='PASS_APPLY_ORBIT_FILE_OPERATOR_AVAILABLE'
    c['sentinel1_r2_graph_path']='data/validation/cashahuacra_sentinel1_r2_graph.xml'
    c['sentinel1_r2_graph_compile_path']='data/validation/cashahuacra_sentinel1_r2_graph_compile.json'
    c['sentinel1_r2_graph_sha256']=g['graph_sha256']
    c['sentinel1_r2_exact_graph_status']='PASS_GRAPH_COMPILED_IDENTICAL_PRE_POST_CONTRACT_FROZEN'
    c['sentinel1_r2_orbit_staging_gate']=g['orbit_staging_gate']
    c['sentinel1_r2_orbit_consumption_verified']=False
    c['sentinel1_r2_execution_gate']='PASS_METHOD_FREEZE_EXECUTION_ALLOWED_BUT_NOT_YET_RUN_ORBIT_CONSUMPTION_MUST_BE_LOG_VERIFIED'
    c['sentinel1_r2_processing_executed']=False
    c['sentinel1_r3_common_support_built']=False
    c['sentinel1_r4_difference_computed']=False
    c['sentinel1_prepost_difference_computed']=False
    assert c['smap_status']=='MISSING_FOR_EVENT_WINDOW'
    assert c['blind_status']=='TERRITORIAL_EVIDENCE_SEALED'

    m['version']='irfen-independent-basin-validation-map-v2.3'
    m['generated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    acq=m.setdefault('acquisition_contract',{})
    acq['sentinel1_r2_operator_schema_report']='site/data/validation/cashahuacra_sentinel1_r2_operator_schema.json'
    acq['sentinel1_r2_orbit_operator_schema_report']='site/data/validation/cashahuacra_sentinel1_r2_orbit_operator_schema.json'
    acq['sentinel1_r2_graph_compile_report']='site/data/validation/cashahuacra_sentinel1_r2_graph_compile.json'
    acq['sentinel1_r2_graph']='site/data/validation/cashahuacra_sentinel1_r2_graph.xml'
    acq['sentinel1_r2_exact_graph_sha256']=g['graph_sha256']
    acq['sentinel1_r2_exact_graph_status']='PASS_GRAPH_COMPILED_AND_EXACT_ORBITS_STAGED_EXECUTION_NOT_RUN'
    acq['sentinel1_r2_next_gate']='EXECUTE_SAME_FROZEN_GRAPH_PRE_AND_POST_VERIFY_EXACT_POEORB_CONSUMPTION_THEN_BUILD_R3_COMMON_SUPPORT'

    Path(args.output).write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'version':m['version'],'framework_stage':c['framework_stage'],'graph_sha256':c['sentinel1_r2_graph_sha256'],'execution_gate':c['sentinel1_r2_execution_gate'],'prepost_difference':c['sentinel1_prepost_difference_computed']},indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
