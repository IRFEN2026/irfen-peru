import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "site/data/phase2/sources/tumbes_bocapan_code_crosswalk_note_v0_1.json"

def test_bocapan_code_crosswalk_note_is_fail_closed():
    x = json.loads(PATH.read_text(encoding="utf-8"))
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    assert x["legacy_code"] == "13936"
    assert x["current_code"] == "13918"
    assert x["geometry_equivalence_verified"] is False
    assert x["map_geometry_replacement_authorized"] is False
