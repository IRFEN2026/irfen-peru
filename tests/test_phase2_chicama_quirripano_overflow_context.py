import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_quirripano_overflow_context_2023.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_quirripano_event_context_stays_fail_closed():
    ev = load(EVID)
    assert ev["deployment_status"] == "RESEARCH_ONLY"
    assert ev["test_mode"] == "TEST_ONLY"
    assert ev["production_use"] is False
    assert ev["production_ready"] is False
    assert ev["operational_alerting_enabled"] is False
    assert ev["activation_gate"] == "BLOCKED"
    assert ev["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert ev["decision_thresholds"] is None
    assert ev["hydraulic_factors"] is None
    assert ev["map_eligible"] is False
    assert ev["map_changed"] is False
    assert ev["temporal_adjudication"]["exact_overflow_date_resolved"] is False
    assert ev["temporal_adjudication"]["exact_overflow_time_resolved"] is False
    assert ev["spatial_adjudication"]["exact_event_footprint_resolved"] is False
    assert ev["spatial_adjudication"]["outlet_resolved"] is False
    assert ev["qa"]["event_date_fabricated"] is False
    assert ev["qa"]["event_footprint_created"] is False
    assert ev["qa"]["threshold_created"] is False
    assert ev["qa"]["capacity_inferred"] is False
    assert ev["qa"]["absence_used_as_negative"] is False
