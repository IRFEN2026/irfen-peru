import json
from pathlib import Path

def test_escalerilla_guardrails():
    c=json.loads(Path('config/phase2_arequipa_escalerilla_identity_v0_1.json').read_text())
    assert c['activation_gate']=='BLOCKED'
    assert c['child']['territorial_context']=='Cerro Colorado, Arequipa'
    assert c['unnamed_tributary']['expected_parent_subunit_code']=='13254'
    assert c['unnamed_tributary']['exact_confluence_status']=='NOT_FROZEN'
    assert c['child']['geometry_asset'] is None
    assert c['child']['map_publishable'] is False
