import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_phase2_local_activation_hierarchy as hierarchy


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_universal_registry_covers_every_current_parent_without_parent_activation():
    registry = hierarchy.build_registry()
    candidate_inventory = load(ROOT / "config/phase2_candidate_inventory_v0_2.json")
    discovery_inventory = load(ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json")
    expected = {x["candidate_id"] for x in candidate_inventory["candidates"]} | {
        x["discovery_id"] for x in discovery_inventory["discovery_units"]
    }
    parents = {x["parent_id"] for x in registry["parent_units"]}
    assert parents == expected
    assert all(x["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE" for x in registry["parent_units"])
    assert all(x["activation_state_allowed"] is False for x in registry["parent_units"])
    assert registry["summary"]["parent_activation_state_assignments"] == 0
    assert registry["summary"]["new_operational_units"] == 0


def test_research_states_are_local_scientific_evidence_only():
    arch = load(ROOT / "config/phase2_local_activation_hierarchy_v0_1.json")
    assert arch["research_evidence_states"] == hierarchy.ALLOWED_STATES
    assert arch["state_semantics"]["states_are_operational_alerts"] is False
    assert arch["state_semantics"]["states_are_risk_classes"] is False
    assert arch["state_semantics"]["parent_state_assignment_forbidden"] is True
    assert arch["parent_policy"]["child_evidence_promotes_parent_activation"] is False
    assert arch["parent_policy"]["allowed_parent_summary"] == "N_SUBUNITS_WITH_EVIDENCE"


def test_imerg_receiver_and_semantic_guards_fail_closed():
    arch = load(ROOT / "config/phase2_local_activation_hierarchy_v0_1.json")
    assert arch["meteorology_policy"]["imerg_role"] == "REGIONAL_OR_SUBBASIN_CONTEXT_ONLY"
    assert arch["meteorology_policy"]["imerg_alone_selects_small_ravine_activation"] is False
    assert arch["receiver_policy"]["tributary_activation_implies_receiver_overflow"] is False
    guards = arch["semantic_guardrails"]
    assert guards["faja_margin_is_event_footprint"] is False
    assert guards["works_or_design_are_historical_capacity"] is False
    assert guards["critical_point_is_observed_event"] is False
    assert guards["cross_basin_threshold_transfer_allowed"] is False
    assert guards["absence_of_report_is_negative_control"] is False
    assert guards["distinct_hydrologic_units_may_be_artificially_connected"] is False


def test_map_policy_keeps_parent_context_and_children_separate():
    arch = load(ROOT / "config/phase2_local_activation_hierarchy_v0_1.json")
    policy = arch["map_policy"]
    assert policy["parent_style"] == "GREY_CONTEXT"
    assert policy["children_are_independent_layers"] is True
    assert policy["historical_footprints_separate"] is True
    assert policy["missing_geometry_is_not_drawn"] is True
    assert policy["parent_composite_from_child_union_forbidden"] is True
    assert policy["risk_colors_forbidden"] is True
    assert policy["alerts_forbidden"] is True


def test_existing_phase2_spatial_subunits_are_local_not_parent_geometry():
    registry = hierarchy.build_registry()
    rows = registry["phase2_local_units"]
    assert rows
    assert all(row["activation_state_allowed"] is True for row in rows)
    assert all(row["counts_as_parent_geometry"] is False for row in rows)
    assert all(row["counts_as_operational_geometry"] is False for row in rows)
    assert all(row["map_eligible"] is True for row in rows)
    assert all(row["geometry_path"].startswith("site/data/phase2/geometries/") for row in rows)


def test_rimac_santa_eulalia_demonstrator_reuses_reproducible_local_subunits_only():
    registry = hierarchy.build_registry()
    rows = [
        x for x in registry["demonstrator_local_units"]
        if x["parent_id"] == "lima_este_santa_eulalia_rimac"
    ]
    by_id = {x["local_unit_id"]: x for x in rows}
    assert set(by_id) == {
        "cashahuacra",
        "shingolay",
        "santa_eulalia_mainstem",
        "rimac_mainstem_receiver",
        "santa_eulalia_rimac_confluence",
    }
    assert by_id["cashahuacra"]["map_eligible"] is True
    assert by_id["shingolay"]["map_eligible"] is True
    assert by_id["cashahuacra"]["spatial_contract_id"].endswith(":cashahuacra:v0.1")
    assert by_id["shingolay"]["spatial_contract_id"].endswith(":shingolay:v0.1")
    assert by_id["santa_eulalia_mainstem"]["map_eligible"] is False
    assert by_id["rimac_mainstem_receiver"]["map_eligible"] is False
    assert by_id["santa_eulalia_rimac_confluence"]["map_eligible"] is False
    assert all(x["evidence_state"] is None for x in rows)


def test_existing_reproducible_discovery_children_remain_local_and_never_operational():
    registry = hierarchy.build_registry()
    for child in registry["discovery_local_units"]:
        assert child["activation_state_allowed"] is True
        assert child["allowed_research_states"] == hierarchy.ALLOWED_STATES
        assert child["counts_as_parent_geometry"] is False
        assert child["counts_as_operational_geometry"] is False
        if child["map_eligible"]:
            assert child["geometry_path"].startswith("site/data/phase2/geometries/")


def test_explicit_weakening_is_rejected_even_when_legacy_omissions_are_inherited():
    unsafe = {
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "operational_alerting_enabled": True,
    }
    with unittest.TestCase().assertRaisesRegex(hierarchy.HierarchyError, "operational_alerting_enabled"):
        hierarchy.reject_explicit_conflict(unsafe, "TEST")


def test_global_guards_exact():
    arch = load(ROOT / "config/phase2_local_activation_hierarchy_v0_1.json")
    for key, expected in hierarchy.SAFE.items():
        assert arch[key] == expected
