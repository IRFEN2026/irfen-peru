import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site/data/phase2/sources/tumbes_bocapan_ana_code_crosswalk_v0_1.json"

def test_crosswalk_stays_research_only_and_unpromoted():
    x = json.loads(DATA.read_text(encoding="utf-8"))
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    assert x["legacy_coding"]["unit_code"] == "13936"
    assert x["current_coding"]["unit_code"] == "13918"
    assert x["adjudication"]["geometry_equivalence_verified"] is False
    assert x["adjudication"]["map_geometry_replacement_authorized"] is False
