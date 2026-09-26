import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_talara_topology_context():
    x=json.loads((ROOT/"site/data/phase2/source_assessments/piura_talara_channel_topology_v0_1.json").read_text())
    assert x["deployment_status"]=="RESEARCH_ONLY"
    assert x["activation_gate"]=="BLOCKED"
    assert x["channels"]["mangle"]["parent"]=="yale"
    assert x["channels"]["politecnico"]["exact_outlet"] is False
    assert x["channels"]["acholado"]["reaches_pacific"] is False
    assert x["map_materialization_allowed"] is False

def test_politecnico_1998_context():
    e=json.loads((ROOT/"site/data/phase2/source_assessments/piura_talara_politecnico_1998_v0_1.json").read_text())
    assert e["child"]=="quebrada_politecnico"
    assert e["exact_event_footprint"] is False
    assert e["measured_discharge"] is False
    assert e["transfer_to_other_children"] is False
    assert e["operational_threshold"] is False
