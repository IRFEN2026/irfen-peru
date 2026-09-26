import json
from pathlib import Path

def test_arequipa_endpoint_registry():
    c = json.loads(Path("config/phase2_arequipa_cerro_colorado_ana_channel_endpoints_v0_1.json").read_text(encoding="utf-8"))
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["activation_gate"] == "BLOCKED"
    assert c["official_parent_unit"]["code"] == "132"
    assert len(c["segments"]) == 8
    assert c["guards"]["endpoint_pair_is_not_channel_centerline"] is True
    assert c["guards"]["endpoint_is_not_outlet"] is True
