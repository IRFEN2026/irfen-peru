import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "site/data/phase2/sources/ancash_santa_2011_hydraulic_model_evidence_v0_1.json"
AXIS = ROOT / "site/data/phase2/sources/ancash_santa_2011_axis_points_v0_1.json"
POINTS = ROOT / "site/data/phase2/sources/ancash_santa_2011_critical_points_v0_1.json"
PKG = ROOT / "site/data/validation/phase2_discovery_packages/ancash_chimbote_lacramarca_santa_bajo.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_2011_study_is_documentary_and_not_map_geometry():
    d = load(DOC)
    assert d["component_id"] == "rio_santa_lower_reach"
    assert d["coordinate_reference"]["datum_resolved"] is False
    assert d["coordinate_reference"]["zone_resolved"] is False
    assert d["coordinate_reference"]["map_eligible"] is False
    assert d["scientific_effect"]["lower_santa_geometry_created"] is False
    assert d["scientific_effect"]["map_publication_enabled"] is False

def test_axis_preserves_source_chainage_conflicts():
    a = load(AXIS)
    assert len(a["table_points"]) == 50
    assert a["narrative_start"] == ["0+000", 758969, 9007565]
    assert a["table_points"][0] == ["1+000", 758969, 9007565]
    assert a["table_points"][-1] == ["50+000", 788372, 9037490]
    assert a["additional_endpoint_record"] == ["50+000", 788881, 9038309]
    assert a["silent_chainage_correction_forbidden"] is True
    assert a["map_eligible"] is False

def test_critical_points_are_context_not_event_or_capacity():
    p = load(POINTS)
    assert len(p["records"]) == 24
    assert p["critical_point_is_observed_event"] is False
    assert p["critical_point_is_current_capacity"] is False
    assert p["map_eligible"] is False

def test_existing_lower_santa_contract_remains_fail_closed():
    pkg = load(PKG)
    comp = {x["component_id"]: x for x in pkg["assets"]["geometry_components"]}["rio_santa_lower_reach"]
    assert comp["geometry"]["status"] == "MISSING_LOWER_REACH_REQUIRES_REPRODUCIBLE_REACH_GEOMETRY"
    assert comp["geometry"]["path"] is None
    assert pkg["production_use"] is False
    assert pkg["production_ready"] is False
    assert pkg["operational_alerting_enabled"] is False
    assert pkg["activation_gate"] == "BLOCKED"
