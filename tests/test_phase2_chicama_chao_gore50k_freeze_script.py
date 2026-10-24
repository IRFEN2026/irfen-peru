import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_gore50k_channel_probe_v0_1.json"
SCRIPT = ROOT / "scripts/freeze_phase2_chicama_chao_gore50k_channels.py"


def load_script():
    spec = importlib.util.spec_from_file_location("gore50k_freeze", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_set_is_fixed_without_identity_promotion():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    names = m.candidates(cfg)
    assert len(names) == 9
    assert len(set(names)) == 9
    assert set(cfg["candidate_names"]["chao"]) == {"Chorobal", "Tutumo", "Tucumaca"}
    assert cfg["scientific_guards"]["same_name_is_identity"] is False
    assert cfg["scientific_guards"]["same_name_is_topology"] is False
    assert cfg["scientific_guards"]["chorobal_outlet_resolved"] is False


def test_query_preserves_all_name_field_matches():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    url = m.query_url(cfg, "Chorobal")
    q = parse_qs(urlparse(url).query)
    where = q["where"][0]
    for field in cfg["query_policy"]["name_fields"]:
        assert f"{field} LIKE '%Chorobal%'" in where
    assert q["returnGeometry"] == ["true"]
    assert q["outSR"] == ["4326"]
    assert q["geometryPrecision"] == ["7"]
    assert q["f"] == ["geojson"]


def test_match_logic_keeps_ambiguity_instead_of_auto_selecting():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    names = m.candidates(cfg)
    feature = {
        "properties": {
            "NOMBRE": "Rio Chorobal / Tutumo",
            "CUENCA": "Chorobal Tutumo",
        }
    }
    matches = m.feature_matches(feature, names, cfg["query_policy"]["name_fields"])
    assert "Chorobal" in matches
    assert "Tutumo" in matches


def test_fail_closed_guards_do_not_allow_map_publication():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    m.validate_guards(cfg)
    assert cfg["map_publish_enabled"] is False
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
