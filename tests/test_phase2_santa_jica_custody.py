import json
from pathlib import Path

def test_santa_jica_source_is_fail_closed():
    p=Path(__file__).resolve().parents[1]/'site/data/phase2/source_assessments/santa_2011_jica_external_custody_v0_1.json'
    d=json.loads(p.read_text())
    assert d['activation_gate']=='BLOCKED'
    assert d['raw_model_assets_recovered'] is False
    assert d['map_geometry_promotion_allowed'] is False
