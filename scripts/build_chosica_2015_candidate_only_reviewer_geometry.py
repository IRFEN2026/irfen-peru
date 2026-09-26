#!/usr/bin/env python3
"""Build an anonymized exact-geometry reviewer artifact from the frozen preincident shortlist."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def bbox(coords):
    pts=[]
    def walk(x):
        if isinstance(x,list) and len(x)>=2 and all(isinstance(v,(int,float)) for v in x[:2]):
            pts.append((float(x[0]),float(x[1])))
        elif isinstance(x,list):
            for y in x: walk(y)
    walk(coords)
    xs=[x for x,_ in pts]; ys=[y for _,y in pts]
    return [round(min(xs),8),round(min(ys),8),round(max(xs),8),round(max(ys),8)]


def vertex_count(coords):
    n=0
    def walk(x):
        nonlocal n
        if isinstance(x,list) and len(x)>=2 and all(isinstance(v,(int,float)) for v in x[:2]): n+=1
        elif isinstance(x,list):
            for y in x: walk(y)
    walk(coords)
    return n


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--contract',type=Path,required=True)
    ap.add_argument('--fingerprints',type=Path,required=True)
    ap.add_argument('--bundle',type=Path,required=True)
    ap.add_argument('--source-geojson',type=Path,required=True)
    ap.add_argument('--output-geojson',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,required=True)
    a=ap.parse_args()
    co=json.loads(a.contract.read_text(encoding='utf-8'))
    fp=json.loads(a.fingerprints.read_text(encoding='utf-8'))
    bundle=json.loads(a.bundle.read_text(encoding='utf-8'))
    guards={'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False}
    assert co['guards']==fp['guards']==bundle['guards']==guards
    assert sha_file(a.source_geojson)==co['source_artifact']['source_geojson_sha256']
    assert sha_file(a.bundle)==co['reviewer_bundle_sha256']
    assert fp['candidate_count']==bundle['candidate_count']==7
    frozen={x['candidate_code']:x for x in fp['candidates']}
    expected_codes=sorted(frozen)
    assert expected_codes==sorted(x['candidate_code'] for x in bundle['candidates'])
    src=json.loads(a.source_geojson.read_text(encoding='utf-8'))
    out_features=[]
    for feature in src['features']:
        cid=feature['properties']['candidate_id']
        code='C_'+hashlib.sha256(cid.encode('utf-8')).hexdigest()[:12]
        assert code in frozen
        geom=feature['geometry']
        gh=sha_bytes(json.dumps(geom,sort_keys=True,separators=(',',':')).encode('utf-8'))
        assert gh==frozen[code]['geometry_sha256']
        assert bbox(geom['coordinates'])==frozen[code]['bbox_wgs84']
        assert vertex_count(geom['coordinates'])==frozen[code]['vertex_count']
        out_features.append({
            'type':'Feature',
            'properties':{
                'candidate_code':code,
                'geometry_sha256':gh,
                **guards
            },
            'geometry':geom
        })
    out_features.sort(key=lambda f:f['properties']['candidate_code'])
    assert [f['properties']['candidate_code'] for f in out_features]==expected_codes
    out={'type':'FeatureCollection','features':out_features}
    raw=(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    low=raw.decode('utf-8').lower()
    for tok in co['forbidden_output_tokens_case_insensitive']:
        assert tok.lower() not in low, f'FAIL_CLOSED_FORBIDDEN_TOKEN:{tok}'
    a.output_geojson.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    a.output_geojson.write_bytes(raw)
    manifest={
        'schema_version':'0.1',
        'status':'PASS_CANDIDATE_ONLY_REVIEWER_GEOMETRY_BUILD',
        'guards':guards,
        'candidate_count':7,
        'candidate_codes':expected_codes,
        'candidate_membership_sha256':co['candidate_membership_sha256'],
        'source_geojson_sha256':sha_file(a.source_geojson),
        'reviewer_bundle_sha256':sha_file(a.bundle),
        'output_geojson_sha256':sha_file(a.output_geojson),
        'target_identifiers_included':False,
        'target_outcomes_accessed':False,
        'candidate_outcomes_accessed':False,
        'a6680_accessed':False,
        'post_anchor_predictors_accessed':False,
        'selection_feedback_used':False,
        'candidate_replacement_performed':False,
        'target_unblind_allowed':False
    }
    a.manifest.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps(manifest,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
