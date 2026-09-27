import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "config/phase2_santa_2011_hydraulic_source_recovery_v0_1.json"

def load():
    return json.loads(DOC.read_text(encoding="utf-8"))

def test_santa_2011_recovery_is_fail_closed():
    d = load()
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["activation_gate"] == "BLOCKED"
    assert d["native_package_gate"]["recovered"] is False
    assert d["map_publication_enabled"] is False
