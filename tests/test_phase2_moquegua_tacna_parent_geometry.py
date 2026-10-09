import json
from pathlib import Path

CFG = Path("config/phase2_south_coast_moquegua_tacna_discovery_v0_1.json")
SCRIPT = Path("scripts/probe_phase2_moquegua_tacna_parent_geometry.py")

EXPECTED = {
    "tacna_de_la_concordia": "13152",
    "tacna_hospicio": "13154",
    "tacna_caplina": "13156",
    "tacna_sama": "13158",
    "tacna_locumba": "1316",
    "moquegua_ilo_moquegua": "13172",
    "moquegua_honda": "13178",
    "moquegua_tambo": "1318",
}

def test_parent_inventory_is_fail_closed():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
    rows = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    assert set(rows) == set(EXPECTED)
    for key, code in EXPECTED.items():
        row = rows[key]
        assert row["official_unit_code"] == code
        assert row["entity_role"] == "OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None

def test_geometry_probe_exists_and_uses_exact_ana_service():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ANA_WMS/MapServer/8/query" in text
    for code in EXPECTED.values():
        assert code in text
    assert "counts_as_event_footprint" in text
    assert "counts_as_operational_geometry" in text
    assert "PENDING_INTEGRATOR_CATALOG_QA" in text
