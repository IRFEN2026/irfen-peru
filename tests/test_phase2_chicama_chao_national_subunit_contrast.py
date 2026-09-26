import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_national_subunit_contrast_v0_1.json"
SRC = ROOT / "site/data/phase2/sources/minam_national_uh_layer1_service_contract_20260926.json"
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chao_huamanzana_code_family_contrast_20260926.json"

EXPECTED = {"1377121","1377123","1377124","1377125","1377127","1377129"}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_guardrails_and_code_family():
    cfg, src, ev = load(CFG), load(SRC), load(EVID)
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
    assert ev["map_eligible"] is False and ev["map_changed"] is False
    assert set(cfg["national_query_codes"]) == EXPECTED
    assert set(ev["regional_renderer_codes"]) == EXPECTED
    assert cfg["regional_renderer_labels_are_identity"] is False
    assert cfg["code_prefix_is_topology"] is False
    assert cfg["chorobal_outlet_resolved"] is False
    assert ev["chorobal_outlet_resolved"] is False
    assert ev["absence_used_as_negative"] is False
    assert src["source_id"] == "MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-L1"
    assert src["geometry_type"] == "esriGeometryPolygon"
    assert src["spatial_reference"] == 4326
    assert src["use"] == "INDEPENDENT_NATIONAL_CONTRAST_ONLY"
    assert src["map_eligible"] is False
    assert ev["national_service_contract_git_blob_sha"] == "fa0a9793f7fafaefa1e4b82eb14358ac31a50284"
