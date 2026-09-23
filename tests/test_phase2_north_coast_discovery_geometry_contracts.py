import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "site/data/validation/phase2_discovery_contracts"
SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_pativilca_and_fortaleza_are_exact_separate_ana_units():
    p = load("lima_norte_pativilca.json")
    f = load("lima_norte_fortaleza_paramonga.json")
    assert p["hydrologic_identity"]["ana_unit_code"] == "13758"
    assert p["hydrologic_identity"]["ana_unit_name"] == "Cuenca Pativilca"
    assert f["hydrologic_identity"]["ana_unit_code"] == "137592"
    assert f["hydrologic_identity"]["ana_unit_name"] == "Cuenca Fortaleza"
    assert p["hydrologic_identity"]["ana_unit_code"] != f["hydrologic_identity"]["ana_unit_code"]
    assert "Cuenca Fortaleza" in p["hydrologic_identity"]["must_not_merge_with"]
    assert "Cuenca Pativilca" in f["hydrologic_identity"]["must_not_merge_with"]
    assert f["hydrologic_identity"]["territorial_reference"] == "Paramonga"
    assert f["hydrologic_identity"]["territorial_reference_is_basin"] is False


def test_discovery_geometry_contracts_fail_closed_and_non_operational():
    for name in ("lima_norte_pativilca.json", "lima_norte_fortaleza_paramonga.json"):
        c = load(name)
        for key, value in SAFE.items():
            assert c[key] == value
        q = c["source_query"]
        code = c["hydrologic_identity"]["ana_unit_code"]
        assert q["where"] == f"CODIGO='{code}'"
        assert q["endpoint"].startswith("https://www.idep.gob.pe/")
        g = c["assets"]["geometry"]
        assert g["counts_as_operational_geometry"] is False
        assert g["counts_as_event_footprint"] is False
        assert c["map_policy"]["approximate_geometry_forbidden"] is True
        assert c["map_policy"]["risk_or_alert_layer"] is False
