import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "site" / "data" / "independent_validation" / "basins.json"


def load_registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_independent_map_is_strictly_non_operational():
    data = load_registry()
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_status"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["operational_labels_allowed"] is False
    assert data["blind_outcome_evidence"] == "SEALED"
    assert data["map_policy"]["never_enters_operational_calc"] is True
    for basin in data["basins"]:
        assert basin["production_use"] is False
        assert basin["production_ready"] is False
        assert basin["operational_alerting_enabled"] is False


def test_every_mapped_basin_has_reproducible_geometry_reference():
    data = load_registry()
    assert data["basins"]
    for basin in data["basins"]:
        geometry = basin["geometry"]
        assert geometry["source_path"]
        assert geometry["feature_property"]
        assert geometry["feature_value"]
        source = ROOT / "site" / geometry["source_path"]
        assert source.exists(), f"Missing geometry source for {basin['basin_id']}: {source}"
        fc = json.loads(source.read_text(encoding="utf-8"))
        assert any(
            feature.get("properties", {}).get(geometry["feature_property"]) == geometry["feature_value"]
            for feature in fc.get("features", [])
        ), f"Geometry selector did not resolve for {basin['basin_id']}"


def test_public_indicators_are_scientific_traceability_only():
    data = load_registry()
    forbidden_indicator_ids = {
        "risk",
        "risk_score",
        "threat",
        "threat_score",
        "priority",
        "priority_score",
        "alert",
        "activation",
        "operational_status",
    }
    for basin in data["basins"]:
        indicators = basin["public_indicators"]
        assert 1 <= len(indicators) <= 6
        ids = {item["id"] for item in indicators}
        assert ids.isdisjoint(forbidden_indicator_ids)
        assert basin["blind_assessment_status"] == "SEALED"


def test_missing_is_not_recast_as_low_risk_and_smap_is_not_imputed():
    data = load_registry()
    assert data["map_policy"]["missing_data_semantics"] == "UNKNOWN_OR_MISSING_NEVER_LOW_RISK"
    cashahuacra = next(b for b in data["basins"] if b["basin_id"] == "cashahuacra")
    assert cashahuacra["sensors"]["smap"]["status"] == "MISSING_FOR_EVENT_WINDOW"
    assert cashahuacra["sensors"]["smap"]["imputation_allowed"] is False


def test_cashahuacra_requires_outlet_revalidation_against_ana_seed():
    data = load_registry()
    cashahuacra = next(b for b in data["basins"] if b["basin_id"] == "cashahuacra")
    geometry = cashahuacra["geometry"]
    assert geometry["status"] == "REVIEW_ONLY_CANDIDATE_REVALIDATION_REQUIRED"
    assert geometry["ana_channel_seed"]["role"] == "SNAP_SEED_ONLY_NOT_FORCED_OUTLET"
    assert geometry["existing_outlet_to_ana_seed_distance_m"] > 0
    assert geometry["raw_byte_hash_independently_reverified"] is False
