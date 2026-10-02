import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_red100k_channel_probe_v0_1.json"
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_red100k_channel_probe_20260926.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_probe_is_research_only_and_not_mapped():
    cfg = load(CFG)
    ev = load(EVID)
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["map_publish_enabled"] is False
    assert ev["map_eligible"] is False
    assert ev["map_changed"] is False

def test_identity_and_topology_are_not_claimed():
    cfg = load(CFG)
    ev = load(EVID)
    g = cfg["scientific_guards"]
    assert g["same_name_is_identity"] is False
    assert g["same_name_is_topology"] is False
    assert g["line_is_subcatchment"] is False
    assert g["line_is_event_footprint"] is False
    assert g["chorobal_outlet_resolved"] is False
    assert ev["qa"]["topology_qa_complete"] is False
    assert ev["qa"]["chorobal_outlet_resolved"] is False
