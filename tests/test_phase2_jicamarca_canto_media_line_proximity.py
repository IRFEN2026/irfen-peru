import hashlib
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/phase2_jicamarca_canto_media_line_proximity_v0_1.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\\0".encode("ascii") + data).hexdigest()

def test_canto_media_frozen_lines_do_not_resolve_exact_junction():
    cfg = load(CONFIG)
    assert cfg["deployment_status"] == "RESEARCH_ONLY"
    assert cfg["test_mode"] == "TEST_ONLY"
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None

    loaded = {}
    for key, row in cfg["source_assets"].items():
        path = ROOT / row["path"]
        assert blob_sha(path) == row["git_blob_sha"]
        source = load(path)
        assert source["properties"]["deployment_status"] == "RESEARCH_ONLY"
        assert source["properties"]["production_use"] is False
        features = source["features"]
        assert sorted(f["properties"]["source_objectid"] for f in features) == sorted(row["expected_source_objectids"])
        for feature in features:
            assert feature["geometry"]["type"] == "LineString"
            assert feature["properties"]["geometry_role"] == "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"
            assert feature["properties"]["outlet_or_confluence"] is False
            assert feature["properties"]["activation_evidence"] is False
        loaded[key] = features

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32718", always_xy=True)
    pairwise = []
    for canto in loaded["canto_grande_upper_branch"]:
        cg = transform(transformer.transform, shape(canto["geometry"]))
        for media in loaded["media_luna"]:
            ml = transform(transformer.transform, shape(media["geometry"]))
            pairwise.append((cg.intersects(ml), cg.distance(ml)))

    assert len(pairwise) == cfg["analysis"]["expected_pair_count"] == 4
    assert sum(bool(intersects) for intersects, _ in pairwise) == 0
    global_min = min(distance for _, distance in pairwise)
    low, high = cfg["analysis"]["expected_global_min_distance_m_range"]
    assert low <= global_min <= high
    assert cfg["adjudication"]["exact_media_luna_canto_grande_junction_resolved"] is False
    assert cfg["adjudication"]["current_frozen_channel_assets_spatially_confirm_exact_junction"] is False
    assert cfg["adjudication"]["routing_enabled"] is False
    assert cfg["adjudication"]["travel_time_estimation_enabled"] is False
    assert cfg["adjudication"]["collector_effect_state"] == "NO_EVIDENCE"

def test_no_proximity_shortcut_is_allowed():
    cfg = load(CONFIG)
    forbidden = " ".join(cfg["forbidden"]).lower()
    assert "hydrologic disconnection" in forbidden
    assert "manufacture a junction" in forbidden
    assert "channel endpoint as an outlet" in forbidden
    assert "travel time" in forbidden
    assert "rimac overflow" in forbidden
