import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_national_subunit_contrast_v0_1.json"

def test_guardrails_and_code_family():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
    assert cfg["map_publish_enabled"] is False
    assert set(cfg["adjudication"]["national_query_codes"]) == {
        "1377121", "1377123", "1377124", "1377125", "1377127", "1377129"
    }
    assert cfg["adjudication"]["regional_renderer_labels_are_identity"] is False
    assert cfg["adjudication"]["code_prefix_is_topology"] is False
    assert cfg["adjudication"]["chorobal_outlet_resolved"] is False
