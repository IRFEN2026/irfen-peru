import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_zee_subunit_probe_v0_1.json"
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_subunit_geometry_sources_20260925.json"

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

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_guards_and_map_hold_are_explicit():
    cfg = load(CFG)
    ev = load(EVID)
    for obj in (cfg, ev):
        for key, expected in SAFE.items():
            assert obj[key] == expected
    assert cfg["map_publish_enabled"] is False
    assert cfg["probe_policy"]["publish_to_map"] is False
    assert ev["qa"]["map_changed"] is False
    assert ev["qa"]["threshold_created"] is False
    assert ev["qa"]["capacity_inferred"] is False
    assert ev["qa"]["absence_used_as_negative"] is False

def test_chicama_subunits_are_candidates_not_promoted_geometry():
    cfg = load(CFG)
    src = next(x for x in cfg["sources"] if x["source_id"] == "MINAM-ZEE-LALIBERTAD-UH-L39")
    assert set(src["candidate_names_chicama"]) == {
        "Cuenca Quirripano", "Cuenca Santanero", "Cuenca Ochape",
        "Cuenca Chuquillanqui", "Cuenca Huancay"
    }
    assert cfg["probe_policy"]["chicama_parent_code"] == "13772"
    assert cfg["probe_policy"]["require_parent_topology_review"] is True
    assert cfg["probe_policy"]["event_footprint_creation_forbidden"] is True

def test_chorobal_identity_is_strengthened_without_false_basin_promotion():
    cfg = load(CFG)
    ev = load(EVID)
    mpsch = next(x for x in cfg["sources"] if x["source_id"] == "MPSCH-OM-14-2018-CHOROBAL")
    du = next(x for x in cfg["sources"] if x["source_id"] == "DU-015-2023-CHAO-SECTORS")
    assert any("Calipuy" in c and "Lamball" in c and "Caypanda" in c for c in mpsch["admissible_claims"])
    assert any("Intercuenca 137711" in c for c in du["admissible_claims"])
    assert cfg["probe_policy"]["chao_national_parent_code"] == "137712"
    assert cfg["probe_policy"]["chorobal_standalone_basin_promotion_forbidden"] is True
    assert cfg["probe_policy"]["chorobal_outlet_status"] == "UNRESOLVED_PENDING_REPRODUCIBLE_ROUTING"
    finding = next(x for x in ev["findings"] if x["finding_id"] == "chorobal_cross_unit_sector_context")
    assert finding["map_eligible"] is False

def test_senamhi_and_thesis_roles_do_not_leak_into_local_thresholds():
    cfg = load(CFG)
    balance = next(x for x in cfg["sources"] if x["source_id"] == "SENAMHI-CHICAMA-BALANCE-2013")
    model = next(x for x in cfg["sources"] if x["source_id"] == "SENAMHI-CHICAMA-MODEL-2013")
    thesis = next(x for x in cfg["sources"] if x["source_id"] == "UPAO-CHICAMA-GALAXIA-PAMPA-HERMOSA-2022")
    assert any("named ravines" in x for x in balance["forbidden_inferences"])
    assert any("operational decision threshold" in x for x in model["forbidden_inferences"])
    assert any("current capacity" in x for x in thesis["forbidden_inferences"])
    assert cfg["mastergis_role"] == "METHOD_REFERENCE_ONLY_NOT_EVIDENCE"
