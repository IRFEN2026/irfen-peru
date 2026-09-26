import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_adjudication_matrix_v0_1.json"

def load():
    return json.loads(MATRIX.read_text(encoding="utf-8"))

def test_matrix_is_fail_closed():
    x = load()
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None

def test_all_targets_remain_unmapped_until_full_adjudication():
    x = load()
    assert len(x["targets"]) == 16
    for row in x["targets"].values():
        assert row["map_publishable"] is False
        assert row["outlet_status"] == "UNRESOLVED"
        assert row["geometry_status"].startswith("QUERY_PENDING")

def test_homonyms_are_explicitly_quarantined():
    x = load()
    assert "HOMONYM_QUARANTINE" in x["targets"]["san_pedro"]["geometry_status"]
    assert "HOMONYM_QUARANTINE" in x["targets"]["pena_negra"]["geometry_status"]

def test_geometry_promotion_requires_reproducible_chain():
    p = load()["promotion_requirements"]
    assert p["name_match_only_is_sufficient"] is False
    assert p["zorritos_spatial_context_required"] is True
    assert p["independent_identity_crosscheck_required"] is True
    assert p["exact_source_snapshot_and_hash_required"] is True
    assert p["outlet_or_downstream_connectivity_required"] is True
    assert p["approximate_points_allowed"] is False
    assert p["synthetic_connectors_allowed"] is False
    assert p["composite_parent_geometry_allowed"] is False
    assert p["absence_of_match_is_negative"] is False
