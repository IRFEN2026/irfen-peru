import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_red100k_channel_freeze_v0_1.json"
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_red100k_exact_name_freeze_20260926.json"
SCRIPT = ROOT / "scripts/freeze_phase2_chicama_chao_red100k_channels.py"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_freeze_contract_remains_research_only_and_unmapped():
    cfg = load(CFG)
    ev = load(EVID)
    for obj in (cfg, ev):
        assert obj["deployment_status"] == "RESEARCH_ONLY"
        assert obj["test_mode"] == "TEST_ONLY"
        assert obj["production_use"] is False
        assert obj["production_ready"] is False
        assert obj["operational_alerting_enabled"] is False
        assert obj["activation_gate"] == "BLOCKED"
        assert obj["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
        assert obj["decision_thresholds"] is None
        assert obj["hydraulic_factors"] is None
    assert cfg["map_publish_enabled"] is False
    assert cfg["freeze_policy"]["map_publish_enabled"] is False
    assert ev["map_eligible"] is False
    assert ev["map_changed"] is False

def test_exact_candidate_set_and_documentary_constraints_are_bounded():
    cfg = load(CFG)
    assert cfg["candidate_groups"]["chao"] == ["Chorobal", "Tutumo", "Tucumaca"]
    assert set(cfg["candidate_groups"]["chicama"]) == {
        "Chicama", "Quirripano", "Santanero", "Ochape", "Chuquillanqui", "Huancay"
    }
    c = cfg["independent_documentary_constraints"]
    assert c["tutumo_derivation_from_chorobal"] is True
    assert c["tucumaca_tributary_to_chorobal"] is True
    assert c["use_as_geometry"] is False
    assert c["use_as_outlet"] is False
    assert c["use_as_subcatchment"] is False
    assert c["use_as_event_footprint"] is False

def test_live_capture_remains_pending_and_not_misrepresented():
    ev = load(EVID)
    assert ev["status"] == "EXECUTABLE_FREEZE_READY_LIVE_FEATURE_CAPTURE_PENDING"
    assert ev["source_features_path"] is None
    assert ev["source_features_sha256"] is None
    assert ev["feature_count"] is None
    assert ev["qa"]["exact_channel_features_frozen"] is False
    assert ev["qa"]["same_name_identity_adjudicated"] is False
    assert ev["qa"]["topology_qa_complete"] is False
    assert ev["qa"]["chorobal_outlet_resolved"] is False
    assert ev["qa"]["absence_used_as_negative"] is False

def test_freeze_executable_exists_and_is_offline_only():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "urllib" not in text
    assert "requests" not in text
    assert "urlopen" not in text
    assert "raw_capture" in text
