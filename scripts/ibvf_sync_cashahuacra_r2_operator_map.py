#!/usr/bin/env python3
"""Project frozen SNAP R2 operator gates into the scientific map manifest.

Fail-closed: operator availability is not equivalent to R2 execution. The map must
not say execution is ready until the exact graph and frozen local orbit staging
contract have been compiled and verified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', required=True)
    ap.add_argument('--operators', required=True)
    ap.add_argument('--orbit-operator', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    m=json.loads(Path(args.map).read_text(encoding='utf-8'))
    o=json.loads(Path(args.operators).read_text(encoding='utf-8'))
    a=json.loads(Path(args.orbit_operator).read_text(encoding='utf-8'))
    for d in (m,o,a):
        assert d['deployment_status']=='RESEARCH_ONLY' and d['test_only'] is True
        assert d['production_use'] is False and d['production_ready'] is False and d['operational_alerting_enabled'] is False
        assert d['uses_operational_event_none_labels'] is False and d['territorial_activation_evidence_blinded'] is True
        assert d['serious_modeling_gate']=='CLOSED_MINIMUM_DATASET_NOT_REACHED'
    assert o['r2_operator_schema_gate']=='PASS'
    assert o['all_required_operators_available'] is True
    assert a['status']=='PASS'
    assert a['r2_exact_graph_compile_allowed'] is True
    assert o['r2_processing_executed'] is False and a['r2_processing_executed'] is False
    assert o['comparison_performed'] is False and a['comparison_performed'] is False

    cash=[c for c in m['cases'] if c.get('unit_id')=='cashahuacra']
    assert len(cash)==1
    c=cash[0]
    c['framework_stage']='A4_R1_COMPLETE_R2_RUNTIME_AND_OPERATOR_SCHEMAS_PASS_EXACT_GRAPH_COMPILE_PENDING'
    c['remote_sensing_status']='S1_A4_R1_COMPLETE_R2_RUNTIME_AND_OPERATOR_SCHEMAS_PASS_EXACT_GRAPH_AND_FROZEN_ORBIT_STAGING_PENDING_NO_PREPOST_DIFFERENCE'
    c['sentinel1_r2_operator_schema_path']='data/validation/cashahuacra_sentinel1_r2_operator_schema.json'
    c['sentinel1_r2_operator_schema_gate']='PASS_THERMAL_NOISE_CALIBRATION_TERRAIN_FLATTENING_TERRAIN_CORRECTION'
    c['sentinel1_r2_orbit_operator_schema_path']='data/validation/cashahuacra_sentinel1_r2_orbit_operator_schema.json'
    c['sentinel1_r2_orbit_operator_schema_gate']='PASS_APPLY_ORBIT_FILE_OPERATOR_AVAILABLE'
    c['sentinel1_r2_exact_graph_status']='PENDING_COMPILE_AND_FROZEN_LOCAL_AUX_POEORB_STAGING_VERIFICATION'
    c['sentinel1_r2_execution_gate']='BLOCKED_METHOD_FINALIZATION_NOT_MISSING_EXACT_GRAPH_AND_LOCAL_FROZEN_ORBIT_STAGING_PENDING'
    c['sentinel1_prepost_difference_computed']=False
    assert c['smap_status']=='MISSING_FOR_EVENT_WINDOW'
    assert c['blind_status']=='TERRITORIAL_EVIDENCE_SEALED'

    m['version']='irfen-independent-basin-validation-map-v2.2'
    m['generated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    acq=m.setdefault('acquisition_contract',{})
    acq['sentinel1_r2_operator_schema_report']='site/data/validation/cashahuacra_sentinel1_r2_operator_schema.json'
    acq['sentinel1_r2_orbit_operator_schema_report']='site/data/validation/cashahuacra_sentinel1_r2_orbit_operator_schema.json'
    acq['sentinel1_r2_exact_graph_status']='PENDING_COMPILE_AND_FROZEN_LOCAL_AUX_POEORB_STAGING_VERIFICATION'

    Path(args.output).write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'version':m['version'],'framework_stage':c['framework_stage'],'execution_gate':c['sentinel1_r2_execution_gate'],'prepost_difference':c['sentinel1_prepost_difference_computed']},indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
