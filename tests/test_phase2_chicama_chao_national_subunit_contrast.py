import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_national_subunit_contrast_v0_1.json"
SRC = ROOT / "site/data/phase2/sources/minam_national_uh_layer1_service_contract_20260926.json"
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chao_huamanzana_code_family_contrast_20260926.json"

EXPECTED_CODES = {"1377121", "1377123", "1377124", "1377125", "1377127", "1377129"}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_guardrails_and_code_family():
    cfg = load(CFG)
    ev = load(EVID)
    for obj in (cfg, ev):
        assert obj["deployment_status"] == "RESEARCH_ONLY"
        assert obj["test_mode"] == "TEST_ONLY"
        assert obj["production_use"] is False
        assert obj["production_ready"] is False
        assert obj["operational_alerting_enabled"] is False
        assert obj["activation_gate"] == "BLOCKED"
        assert obj["decision_thresholds"] is None
        assert obj["hydraulic_factors"] is None
    assert cfg["map_publish_enabled"] is False
    assert ev["map_eligible"] is False
    assert ev["map_changed"] is False
    assert set(cfg["adjudication"]["national_query_codes"]) == EXPECTED_CODES
    assert set(ev["regional_renderer_codes"]) == EXPECTED_CODES
    assert cfg["adjudication"]["regional_renderer_labels_are_identity"] is False
    assert cfg["adjudication"]["code_prefix_is_topology"] is False
    assert cfg["adjudication"]["chorobal_outlet_resolved"] is False
    assert ev["chorobal_outlet_resolved"] is False
    assert ev["absence_used_as_negative"] is False

def test_national_service_is_only_an_independent_contrast():
    src = load(SRC)
    ev = load(EVID)
    assert src["source_id"] == "MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-L1"
    assert src["geometry_type"] == "esriGeometryPolygon"
    assert src["spatial_reference"] == 4326
    assert "CODIGO" in src["fields"]
    assert "Nombre_UH" in src["fields"]
    assert src["use"] == "INDEPENDENT_NATIONAL_CONTRAST_ONLY"
    assert src["map_eligible"] is False
    assert ev["national_service_contract_path"] == SRC.relative_to(ROOT).as_posix()
    assert ev["national_service_contract_git_blob_sha"] == "fa0a9793f7fafaefa1e4b82eb14358ac31a50284"
    assert ev["exact_regional_features_frozen"] is False
    assert ev["exact_national_features_frozen"] is False
    assert ev["parent_containment_qa_complete"] is False
    assert ev["channel_routing_qa_complete"] is False
