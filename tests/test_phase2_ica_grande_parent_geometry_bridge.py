import json
from pathlib import Path

def test_grande_bridge():
    c=json.loads(Path("config/phase2_ica_grande_parent_geometry_bridge_v0_1.json").read_text())
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    assert c["official_parent_identity"]["official_unit_code"]=="1372"
    r=c["reused_frozen_geometry"]
    assert len(r["normalized_geometry_sha256"])==64
    assert len(r["source_snapshot_sha256"])==64
    assert c["homonym_and_scope_guards"]["parent_uh_match_required_for_local_assignment"] is True
    assert c["summary"]["new_operational_zones"]==0
