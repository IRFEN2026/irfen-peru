import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_topology_gate_v0_2.json"

def test_topology_gate_v02_fail_closed():
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
    assert cfg["map_publish_enabled"] is False
    gate = cfg["acceptance_gate"]
    required_false = [
        "exact_source_features_frozen","source_hashes_recorded",
        "parent_containment_qa_complete","line_continuity_qa_complete",
        "confluence_qa_complete","outlet_qa_complete",
        "regional_vs_national_contrast_complete","same_name_is_identity",
        "nearest_feature_auto_selection","longest_feature_auto_selection",
        "faja_is_channel_centerline","faja_is_subcatchment",
        "faja_is_event_footprint","polygon_is_event_footprint",
        "line_is_subcatchment","absence_is_negative",
        "works_imply_capacity","map_publication_allowed",
    ]
    assert all(gate[k] is False for k in required_false)

def test_topology_roles_are_not_promoted():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    chicama = cfg["chicama"]
    assert chicama["parent_context_code"] == "13772"
    assert chicama["exposure_nodes"]["Cartavio"] == "EXPOSURE_NODE_NOT_BASIN"
    assert chicama["exposure_nodes"]["Santiago de Cao"] == "EXPOSURE_NODE_NOT_BASIN"
    assert chicama["map_eligible_children"] == []
    chao = cfg["chao"]
    assert chao["chorobal_standalone_basin_promotion_forbidden"] is True
    assert chao["chorobal_outlet_resolved"] is False
    assert chao["local_pluvial_drainage_separate"] is True
    assert chao["map_eligible_children"] == []
    rels = {(r["subject"], r["relation"], r["object"]): r for r in chao["documentary_relationships"]}
    assert ("Tutumo", "DERIVATION_FROM", "Chorobal") in rels
    assert ("Tucumaca", "TRIBUTARY_TO", "Chorobal") in rels
    assert ("Huancaybito", "WITHIN_FAJA_CONTEXT_OF", "Chorobal") in rels
    assert all(r["geometry_proof"] is False for r in rels.values())
