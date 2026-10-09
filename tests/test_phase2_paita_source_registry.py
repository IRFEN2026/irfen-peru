import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site/data/phase2/sources/piura_paita_official_evidence_v0_1.json"

def test_paita_source_registry_is_fail_closed():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None
    ids = {row["source_id"] for row in data["sources"]}
    assert ids == {
        "IGP-PAITA-ZONIFICACION-2019",
        "MP-PAITA-EVAR-ZANJON-2021",
        "CENEPRED-PAITA-RPAS-2018",
    }
    for row in data["sources"]:
        assert row["admissible_claims"]
        assert row["forbidden_inferences"]
    qa = data["qa"]
    assert qa["documentary_topology_promoted_before_primary_archive"] is False
    assert qa["critical_or_risk_context_used_as_event"] is False
    assert qa["rpas_context_used_as_final_geometry"] is False
    assert qa["absence_of_report_is_negative"] is False
