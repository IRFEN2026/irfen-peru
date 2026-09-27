from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
ASSESSMENT = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"


def test_casma_descendant_recovery_has_no_ci_only_area_exception():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "diagnostic_bypass" not in source
    assert "is_bounded_ci_probe" not in source


def test_casma_descendant_drift_remains_fail_closed():
    d = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
    assert d["status"] == "FAIL_CLOSED_DESCENDANT_ATTRIBUTE_DRIFT"
    assert d["findings"]["strict_2007_attribute_equivalence_passed"] is False
    assert d["findings"]["map_publication_authorized"] is False
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None
