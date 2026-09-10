#!/usr/bin/env python3
"""Recover exact preincident candidate basin polygons under clean-room pseudonyms only."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--input',type=Path,required=True);ap.add_argument('--matching',type=Path,required=True)
    ap.add_argument('--candidate-pool',type=Path,required=True);ap.add_argument('--source-report',type=Path,required=True);ap.add_argument('--source-geojson',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    co=json.loads(a.contract.read_text(encoding='utf-8'));inp=json.loads(a.input.read_text(encoding='utf-8'));mat=json.loads(a.matching.read_text(encoding='utf-8'))
    pool=json.loads(a.candidate_pool.read_text(encoding='utf-8'));rep=json.loads(a.source_report.read_text(encoding='utf-8'));src=json.loads(a.source_geojson.read_text(encoding='utf-8'))
    assert co['status']=='FROZEN_PRE_EXECUTION_CLEANROOM_CANDIDATE_GEOMETRY_RECOVERY' and co['guards']==GUARDS
    fi=co['frozen_cleanroom_inputs']; ps=co['preincident_geometry_sources']; op=co['output_policy']; mr=co['mapping_rule']
    assert sha(a.input)==fi['cleanroom_input_sha256'] and sha(a.matching)==fi['cleanroom_matching_sha256']
    assert sha(a.candidate_pool)==ps['candidate_pool_raw_sha256'] and sha(a.source_report)==ps['shortlist_geometry_report_sha256'] and sha(a.source_geojson)==ps['shortlist_geometry_geojson_sha256']
    assert rep['status']=='PASS_PREUNBLIND_NEGATIVE_CONTROL_SHORTLIST_GEOMETRY' and rep['guards']==GUARDS
    for k,v in ps['source_anti_leakage_required'].items(): assert rep[k] is v
    assert pool['outcome_evidence_read'] is False and pool['control_outcome_adjudication_performed'] is False
    selected=sorted(mat['selected_candidate_codes']); assert len(selected)==fi['selected_candidate_count']==7 and len(selected)==len(set(selected))
    bycode={x['candidate_code']:x for x in inp['candidates']}; assert set(selected)<=set(bycode)
    prec=int(mr['coordinate_precision_decimals'])
    legacy_by_xy={}
    for x in pool['candidates']:
        key=(round(float(x['mainstem_cell']['x_m']),prec),round(float(x['mainstem_cell']['y_m']),prec))
        assert key not in legacy_by_xy;legacy_by_xy[key]=x['candidate_id']
    legacy_to_code={}
    for code in selected:
        x=bycode[code]; key=(round(float(x['mainstem_confluence_x_m']),prec),round(float(x['mainstem_confluence_y_m']),prec))
        assert key in legacy_by_xy; old=legacy_by_xy[key]; assert old not in legacy_to_code; legacy_to_code[old]=code
    assert len(legacy_to_code)==7
    source_features={f['properties']['candidate_id']:f for f in src['features']}; assert set(source_features)==set(legacy_to_code)
    features=[]
    for old,code in legacy_to_code.items():
        f=source_features[old]
        props={'candidate_code':code,'RESEARCH_ONLY':True,'TEST_ONLY':True,'production_use':False,'production_ready':False,'operational_alerting_enabled':False,'outcome_evidence_read':False,'candidate_outcome_evidence_read':False}
        features.append({'type':'Feature','properties':props,'geometry':f['geometry']})
    features.sort(key=lambda f:f['properties']['candidate_code'])
    out={'type':'FeatureCollection','name':'chosica_2015_cleanroom_candidate_geometries_v0_1','features':features}
    raw=json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'; a.output.write_text(raw,encoding='utf-8')
    digest=sha(a.output); assert digest==op['expected_geojson_sha256']; assert len(features)==op['expected_feature_count']==7
    low=raw.lower(); assert 'nc_' not in low
    for token in ('pedregal','quirio','carossio','carosio','rayos de sol','cashahuacra','la libertad','a6680','official_outcome_evidence'):
        assert token not in low
    print(json.dumps({'status':'PASS_CLEANROOM_CANDIDATE_GEOMETRY_RECOVERY','feature_count':len(features),'geojson_sha256':digest},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
