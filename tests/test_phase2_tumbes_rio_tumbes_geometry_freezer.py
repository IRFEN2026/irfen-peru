import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_tumbes_rio_tumbes_official_geometry as freezer


def test_layer_contract_is_exact_and_separated():
    assert set(freezer.LAYERS) == {2, 66, 67}
    assert freezer.LAYERS[2]["role"] == "OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT"
    assert freezer.LAYERS[2]["event_date"] is None
    assert freezer.LAYERS[66]["role"] == "OBSERVED_EVENT_FOOTPRINT_ONLY"
    assert freezer.LAYERS[66]["event_date"] == "2023-04-28"
    assert freezer.LAYERS[67]["role"] == "OBSERVED_EVENT_FOOTPRINT_ONLY"
    assert freezer.LAYERS[67]["event_date"] == "2023-05-04"


def test_research_guards_fail_closed():
    safe = freezer.SAFE
    assert safe["deployment_status"] == "RESEARCH_ONLY"
    assert safe["test_mode"] == "TEST_ONLY"
    assert safe["production_use"] is False
    assert safe["production_ready"] is False
    assert safe["operational_alerting_enabled"] is False
    assert safe["activation_gate"] == "BLOCKED"
    assert safe["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert safe["decision_thresholds"] is None
    assert safe["hydraulic_factors"] is None


def test_query_contract_is_reproducible():
    for layer_id in (2, 66, 67):
        url = freezer.query_url(layer_id)
        assert f"/{layer_id}/query?" in url
        assert "where=1%3D1" in url
        assert "outFields=%2A" in url
        assert "returnGeometry=true" in url
        assert "outSR=4326" in url
        assert "geometryPrecision=7" in url
        assert "f=geojson" in url


def test_validate_basin_requires_one_polygon():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
        ],
    }
    count, types = freezer.validate_geojson(2, fc)
    assert count == 1
    assert types == {"Polygon"}


def test_event_layers_are_not_required_to_be_single_feature():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}} ,
            {"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]}},
        ],
    }
    count, types = freezer.validate_geojson(66, fc)
    assert count == 2
    assert types == {"Polygon", "MultiPolygon"}


def test_canonical_bytes_are_stable():
    a = {"z": 1, "a": {"b": 2}}
    b = {"a": {"b": 2}, "z": 1}
    assert freezer.canonical_bytes(a) == freezer.canonical_bytes(b)
    assert freezer.sha256(freezer.canonical_bytes(a)) == freezer.sha256(freezer.canonical_bytes(b))
