#!/usr/bin/env python3
"""Validate exact pre-unblind Chosica 2015 morphometry and IMERG freeze artifacts."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
TARGETS={"cashahuacra","quirio","pedregal_san_antonio","la_libertad","carossio","rayos_de_sol"}

def sha256(p: Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--morph-report', required=True)
    ap.add_argument('--imerg-report', required=True)
    ap.add_argument('--morph-freeze', default='config/chosica_2015_morphometry_phase1_freeze_record_v0_1.json')
    ap.add_argument('--imerg-freeze', default='config/chosica_2015_preunblind_imerg_freeze_record_v0_1.json')
    a=ap.parse_args()
    mf, pf=load(a.morph_freeze), load(a.imerg_freeze)
    mrp, irp=Path(a.morph_report), Path(a.imerg_report)
    assert mf['phase1_frozen'] is True and pf['predictors_frozen'] is True
    assert mf['guards']==GUARDS and pf['guards']==GUARDS
    assert mrp.stat().st_size==mf['provenance']['report_size_bytes']
    assert irp.stat().st_size==pf['provenance']['report_size_bytes']
    assert sha256(mrp)==mf['provenance']['report_sha256']
    assert sha256(irp)==pf['provenance']['report_sha256']
    m=json.loads(mrp.read_text(encoding='utf-8')); i=json.loads(irp.read_text(encoding='utf-8'))
    assert m['status']=='PASS_CHOSICA_2015_PHASE1_MORPHOMETRY'
    assert m['phase']=='PHASE_1_PREUNBLIND_DEM_MORPHOMETRY'
    assert m['execution_revision']=='0.10_SINGLE_GRID_EXACT_PYSHEDS_CATCHMENT'
    assert m['target_count']==6 and {t['target_id'] for t in m['targets']}==TARGETS
    assert m['guards']==GUARDS
    assert m['a6680_numeric_reference_read'] is False
    assert m['outcome_evidence_read'] is False
    assert m['post_anchor_predictor_read'] is False
    assert m['revision_guards']['selection_or_tuning_from_metric_values'] is False
    assert m['revision_guards']['frozen_polygon_mask_modified'] is False
    assert m['revision_guards']['frozen_outlet_modified'] is False
    assert m['revision_guards']['scientific_quantity_changed'] is False
    for x in m['exact_geometry_dem_audit'].values():
        assert x['exact_binary_hash_match'] is True and x['geometry_or_outlet_modified'] is False
    assert i['status']=='PASS_CHOSICA_2015_PREUNBLIND_IMERG_EXTRACTION'
    assert i['phase']=='PREUNBLIND_PREDICTOR_RECONSTRUCTION'
    assert i['anchor_utc']=='2015-03-23T19:30:00Z'
    assert i['target_count']==6 and {t['target_id'] for t in i['targets']}==TARGETS
    assert i['guards']==GUARDS
    assert i['outcome_evidence_read'] is False and i['a6680_numeric_reference_read'] is False and i['post_anchor_predictor_read'] is False
    assert i['geometry_or_outlet_modified'] is False and i['window_shifted'] is False and i['zero_imputation_used'] is False
    for t in i['targets']:
        assert t['slot_count']==720 and t['valid_slot_count']==720 and abs(t['coverage_fraction']-1.0)<1e-12
        assert all(r['time_utc'] < i['anchor_utc'] for r in t['series'])
        assert all(r['accum_mm'] is not None and r['all_weighted_cells_present'] is True for r in t['series'])
        assert all(w['complete'] is True and w['accum_mm'] is not None for w in t['windows'].values())
    print(json.dumps({'status':'PASS_CHOSICA_2015_PREUNBLIND_FREEZE_VALIDATION','phase1_frozen':True,'predictors_frozen':True,'a6680_numeric_morphometry_comparison_allowed':True,'sealed_outcome_unblind_allowed':False},sort_keys=True))
if __name__=='__main__': main()
