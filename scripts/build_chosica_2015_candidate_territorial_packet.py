#!/usr/bin/env python3
"""Build the candidate-only territorial unblind packet from committed clean-room artifacts.

This script is intentionally package-only. It does not read target outcomes, A6680, post-event
territorial evidence, contaminated adjudication material, or any network source.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

GUARDS={"RESEARCH_ONLY":True,"TEST_ONLY":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False}
ALLOWED_CANDIDATE_KEYS={
    "candidate_code","mainstem_confluence_x_m","mainstem_confluence_y_m","area_km2",
    "relief_m","mean_basin_slope_deg","preanchor_mm_if_frozen"
}
FORBIDDEN_TOKENS=("target_name","target_id","outcome","a6680","damage","severity","activation","shortlist","rank","score")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--contract',type=Path,required=True)
    ap.add_argument('--freeze-record',type=Path,required=True)
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--matching',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    co=json.loads(a.contract.read_text(encoding='utf-8'))
    fr=json.loads(a.freeze_record.read_text(encoding='utf-8'))
    inp=json.loads(a.input.read_text(encoding='utf-8'))
    mat=json.loads(a.matching.read_text(encoding='utf-8'))
    assert co['guards']==fr['guards']==inp['guards']==mat['guards']==GUARDS
    assert fr['status']=='FROZEN_CLEANROOM_PACKAGE_AND_MATCHING'
    assert fr['gates']['committed_freeze_verified'] is True
    assert fr['gates']['candidate_territorial_unblind_allowed'] is True
    assert fr['gates']['sealed_target_unblind_allowed'] is False
    assert sha(a.input)==co['frozen_inputs']['cleanroom_input']['sha256']
    assert sha(a.matching)==co['frozen_inputs']['cleanroom_matching']['sha256']
    selected=list(mat['selected_candidate_codes'])
    assert len(selected)==co['frozen_inputs']['selected_candidate_count']==7
    assert len(selected)==len(set(selected))
    by_code={c['candidate_code']:c for c in inp['candidates']}
    assert set(selected) <= set(by_code)
    packet_candidates=[]
    for code in sorted(selected):
        src=by_code[code]
        extra=set(src)-ALLOWED_CANDIDATE_KEYS
        assert not extra, (code, sorted(extra))
        assert src.get('preanchor_mm_if_frozen') is not None, f'MISSING_FROZEN_PREANCHOR {code}'
        packet_candidates.append({
            'candidate_code':code,
            'mainstem_confluence_x_m':src['mainstem_confluence_x_m'],
            'mainstem_confluence_y_m':src['mainstem_confluence_y_m'],
            'analysis_crs':co['packet_policy']['analysis_crs'],
            'area_km2':src['area_km2'],
            'relief_m':src['relief_m'],
            'mean_basin_slope_deg':src['mean_basin_slope_deg'],
            'preanchor_mm':src['preanchor_mm_if_frozen']
        })
    out={
        'schema_version':'0.1',
        'batch_id':co['batch_id'],
        'status':'PASS_FROZEN_CANDIDATE_ONLY_TERRITORIAL_PACKET',
        'phase':'CANDIDATE_ONLY_TERRITORIAL_UNBLIND_PRE_EVIDENCE',
        'guards':GUARDS,
        'selection_is_immutable':True,
        'candidate_count':len(packet_candidates),
        'candidates':packet_candidates,
        'event_window':co['event_window'],
        'source_allowlisting_required_before_read':True,
        'free_web_search_allowed':False,
        'target_outcome_sources_allowed':False,
        'candidate_replacement_allowed':False,
        'candidate_reranking_allowed':False,
        'feedback_to_matching_allowed':False,
        'sealed_target_unblind_allowed':False,
        'input_sha256':sha(a.input),
        'matching_sha256':sha(a.matching),
        'contract_sha256':sha(a.contract),
        'freeze_record_sha256':sha(a.freeze_record)
    }
    raw=json.dumps(out,sort_keys=True,separators=(',',':'))+'\n'
    low=raw.lower()
    for tok in FORBIDDEN_TOKENS:
        if tok in low:
            # Policy field names containing "outcome" are allowed only at top-level false guards.
            if tok=='outcome' and '"target_outcome_sources_allowed":false' in low:
                continue
            raise AssertionError(f'FORBIDDEN_TOKEN_IN_PACKET {tok}')
    a.output.write_text(raw,encoding='utf-8')
    print(json.dumps({'status':out['status'],'candidate_count':len(packet_candidates),'packet_sha256':sha(a.output)},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
