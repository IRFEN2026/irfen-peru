import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_talara_topology_context():
    p=ROOT/"site/data/phase2/source_assessments/piura_talara_channel_topology_v0_1.json"
    x=json.loads(p.read_text())
    assert x["deployment_status"]=="RESEARCH_ONLY"
    assert x["activation_gate"]=="BLOCKED"
    assert x["channels"]["mangle"]["parent"]=="yale"
    assert x["channels"]["santa_rita"]["exact_outlet"] is False
    assert x["channels"]["politecnico"]["exact_outlet"] is False
    assert x["channels"]["acholado"]["reaches_pacific"] is False
    assert x["map_materialization_allowed"] is False
