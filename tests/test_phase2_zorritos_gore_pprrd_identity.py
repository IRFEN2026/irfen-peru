import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/phase2/sources/tumbes_zorritos_gore_pprrd_identity_v0_1.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_zorritos_bocapan_coastal_ravines.json"

SAFE = {
    "status": "RESEARCH_ONLY_IDENTITY_CONTEXT",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_gore_tumbes_identity_sidecar_is_fail_closed():
    e = load(EVIDENCE)
    for key, expected in SAFE.items():
        assert e[key] == expected
    assert e["identity_context_only"] is True
    assert e["prevention_activity_is_event"] is False
    assert e["intervention_ambit_is_catchment_geometry"] is False
    assert e["works_define_historical_capacity"] is False
    assert e["child_event_transfer_allowed"] is False

def test_named_ravines_correspond_to_existing_independent_children():
    e = load(EVIDENCE)
    p = load(PACKAGE)
    children = p["hydrologic_components"]
    expected_ids = {
        "el_rubio", "san_pedro", "pena_negra",
        "bocapan_casitas", "el_tiburon", "nuevo_paraiso",
    }
    rows = {row["component_id"]: row for row in e["named_ravines"]}
    assert set(rows) == expected_ids
    for component_id in expected_ids:
        assert component_id in children
        assert children[component_id]["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
        assert children[component_id]["map_publishable"] is False
        assert children[component_id]["activation_verified"] is False

def test_sidecar_does_not_promote_source_to_event_or_threshold():
    e = load(EVIDENCE)
    assert e["source_id"] == "GORE-TUMBES-PPRRD-2024-2030-GUIA"
    assert e["source_locator"] == "PPRRD Tumbes 2024-2030, page 36"
    assert e["decision_thresholds"] is None
    assert e["hydraulic_factors"] is None
