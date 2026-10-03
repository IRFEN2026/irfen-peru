import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_tumbes_rio_tumbes_ana_sources as freeze

PLAN = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_geometry_freeze_plan_v0_3.json"


def sample_metadata(layer_id, name):
    return {"id": layer_id, "name": name, "capabilities": "Map,Query,Data"}


def sample_fc():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            },
        }],
    }


def test_plan_is_fail_closed_and_atomic():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    freeze.validate_plan(plan)
    assert plan["deployment_status"] == "RESEARCH_ONLY"
    assert plan["test_mode"] == "TEST_ONLY"
    assert plan["production_use"] is False
    assert plan["production_ready"] is False
    assert plan["operational_alerting_enabled"] is False
    assert plan["activation_gate"] == "BLOCKED"
    assert plan["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert plan["decision_thresholds"] is None
    assert plan["hydraulic_factors"] is None
    assert plan["freeze_contract"]["preserve_raw_metadata_bytes"] is True
    assert plan["freeze_contract"]["preserve_raw_geojson_bytes"] is True
    assert plan["freeze_contract"]["all_layers_must_validate_before_any_write"] is True


def test_preregistered_layer_roles_are_separate():
    assert freeze.SPECS["basin"]["layer_id"] == 2
    assert freeze.SPECS["basin"]["event_date"] is None
    assert freeze.SPECS["event_20230428"]["layer_id"] == 66
    assert freeze.SPECS["event_20230428"]["event_date"] == "2023-04-28"
    assert freeze.SPECS["event_20230504"]["layer_id"] == 67
    assert freeze.SPECS["event_20230504"]["event_date"] == "2023-05-04"


def test_build_records_preserves_raw_and_canonical_hashes_without_promotion():
    payloads = {}
    names = {
        "basin": "Cuenca Tumbes",
        "event_20230428": "Areas Inundadas Rio Tumbes 28 Abril 2023",
        "event_20230504": "Areas Inundadas Rio Tumbes 04 Mayo 2023",
    }
    for key, spec in freeze.SPECS.items():
        metadata_raw = json.dumps(sample_metadata(spec["layer_id"], names[key]), indent=2).encode()
        geojson_raw = json.dumps(sample_fc(), indent=2).encode()
        payloads[key] = (metadata_raw, geojson_raw)
    inventory, parsed = freeze.build_freeze_records(payloads)
    assert set(parsed) == set(freeze.SPECS)
    assert len(inventory["layers"]) == 3
    guards = inventory["scientific_guards"]
    assert guards["map_publication_authorized_by_this_freeze"] is False
    assert guards["basin_geometry_is_event_footprint"] is False
    assert guards["event_footprints_are_basin_geometry"] is False
    for row in inventory["layers"]:
        assert len(row["raw_metadata_sha256"]) == 64
        assert len(row["canonical_metadata_sha256"]) == 64
        assert len(row["raw_geojson_sha256"]) == 64
        assert len(row["canonical_geojson_sha256"]) == 64


def test_wrong_layer_identity_fails_closed():
    spec = freeze.SPECS["basin"]
    try:
        freeze.validate_metadata(sample_metadata(999, "Cuenca Tumbes"), spec)
    except freeze.SourceContractError:
        pass
    else:
        raise AssertionError("wrong ANA layer id must fail closed")
