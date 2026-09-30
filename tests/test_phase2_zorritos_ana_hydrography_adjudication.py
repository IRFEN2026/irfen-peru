import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_adjudication_matrix_v0_1.json"
PLAN = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_source_plan_v0_1.json"
CONTEXT = ROOT / "site/data/phase2/sources/tumbes_zorritos_extended_identity_context_v0_1.json"
PROBE = ROOT / "scripts/probe_zorritos_ana_hydrography.py"


def load_matrix():
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def load_plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def load_context():
    return json.loads(CONTEXT.read_text(encoding="utf-8"))


def test_matrix_is_fail_closed():
    x = load_matrix()
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None


def test_all_18_targets_remain_unmapped_until_full_adjudication():
    x = load_matrix()
    assert len(x["targets"]) == 18
    for row in x["targets"].values():
        assert row["map_publishable"] is False
        assert row["outlet_status"] == "UNRESOLVED"
        assert row["geometry_status"].startswith("QUERY_PENDING")


def test_target_sets_match_and_include_la_tucilla():
    matrix_targets = set(load_matrix()["targets"])
    plan = load_plan()
    plan_targets = set(plan["target_children"])
    assert matrix_targets == plan_targets
    assert len(matrix_targets) == 18
    assert "la_tucilla" in matrix_targets


def test_la_tucilla_is_fail_closed_anchor_not_geometry():
    row = load_matrix()["targets"]["la_tucilla"]
    plan = load_plan()
    assert row["identity_source"].startswith("ANA-2015-2016 official map anchor")
    assert row["geometry_status"] == "QUERY_PENDING_OFFICIAL_MAP_ANCHOR_NOT_LINE_GEOMETRY"
    assert row["outlet_status"] == "UNRESOLVED"
    assert row["map_publishable"] is False
    assert "la_tucilla" in plan["query_policy"]["official_map_anchor_not_line_geometry_quarantine"]
    assert "la_tucilla" in plan["query_policy"]["scope_adjudication_quarantine"]
    assert "la_tucilla" in plan["query_policy"]["marine_hazard_separation_required"]


def test_la_tucilla_ingemmet_a7454_context_is_identity_only():
    context = load_context()
    source = context["sources"]["INGEMMET-A7454-24-050-TUCILLAL"]
    adjudication = context["adjudication"]["la_tucilla"]
    guards = context["scientific_guards"]

    assert source["feature_code"] == "24-050"
    assert source["source_name"] == "Quebrada Tucillal (Zorritos)"
    assert source["coordinate_reference"] == "WGS84 / UTM zone 17S"
    assert source["northing_m"] == 9595829
    assert source["easting_m"] == 538559
    assert source["claim_scope"] == "OFFICIAL_NAMED_RAVINE_IDENTITY_AND_CRITICAL_HAZARD_POINT_CONTEXT_ONLY"
    assert source["snapshot_sha256"] is None
    assert source["freeze_status"] == "SOURCE_IDENTIFIED_BYTES_NOT_FROZEN"

    assert adjudication["identity_status"] == "OFFICIAL_NAMED_RAVINE_IDENTITY_CORROBORATED_INGEMMET_A7454_24_050"
    assert adjudication["geometry_status"] == "OFFICIAL_POINT_AND_MAP_ANCHORS_ONLY_LINE_AND_CATCHMENT_UNRESOLVED"
    assert adjudication["outlet_status"] == "UNRESOLVED"
    assert adjudication["event_status"] == "NO_DATED_CHILD_LEVEL_ACTIVATION_INFERRED_FROM_SUSCEPTIBILITY"
    assert adjudication["map_publishable"] is False

    assert guards["point_anchor_is_outlet"] is False
    assert guards["point_anchor_is_line_geometry"] is False
    assert guards["point_anchor_is_catchment"] is False
    assert guards["susceptibility_is_dated_activation_event"] is False
    assert guards["susceptibility_is_threshold"] is False
    assert guards["susceptibility_is_capacity"] is False


def test_homonyms_and_paired_context_remain_quarantined():
    x = load_matrix()
    assert "HOMONYM_QUARANTINE" in x["targets"]["san_pedro"]["geometry_status"]
    assert "HOMONYM_QUARANTINE" in x["targets"]["pena_negra"]["geometry_status"]
    leoncio = x["targets"]["leoncio_prado"]
    assert "PAIRED_EVENT_CONTEXT_QUARANTINE" in leoncio["geometry_status"]
    assert leoncio["map_publishable"] is False
    assert leoncio["outlet_status"] == "UNRESOLVED"


def test_miramar_spatial_crosswalk_remains_quarantined():
    row = load_matrix()["targets"]["miramar"]
    plan = load_plan()
    assert row["outlet_status"] == "UNRESOLVED"
    assert row["map_publishable"] is False
    assert "miramar" in plan["query_policy"]["spatial_crosswalk_quarantine"]


def test_probe_check_plan_only_is_ci_safe_and_passes():
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--check-plan-only"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "PASS_ZORRITOS_ANA_HYDROGRAPHY_PLAN" in completed.stdout


def test_geometry_promotion_requires_reproducible_chain():
    p = load_matrix()["promotion_requirements"]
    assert p["name_match_only_is_sufficient"] is False
    assert p["zorritos_spatial_context_required"] is True
    assert p["independent_identity_crosscheck_required"] is True
    assert p["exact_source_snapshot_and_hash_required"] is True
    assert p["outlet_or_downstream_connectivity_required"] is True
    assert p["approximate_points_allowed"] is False
    assert p["synthetic_connectors_allowed"] is False
    assert p["composite_parent_geometry_allowed"] is False
    assert p["absence_of_match_is_negative"] is False
