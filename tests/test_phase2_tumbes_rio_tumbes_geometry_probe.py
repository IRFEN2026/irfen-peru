from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import probe_tumbes_rio_tumbes_official_geometry as probe


def test_static_guards():
    assert probe.LAYER_ID == 2
    assert probe.EXPECTED_NAME == "Cuenca Tumbes"
    assert probe.SAFE["deployment_status"] == "RESEARCH_ONLY"
    assert probe.SAFE["test_mode"] == "TEST_ONLY"
    assert probe.SAFE["production_use"] is False
    assert probe.SAFE["production_ready"] is False
    assert probe.SAFE["activation_gate"] == "BLOCKED"
    assert probe.SAFE["decision_thresholds"] is None
    assert probe.SAFE["hydraulic_factors"] is None


def test_metadata_contract():
    good = {"id": 2, "name": "Cuenca Tumbes", "capabilities": "Map,Query,Data"}
    assert probe.validate_metadata(good) == "Cuenca Tumbes"


def test_one_polygon_contract():
    fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]
            }
        }]
    }
    assert probe.validate_feature_collection(fc) == (1, "Polygon")


def test_query_is_pinned_to_layer_two():
    url = probe.query_url()
    assert "/MapServer/2/query?" in url
    assert "where=1%3D1" in url
    assert "returnGeometry=true" in url
    assert "outSR=4326" in url
