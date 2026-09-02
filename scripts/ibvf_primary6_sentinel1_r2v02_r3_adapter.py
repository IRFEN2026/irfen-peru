#!/usr/bin/env python3
"""Create an explicit compatibility view from accepted R2 v0.2 to frozen generic R3.

This is a metadata-only adapter. It does not read rasters or alter any R2 output
identity. The generic R3 implementation predates the POEORB v0.2 amendment and
checks the original generic PASS status string. This adapter verifies the
stronger v0.2 invariants and emits that legacy interface status while retaining
full v0.2 provenance. RESEARCH_ONLY / TEST_ONLY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--r2-v02',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    d=json.loads(args.r2_v02.read_text(encoding='utf-8'))
    assert d['schema_version']=='irfen-ibvf-primary6-sentinel1-r2-execution-v0.2'
    assert d['deployment_status']=='RESEARCH_ONLY' and d['test_only'] is True
    assert d['production_use'] is False and d['production_ready'] is False
    assert d['operational_alerting_enabled'] is False and d['uses_operational_event_none_labels'] is False
    assert d['territorial_activation_evidence_blinded'] is True
    assert d['status']=='PASS_R2_V02_PRE_POST_INDEPENDENT_SNAP14_CANONICAL_POEORB_VERIFIED_NO_COMPARISON'
    assert d['poeorb_selector_version']=='SNAP14_POEORB_V02'
    assert d['r2_processing_executed'] is True and d['poeorb_consumption_verified_both_dates'] is True
    assert d['pre']['requested_exact_v02_frozen_resource'] is True
    assert d['post']['requested_exact_v02_frozen_resource'] is True
    assert d['pre']['frozen_resource_bytes_independently_verified'] is True
    assert d['post']['frozen_resource_bytes_independently_verified'] is True
    assert d['paired_pixel_values_extracted_for_comparison'] is False
    assert d['comparison_performed'] is False and d['r3_common_support_built'] is False
    assert d['r4_difference_computed'] is False and d['territorial_outcomes_read'] is False
    assert d['known_event_dates_read'] is False and d['case_control_role_assigned'] is False
    assert d['activation_inference_allowed'] is False and d['modeling_allowed'] is False
    out=dict(d)
    out['schema_version']='irfen-ibvf-primary6-sentinel1-r2v02-r3-interface-v0.1'
    out['source_r2_v02_path']=str(args.r2_v02)
    out['source_r2_v02_sha256']=sha(args.r2_v02)
    out['source_r2_v02_status']=d['status']
    out['status']='PASS_R2_PRE_POST_INDEPENDENT_PROCESSING_POEORB_VERIFIED_NO_COMPARISON'
    out['adapter_changes_raster_identity']=False
    out['adapter_reads_raster_pixels']=False
    out['adapter_changes_scientific_rules']=False
    out['adapter_changes_orbit_identity']=False
    out['adapter_changes_only_interface_status_and_adds_provenance']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'source_r2_v02_sha256':out['source_r2_v02_sha256'],'pixels_read':False},indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
