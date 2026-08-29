#!/usr/bin/env python3
"""Freeze the official published checksum for the pre-registered SNAP runtime.

RESEARCH_ONLY / TEST_ONLY. Does not download the ~1 GB installer and performs no
Sentinel-1 processing or pre/post comparison. A published checksum alone does
not authorize R2 execution; installer bytes must later be verified against it.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
import requests

UA='IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY'
HEX64=re.compile(r'^[0-9a-fA-F]{64}$')

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',required=True,type=Path); ap.add_argument('--output',required=True,type=Path); a=ap.parse_args()
    c=json.loads(a.contract.read_text(encoding='utf-8'))
    assert c['production_use'] is False and c['production_ready'] is False and c['operational_alerting_enabled'] is False
    assert c['uses_operational_event_none_labels'] is False and c['territorial_activation_evidence_blinded'] is True
    u=c['official_release']['official_sha256sums_url']; fn=c['official_release']['installer_filename']
    try:
        r=requests.get(u,timeout=(20,60),headers={'User-Agent':UA}); r.raise_for_status(); raw=r.content
    except Exception as exc:
        report={'schema_version':'irfen-ibvf-snap-runtime-published-checksum-v0.1','generated_at':now(),'case_id':c['case_id'],'deployment_status':'RESEARCH_ONLY','test_only':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False,'uses_operational_event_none_labels':False,'territorial_activation_evidence_blinded':True,'serious_modeling_gate':'CLOSED_MINIMUM_DATASET_NOT_REACHED','status':'TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING','source_url':u,'error':repr(exc),'installer_byte_verified':False,'r2_execution_allowed':False,'comparison_performed':False,'activation_inference_allowed':False}
        a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':report['status']})); return 0
    source_sha=hashlib.sha256(raw).hexdigest(); text=raw.decode('utf-8',errors='strict')
    matches=[]
    for line in text.splitlines():
        parts=line.strip().replace('*',' ').split()
        if len(parts)>=2 and parts[-1].split('/')[-1]==fn and HEX64.match(parts[0]): matches.append(parts[0].lower())
    if len(matches)!=1: raise RuntimeError(f'expected unique published checksum for {fn}, got {matches}')
    report={'schema_version':'irfen-ibvf-snap-runtime-published-checksum-v0.1','generated_at':now(),'case_id':c['case_id'],'deployment_status':'RESEARCH_ONLY','test_only':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False,'uses_operational_event_none_labels':False,'territorial_activation_evidence_blinded':True,'serious_modeling_gate':'CLOSED_MINIMUM_DATASET_NOT_REACHED','status':'PUBLISHED_CHECKSUM_FROZEN_INSTALLER_BYTES_NOT_YET_VERIFIED','source_url':u,'source_bytes':len(raw),'source_sha256':source_sha,'installer_filename':fn,'installer_url':c['official_release']['linux_sentinel_toolboxes_installer_url'],'published_installer_sha256':matches[0],'unique_match_count':1,'installer_byte_verified':False,'r2_execution_allowed':False,'pre_post_sar_values_read':False,'comparison_performed':False,'activation_inference_allowed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); print(json.dumps({'status':report['status'],'published_installer_sha256':matches[0],'source_sha256':source_sha},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
