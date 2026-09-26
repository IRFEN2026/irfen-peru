import json
from pathlib import Path

def test_sources_registered():
    c=json.loads(Path('config/phase2_arequipa_additional_channel_sources_v0_1.json').read_text())
    assert len(c['sources'])==4
    assert all(s['official'] for s in c['sources'])
    assert all(s['verified_on']=='2026-09-26' for s in c['sources'])
    assert all(s['content_sha256'] is None for s in c['sources'])
