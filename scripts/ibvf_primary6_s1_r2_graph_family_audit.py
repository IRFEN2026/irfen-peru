#!/usr/bin/env python3
"""Fail-closed audit that PRIMARY6 UTM17S R2 graph differs only by CRS/id.

RESEARCH_ONLY / TEST_ONLY. No science pixels or outcomes are read.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def projection(root: ET.Element) -> str:
    vals=[(x.text or '').strip() for x in root.iter() if x.tag.rsplit('}',1)[-1]=='mapProjection']
    if len(vals)!=1: raise ValueError(f'expected one mapProjection, got {vals}')
    return vals[0]


def normalized(root: ET.Element) -> bytes:
    root.attrib['id']='IBVF_R2_GRAPH_NORMALIZED'
    for x in root.iter():
        if x.tag.rsplit('}',1)[-1]=='mapProjection':
            x.text='EPSG:NORMALIZED'
    return ET.tostring(root,encoding='utf-8')


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--zone18',type=Path,required=True)
    ap.add_argument('--zone17',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    r18=ET.parse(a.zone18).getroot(); r17=ET.parse(a.zone17).getroot()
    p18=projection(r18); p17=projection(r17)
    n18=normalized(r18); n17=normalized(r17)
    same=n18==n17
    report={
      'schema_version':'irfen-ibvf-primary6-s1-r2-graph-family-audit-v0.1',
      'generated_at':now(),
      'framework':'IRFEN Independent Basin Validation Framework',
      'deployment_status':'RESEARCH_ONLY','test_only':True,
      'production_use':False,'production_ready':False,'operational_alerting_enabled':False,
      'uses_operational_event_none_labels':False,'territorial_activation_evidence_blinded':True,
      'zone18_graph_sha256':sha(a.zone18),'zone17_graph_sha256':sha(a.zone17),
      'zone18_projection':p18,'zone17_projection':p17,
      'normalized_graphs_identical':same,
      'allowed_difference':'GRAPH_ID_AND_MAP_PROJECTION_ONLY',
      'science_pixels_read':False,'rainfall_read':False,'territorial_outcomes_read':False,
      'case_control_assignment_performed':False,'activation_inference_allowed':False,'modeling_allowed':False,
      'status':'PASS_ONLY_ID_AND_CRS_DIFFER' if same and p18=='EPSG:32718' and p17=='EPSG:32717' else 'FAIL_GRAPH_FAMILY_DIFFERENCE'
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    if report['status']!='PASS_ONLY_ID_AND_CRS_DIFFER': raise SystemExit(2)
    return 0
if __name__=='__main__': raise SystemExit(main())
