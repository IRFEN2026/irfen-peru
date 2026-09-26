import json
from pathlib import Path

def test_el_grillo_anchor_is_fail_closed():
    p = Path(__file__).resolve().parents[1] / "site/data/phase2/sources/tumbes_zorritos_el_grillo_ingemmet_anchor_v0_2.json"
    x = json.loads(p.read_text(encoding="utf-8"))
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    assert x["control_point"]["map_publishable_as_child_geometry"] is False
    assert x["control_point"]["counts_as_outlet"] is False
