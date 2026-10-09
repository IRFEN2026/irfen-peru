"""Fail-closed tests for the Rímac corridor documentary inventory.

Documentary rows are not a count of unique hydrologic catchments.
A source mention, regulatory faja, work or event is not publishable GIS geometry.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json"


def load():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_inventory_is_research_only_and_never_operational():
    d = load()
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None
    assert d["counts"]["confirmed_unique_hydrologic_unit_count"] is None
    assert d["counts"]["possible_alias_double_count_unresolved"] is True


def test_documentary_rows_have_unique_ids_but_are_not_unique_catchments():
    d = load()
    units = d["units"]
    ids = [unit["id"] for unit in units]
    assert len(ids) == len(set(ids))
    assert len(units) == d["counts"]["total_documentary_rows"]
    assert (
        d["counts"]["national_audit_corridor_documentary_rows"]
        + d["counts"]["jicamarca_additional_documentary_rows"]
        == len(units)
    )
    assert d["provenance"]["base_inventory_ref"] == (
        "config/phase2_national_inventory_completeness_audit_v0_1.json"
    )
    assert d["counts"]["confirmed_unique_hydrologic_unit_count"] is None
    for unit in units:
        assert unit["id"] and unit["documentary_label"]
        assert unit["record_role"] and unit["identity_adjudication"]
        assert isinstance(unit["source_refs"], list)
        assert isinstance(unit["documentary_variants"], list)
        for source in unit["source_refs"]:
            assert source["source_id"]
            assert isinstance(source["source_text_verified"], bool)


def test_pending_aliases_are_not_promoted_to_identity_equivalence():
    d = load()
    ids = {unit["id"] for unit in d["units"]}
    groups = d["pending_identity_groups"]
    assert groups
    for group in groups:
        assert group["status"].startswith("PENDING") or group["status"] == "DISTRICT_CONFLICT_PENDING"
        assert len(group["labels"]) >= 2
        assert group["needed"]
        assert set(group["inventory_ids"]).issubset(ids)
    assert d["counts"]["possible_alias_double_count_unresolved"] is True


def test_no_outlet_tau_capacity_overflow_or_new_map_publication():
    d = load()
    assert d["map_updates"] == {
        "new_geometries_published": 0,
        "new_outlets_published": 0,
        "new_collector_reaches_published": 0,
    }
    semantics = d["collector_semantics"]
    for key in (
        "no_child_activation_implies_collector_overflow",
        "works_are_not_capacity",
        "design_is_not_measured_capacity",
        "regulatory_faja_is_not_channel_or_event_footprint",
        "station_activation_is_not_discharge",
        "imerg_context_only",
        "missing_data_is_not_negative",
        "all_exact_outlets_unresolved_in_this_inventory",
    ):
        assert semantics[key] is True

    for unit in d["units"]:
        assert unit["map_publishable"] is False
        for field in (
            "outlet_coordinate",
            "exact_confluence_coordinate",
            "travel_time_tau",
            "discharge_q_i",
            "collector_capacity",
            "collector_overflow_evidence",
        ):
            assert unit[field] is None
        if unit["reproducible_geometry_ref"] is not None:
            # An existing documentary line ref is not an approved catchment,
            # outlet or operationally publishable channel.
            assert unit["channel_or_catchment_geometry"] == (
                "OFFICIAL_IGP_LINE_CONTEXT_NOT_CATCHMENT"
            )


def test_unresolved_requested_names_remain_leads_not_negative_evidence():
    d = load()
    leads = d["requested_unresolved_name_leads"]
    assert len(leads) == d["counts"]["missing_source_name_leads"]
    for lead in leads:
        assert lead["requested_name"]
        assert lead["result"] in (
            "NO_SOURCE_FOUND_IN_THIS_SWEEP",
            "ONLY_SHORTER_LABEL_FOUND",
        )
        assert lead["note"]



def test_dos_barrios_official_post_sweep_attestation_remains_fail_closed():
    """Two official mentions attest a label, not a uniquely routed or mapped ravine."""
    d = load()
    leads = [
        lead for lead in d["requested_unresolved_name_leads"]
        if lead["requested_name"] == "Dos Barrios"
    ]
    assert len(leads) == 1
    lead = leads[0]
    # Preserve the provenance of the earlier sweep; later evidence supersedes
    # its source-search conclusion without rewriting the historical observation.
    assert lead["result"] == "NO_SOURCE_FOUND_IN_THIS_SWEEP"
    evidence = lead["post_sweep_official_evidence"]
    assert evidence["status"] == (
        "OFFICIAL_DOCUMENTARY_NAME_ATTESTED_NOT_YET_INTEGRATED_AS_UNIT"
    )
    assert evidence["identity_adjudication"] == (
        "PENDING_PRIMARY_GEOMETRY_AND_ALIAS_REVIEW"
    )
    assert {source["publisher"] for source in evidence["sources"]} == {
        "SENAMHI", "INGEMMET"
    }
    assert all(source["source_url"].startswith("https://") for source in evidence["sources"])
    assert all(source["original_pdf_sha256"] is None for source in evidence["sources"])
    assert all(source["exact_geometry"] is None for source in evidence["sources"])
    event_mentions = [
        source for source in evidence["sources"]
        if source["evidence_type"] == "HISTORICAL_PERIOD_EVENT_MENTION"
    ]
    assert len(event_mentions) == 1
    assert event_mentions[0]["event_period"] == "2012-04"
    assert event_mentions[0]["event_day"] is None

    # An attested label must not silently become an extra confirmed unit or
    # be equated to Pablo Patron / Dos Amigos by locality or similarity.
    assert evidence["integrated_in_units"] is False
    assert evidence["confirmed_unique_hydrologic_unit"] is False
    assert evidence["map_publishable"] is False
    assert evidence["exact_confluence"] is None
    for field in (
        "travel_time_tau", "discharge_q_i", "collector_capacity",
        "collector_overflow_evidence",
    ):
        assert evidence[field] is None
    assert not any(
        unit["documentary_label"] == "Dos Barrios" for unit in d["units"]
    )
    assert d["counts"]["confirmed_unique_hydrologic_unit_count"] is None
