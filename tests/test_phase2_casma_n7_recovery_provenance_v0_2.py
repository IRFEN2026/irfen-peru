import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "config/phase2_casma_n7_recovery_provenance_v0_2.json"

def test_casma_2007_provenance_is_frozen_fail_closed():
    x = json.loads(P.read_text(encoding="utf-8"))
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    assert x["study_provenance"]["md5"] == "e49d0383cf8520a13c0a6bcbdf505de1"
    assert x["study_provenance"]["geometry_role"] == "QA_ONLY_NOT_VECTOR"
    assert x["scientific_effect"]["geometry_recovered"] is False
    assert x["scientific_effect"]["pdf_digitized"] is False
    assert x["scientific_effect"]["map_publication_enabled"] is False
