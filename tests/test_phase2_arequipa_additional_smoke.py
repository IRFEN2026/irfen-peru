import json
from pathlib import Path

def test_pastoraiz_guardrails():
    c=json.loads(Path('config/phase2_arequipa_pastoraiz_identity_v0_1.json').read_text())
    assert c['deployment_status']=='RESEARCH_ONLY'
    assert c['test_mode']=='TEST_ONLY'
    assert c['activation_gate']=='BLOCKED'
    assert c['child']['geometry_asset'] is None
    assert c['child']['map_publishable'] is False
