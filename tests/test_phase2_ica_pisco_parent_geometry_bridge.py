import hashlib
import json
from pathlib import Path

CFG = Path("config/phase2_ica_pisco_parent_geometry_bridge_v0_1.json")
VAL = Path("site/data/phase2/geometries/ica_pisco_san_andres_geometry_validation.json")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha(path):
    data = load(path)
    payload = (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_bridge_remains_fail_closed_and_research_only():
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
    assert cfg["summary"]["new_operational_zones"] == 0


def test_bridge_matches_frozen_official_pisco_geometry_exactly():
    cfg = load(CFG)
    reused = cfg["reused_frozen_geometry"]
    validation = load(Path(reused["geometry_validation_path"]))
    assert validation["official_unit"] == {
        "area_km2": 4208.7453,
        "code": "13752",
        "name": "Cuenca Pisco",
    }
    assert validation["normalized_geometry_sha256"] == reused["normalized_geometry_sha256"]
    assert validation["source_snapshot_sha256"] == reused["source_snapshot_sha256"]
    assert canonical_sha(Path(reused["geometry_path"])) == reused["normalized_geometry_sha256"]
    assert canonical_sha(Path(reused["source_snapshot_path"])) == reused["source_snapshot_sha256"]

    geom = load(Path(reused["geometry_path"]))
    assert len(geom["features"]) == 1
    props = geom["features"][0]["properties"]
    assert props["official_hydrologic_unit_code"] == "13752"
    assert props["official_hydrologic_unit_name"] == "Cuenca Pisco"
    assert props["counts_as_complete_candidate_geometry"] is False
    assert props["loaded_into_operational_calculation"] is False
    assert props["carries_alert_values"] is False
    assert props["carries_risk_classification"] is False
    assert props["decision_thresholds"] is None
    assert props["hydraulic_factors"] is None


def test_local_pisco_children_are_not_promoted_by_parent_geometry_reuse():
    cfg = load(CFG)
    assert cfg["base_discovery_dependency"]["pull_request"] == 308
    assert cfg["map_binding_policy"]["new_discovery_parent_registry_update_in_this_pr"] is False
    assert cfg["map_binding_policy"]["future_parent_style"] == "CONTEXT_GREY_ONLY"
    assert cfg["map_binding_policy"]["risk_colours_forbidden"] is True
    assert cfg["map_binding_policy"]["event_footprint_inference_forbidden"] is True

    children = {row["child_id"]: row for row in cfg["local_children_remaining_fail_closed"]}
    assert set(children) == {"ica_quitasol", "ica_paracas"}
    for row in children.values():
        assert row["geometry_asset"] is None
        assert row["outlet"] is None
        assert row["map_publishable"] is False
        assert row["event_state"] == "CRITICAL_POINT_CONTEXT_NOT_EVENT"

    guards = cfg["scientific_guards"]
    assert all(guards.values())
