import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/"site/data/phase2/sources/tumbes_rio_tumbes_geometry_freeze_plan_v0_3.json"
SCRIPT=ROOT/"scripts/replay_phase2_tumbes_rio_tumbes_geometry.py"

spec=importlib.util.spec_from_file_location("tumbes_replay",SCRIPT)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def load_plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))

def test_plan_identity_and_service_are_exact():
    p=load_plan(); mod.validate_plan(p)
    assert p["discovery_id"]=="tumbes_rio_tumbes"
    assert p["service_item_id"]=="05eaeb1a998f42a3a5e9649482bd9332"
    rows={r["layer_id"]:r for r in p["layers"]}
    assert rows[2]["expected_name"]=="Cuenca Tumbes"
    assert rows[66]["expected_name"]=="Áreas Inundadas Río Tumbes 28 Abril 2023 - 3290.85 Ha"
    assert rows[67]["expected_name"]=="Áreas Inundadas Río Tumbes 04 Mayo 2023 - Caudal 1845.77_m3_s - 1085.32 Ha"

def test_plan_keeps_basin_and_event_roles_separate():
    p=load_plan(); rows={r["layer_id"]:r for r in p["layers"]}
    assert rows[2]["role"]=="OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT"
    assert rows[2]["counts_as_event_footprint"] is False
    for lid,date in ((66,"2023-04-28"),(67,"2023-05-04")):
        assert rows[lid]["role"]=="OBSERVED_EVENT_FOOTPRINT_ONLY"
        assert rows[lid]["event_date"]==date
        assert rows[lid]["counts_as_basin_geometry"] is False

def test_plan_is_fail_closed():
    p=load_plan()
    assert p["deployment_status"]=="RESEARCH_ONLY"
    assert p["test_mode"]=="TEST_ONLY"
    assert p["production_use"] is False
    assert p["production_ready"] is False
    assert p["operational_alerting_enabled"] is False
    assert p["activation_gate"]=="BLOCKED"
    assert p["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert p["decision_thresholds"] is None
    assert p["hydraulic_factors"] is None
    assert all(v is False for v in p["guards"].values())

def test_replay_accepts_only_polygonal_feature_collections():
    row={"layer_id":2}
    good={"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}}]}
    fs,types=mod.validate_fc(good,row)
    assert len(fs)==1 and types=={"Polygon"}
    bad={"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"LineString","coordinates":[[0,0],[1,1]]}}]}
    with pytest.raises(mod.ReplayError,match="UNEXPECTED_GEOMETRY"):
        mod.validate_fc(bad,row)

def test_replay_does_not_download_when_snapshots_are_absent():
    rawdir=ROOT/load_plan()["freeze_contract"]["raw_directory"]
    if rawdir.exists():
        pytest.skip("Frozen snapshots already materialized; missing-snapshot gate no longer applicable")
    with pytest.raises(mod.ReplayError,match="FROZEN_RAW_BYTES_MISSING_2"):
        mod.replay()
