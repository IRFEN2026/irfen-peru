import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_red100k_channel_probe_v0_1.json"
SCRIPT = ROOT / "scripts/freeze_phase2_chicama_chao_red100k_channels.py"


def load_script():
    spec = importlib.util.spec_from_file_location("red100k_freeze", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_query_retains_variants_without_promoting_identity():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    names = m.candidate_names(cfg)
    assert len(names) == 9
    where = m.build_where("Chorobal", cfg["source"]["name_fields"])
    assert "r_q_text LIKE '%Chorobal%'" in where
    assert "nomb_min LIKE '%Chorobal%'" in where
    assert "nombre LIKE '%Chorobal%'" in where
    assert cfg["scientific_guards"]["same_name_is_identity"] is False
    assert cfg["scientific_guards"]["same_name_is_topology"] is False


def test_candidate_match_is_case_insensitive_and_preserves_ambiguity():
    m = load_script()
    props = {
        "r_q_text": "Rio Chorobal",
        "nomb_min": "CHOROBAL",
        "nombre": None,
    }
    assert m.candidate_matches(
        props, ["Chorobal", "Tutumo"], ["r_q_text", "nomb_min", "nombre"]
    ) == ["Chorobal"]


def test_output_contract_keeps_map_and_operations_blocked():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    m.validate_guards(cfg, "CONFIG")
    assert cfg["map_publish_enabled"] is False
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
