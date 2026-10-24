"""Fail-closed tests for the isolated Rímac corridor documentary replay.

These tests assert documentary semantics, not hydrologic identity or operational
readiness. They intentionally do not access networks or require GIS libraries.
"""
from __future__ import annotations

import json
from pathlib import Path

REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json"
)


def _registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _by_id():
    return {row["id"]: row for row in _registry()["units"]}


def test_registry_is_research_only_and_fail_closed():
    data = _registry()
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None


def test_documentary_rows_have_unique_ids_but_not_assumed_unique_catchments():
    data = _registry()
    rows = data["units"]
    assert len(rows) == len({row["id"] for row in rows})
    assert len(rows) == data["counts"]["total_documentary_rows"]
    assert data["counts"]["confirmed_unique_hydrologic_unit_count"] is None
    assert data["counts"]["possible_alias_double_count_unresolved"] is True


def test_national_membership_is_exact_id_only():
    data = _registry()
    assert data["provenance"]["national_master_reconciliation"]["match_method"] == (
        "EXACT_INVENTORY_ID_NOT_NAME_OR_ALIAS"
    )
    assert data["counts"]["national_master_membership_by_exact_id_verified"] is True


def test_alias_groups_are_not_silently_adjudicated():
    data = _registry()
    assert data["pending_identity_groups"]
    assert all(group["status"].startswith(("PENDING", "DISTRICT_CONFLICT")) for group in data["pending_identity_groups"])
    assert data["counts"]["possible_alias_double_count_unresolved"] is True


def test_no_new_map_geometry_or_outlet_published():
    data = _registry()
    assert all(row["map_publishable"] is False for row in data["units"])
    assert data["map_updates"]["new_geometries_published"] == 0
    assert data["map_updates"]["new_outlets_published"] == 0
    assert data["map_updates"]["new_collector_reaches_published"] == 0
    # Some rows carry research geometry references; this is not publication.
    assert data["collector_semantics"]["all_exact_outlets_unresolved_in_this_inventory"] is True


def test_no_hydraulic_numbers_promoted_from_documentary_leads():
    for row in _registry()["units"]:
        assert row["travel_time_tau"] is None, row["id"]
        assert row["discharge_q_i"] is None, row["id"]
        assert row["collector_capacity"] is None, row["id"]
        assert row["collector_overflow_evidence"] is None, row["id"]


def test_unverified_event_leads_never_count_as_confirmed_events():
    for row in _registry()["units"]:
        for lead in row["unverified_event_leads"]:
            assert lead.get("usable_as_confirmed_unit_event") is not True, row["id"]
            assert lead.get("event_ledger_entry_allowed") is not True, row["id"]


def test_quirio_and_cashahuacra_events_remain_unverified():
    rows = _by_id()
    for unit_id in ("lima_lurigancho_quirio", "lima_santa_eulalia_cashahuacra"):
        assert rows[unit_id]["verified_event_refs"] == []
        assert rows[unit_id]["unverified_event_leads"]


def test_igp_station_activations_are_not_discharge_or_stage():
    rows = _by_id()
    for unit_id in ("lima_huaycoloro", "jicamarca_rio_seco"):
        row = rows[unit_id]
        assert row["flow_or_stage_observation_refs"] == []
        assert row["verified_event_refs"] == []
        assert row["discharge_q_i"] is None


def test_la_ronda_conflicting_administrative_identity_stays_unresolved():
    row = _by_id()["lima_lurigancho_la_ronda"]
    assert row["district"] is None
    assert row["province"] is None
    assert row["map_publishable"] is False
    assert row["exact_confluence_coordinate"] is None


def test_dos_barrios_documentary_evidence_does_not_imply_catchment():
    row = _by_id()["lima_district_unknown_dos_barrios"]
    assert row["identity_adjudication"].startswith("DOCUMENTARY_LABEL_ONLY")
    assert row["reproducible_geometry_ref"] is None
    assert row["exact_confluence_coordinate"] is None
    assert row["verified_event_refs"] == []


def test_collector_semantics_separate_activation_works_and_overflow():
    semantics = _registry()["collector_semantics"]
    assert semantics["no_child_activation_implies_collector_overflow"] is True
    assert semantics["works_are_not_capacity"] is True
    assert semantics["design_is_not_measured_capacity"] is True
    assert semantics["station_activation_is_not_discharge"] is True
    assert semantics["imerg_context_only"] is True
    assert semantics["missing_data_is_not_negative"] is True
