import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/piura_talara_parinas.json"


def load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_talara_parinas_parent_contract_is_fail_closed():
    c = load()
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["test_mode"] == "TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"] == "BLOCKED"
    assert c["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None


def test_exact_ana_parent_identity_and_query_lock():
    c = load()
    h = c["hydrologic_identity"]
    assert h["ana_unit_code"] == "1392"
    assert h["ana_unit_name"] == "Cuenca Pariñas"
    assert h["territorial_reference_is_basin"] is False
    q = c["source_query"]
    assert q["where"] == "CODIGO='1392'"
    assert q["endpoint"].endswith("/MapServer/8/query")
    assert q["out_sr"] == 4326


def test_child_crosswalk_fails_closed():
    g = load()["crosswalk_gate"]
    assert g["local_children_auto_assigned_to_cuenca_parinas"] is False
    assert g["quebrada_acholado_auto_crosswalk_to_ana_acholada"] is False
    assert g["same_or_similar_name_is_identity_proof"] is False
    assert g["exact_child_outlets_required_before_collector_assignment"] is True


def test_parent_context_is_not_operational_or_child_geometry():
    c = load()
    a = c["assets"]["geometry"]
    assert a["status"] == "PENDING_EXACT_ANA_GEOMETRY_FREEZE"
    assert a["counts_as_operational_geometry"] is False
    assert a["counts_as_event_footprint"] is False
    assert c["map_policy"]["approximate_geometry_forbidden"] is True
    assert c["map_policy"]["child_geometry_not_derived_from_parent_polygon"] is True
    assert c["map_policy"]["risk_or_alert_layer"] is False
