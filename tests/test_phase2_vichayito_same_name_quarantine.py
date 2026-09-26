import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "phase2_vichayito_same_name_quarantine_v0_1.json"
REG = ROOT / "site" / "data" / "phase2" / "sources" / "piura_mancora_organos_official_evidence_v0_1.json"


def load(path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_vichayito_same_name_quarantine_is_fail_closed():
    cfg = load(CFG)

    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None

    adjudication = cfg["adjudication"]
    assert adjudication["same_name_is_sufficient_for_cross_province_geometry_binding"] is False
    assert adjudication["administrative_or_cartographic_context_is_sufficient_for_hydrologic_identity"] is False
    assert adjudication["paita_same_name_label_may_fill_talara_geometry_gap_without_crosswalk"] is False
    assert adjudication["paita_and_talara_features_proven_distinct"] is False
    assert adjudication["paita_and_talara_features_proven_same"] is False
    assert adjudication["talara_vichayito_geometry_status_after_review"] == "MISSING_NO_APPROXIMATION_ALLOWED"
    assert adjudication["talara_vichayito_activation_verified"] is False
    assert adjudication["negative_control_created"] is False
    assert adjudication["map_geometry_created"] is False


def test_registry_preserves_vichayito_cross_province_quarantine():
    reg = load(REG)

    assert reg["deployment_status"] == "RESEARCH_ONLY"
    assert reg["test_mode"] == "TEST_ONLY"
    assert reg["production_use"] is False
    assert reg["production_ready"] is False
    assert reg["operational_alerting_enabled"] is False
    assert reg["activation_gate"] == "BLOCKED"

    src = next(
        s for s in reg["sources"]
        if s["source_id"] == "IGP-PAITA-GEODYNAMIC-2022-036"
    )
    assert src["role"] == "CROSS_PROVINCE_SAME_NAME_CARTOGRAPHIC_CONTEXT_ONLY"
    assert any(
        "not by itself evidence" in claim or "same-name label" in claim
        for claim in src["admissible_claims"]
    )
    assert any(
        "Talara Vichayito catchment" in inference
        for inference in src["forbidden_inferences"]
    )

    qa = reg["qa"]
    assert qa["vichayito_named_ravine_confirmed"] is True
    assert qa["vichayito_activation_verified"] is False
    assert qa["vichayito_cross_province_same_name_binding_allowed"] is False

    artifacts = {a["path"]: a for a in reg["qa_artifacts"]}
    artifact = artifacts["config/phase2_vichayito_same_name_quarantine_v0_1.json"]
    assert artifact["may_supply_talara_vichayito_geometry"] is False
    assert artifact["may_bind_same_name_source_without_coordinate_crosswalk"] is False
