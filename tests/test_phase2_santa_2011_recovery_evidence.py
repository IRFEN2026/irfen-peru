import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ASSET=ROOT/'site/data/phase2/sources/ancash_santa_2011_lower_reach_recovery_v0_1.json'

def test_santa_2011_recovery_stays_fail_closed():
    a=json.loads(ASSET.read_text(encoding='utf-8'))
    assert a['study_scope']['start_progressive']=='0+000'
    assert a['study_scope']['end_progressive']=='50+000'
    assert a['coordinate_evidence']['crs_status']=='UNRESOLVED_FAIL_CLOSED'
    assert a['coordinate_evidence']['map_ready'] is False
    assert a['model_context']['observed_event_footprint'] is False
    assert a['model_context']['current_capacity'] is False
    assert a['safety']['production_use'] is False
    assert a['safety']['production_ready'] is False
    assert a['safety']['operational_alerting_enabled'] is False
    assert a['safety']['activation_gate']=='BLOCKED'
    assert a['safety']['decision_thresholds'] is None
    assert a['safety']['hydraulic_factors'] is None
