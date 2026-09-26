import json
from pathlib import Path

def test_la_huaylla_guardrails():
    c=json.loads(Path('config/phase2_arequipa_la_huaylla_identity_v0_1.json').read_text())
    assert c['activation_gate']=='BLOCKED'
    assert c['child']['expected_parent_uh_code']=='132'
    assert c['child']['geometry_asset'] is None
    assert c['child']['map_publishable'] is False
    assert c['works_segment_context']['reported_length_m']==5710
    assert c['works_segment_context']['geometry_semantics']=='AUTHORIZED_WORKS_SEGMENT_LIMITS_NOT_FULL_CHANNEL_AXIS'
