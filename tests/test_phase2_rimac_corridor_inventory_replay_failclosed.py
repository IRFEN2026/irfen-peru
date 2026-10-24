"""Independent fail-closed smoke tests for the clean Rímac inventory replay.

This test is intentionally self-contained: the inventory may be replayed from
a diverged documentary PR without importing its unmerged source archives.
No assertion here validates a geographic identity or authorizes map publication.
"""
import json
from pathlib import Path

INVENTORY = (
    Path(__file__).resolve().parents[1]
    / "config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json"
)


def _inventory():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_replay_is_nonoperational_and_unknown_is_not_low_risk():
    d = _inventory()
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None


def test_documentary_rows_are_not_a_deduplicated_hydrologic_census():
    d = _inventory()
    units = d["units"]
    ids = [u["id"] for u in units]
    assert len(ids) == len(set(ids))
    assert len(ids) == d["counts"]["total_documentary_rows"]
    assert d["counts"]["confirmed_unique_hydrologic_unit_count"] is None
    assert d["counts"]["possible_alias_double_count_unresolved"] is True
    # Pending name relationships are evidence leads, never implicit alias merges.
    ids_set = set(ids)
    for group in d["pending_identity_groups"]:
        assert set(group["inventory_ids"]) <= ids_set
        assert ("PENDING" in group["status"] or "CONFLICT" in group["status"])
    for unit in units:
        assert unit["identity_adjudication"] != "CONFIRMED_HYDROLOGIC_UNIT"
        # Documentary spelling/sector variants must never silently become
        # adjudicated aliases or additional hydrologic units.
        for variant in unit.get("documentary_variants", []):
            assert variant["alias_adjudication"] == "PENDING_NOT_MERGED", unit["id"]
            assert variant["source_id"], unit["id"]
        # A verified internal JSON contract is not equivalent to verified
        # original source bytes. External source-text promotion requires an
        # explicit original SHA-256; the hash claim itself still needs a
        # separate byte-level verification before any scientific promotion.
        for source in unit["source_refs"]:
            if source["source_text_verified"] is True and not source["source_id"].startswith("config/"):
                digest = source.get("original_pdf_sha256")
                assert isinstance(digest, str) and len(digest) == 64, unit["id"]
                assert all(c in "0123456789abcdef" for c in digest.lower()), unit["id"]
    assert d["counts"]["national_audit_corridor_documentary_rows"] + (
        d["counts"]["jicamarca_additional_documentary_rows"]
    ) == len(units)
    # Official name leads are retained for discovery but never inflate the
    # count of adjudicated catchments or documentary inventory rows.
    # Name-only leads are retained without silently acquiring event, flow,
    # receiver, geometry or routing evidence. Missing GIS is not absence.
    leads = d["official_unmaterialized_name_leads"]
    assert len({lead["documentary_name"] for lead in leads}) == len(leads)
    for lead in leads:
        assert lead["source_text_verified"] is False
        assert lead["original_pdf_bytes_archived_in_this_contract"] is False
        assert lead["original_pdf_sha256"] is None
        assert lead["map_publishable"] is False
        assert lead["counted_as_confirmed_unique_hydrologic_unit"] is False
        assert lead["catchment_geometry"] is None
        assert lead["channel_geometry"] is None
        assert lead["outlet_coordinate"] is None
        assert lead["exact_confluence_coordinate"] is None
        assert lead["receiver_chain_adjudicated"] is False
        assert lead["verified_event_refs"] == []
        assert lead["rainfall_observation_refs"] == []
        assert lead["flow_or_stage_observation_refs"] == []
        assert lead["travel_time_tau"] is None
        assert lead["collector_capacity"] is None
        assert lead["collector_overflow_evidence"] is None
    design = d["official_road_crossing_design_leads"]
    assert design["source_text_verified"] is False
    assert design["original_pdf_sha256"] is None
    assert design["documentary_row_count_increment"] == 0
    assert design["confirmed_unique_hydrologic_unit_count_increment"] == 0
    assert design["road_chainage_is_not_outlet_or_geodetic_coordinate"] is True
    assert design["project_design_is_not_constructed_work_or_measured_hydraulic_capacity"] is True
    for candidate in design["candidates"]:
        assert candidate["map_publishable"] is False
        assert candidate["geometry_ref"] is None
        assert candidate["outlet_coordinate"] is None
        assert candidate["exact_confluence_coordinate"] is None
        assert candidate["measured_discharge"] is None
        assert candidate["travel_time_tau"] is None
        assert candidate["capacity_evidence"] is None


def test_no_documentary_unit_is_map_publishable_or_has_inferred_routing():
    d = _inventory()
    for u in d["units"]:
        assert u["map_publishable"] is False, u["id"]
        assert u["outlet_coordinate"] is None, u["id"]
        assert u["exact_confluence_coordinate"] is None, u["id"]
        assert u["travel_time_tau"] is None, u["id"]
        assert u["discharge_q_i"] is None, u["id"]
        assert u["rainfall_observation_refs"] == [], u["id"]
        assert u["flow_or_stage_observation_refs"] == [], u["id"]
        assert u["collector_capacity"] is None, u["id"]
        assert u["collector_overflow_evidence"] is None, u["id"]
        # Frozen documentary line references are not permission to publish.
    # Documentary receiver links, engineering works and monitoring triggers
    # cannot silently become hydraulic routing, capacity or overflow evidence.
    semantics = d["collector_semantics"]
    for flag in (
        "no_child_activation_implies_collector_overflow",
        "works_are_not_capacity",
        "design_is_not_measured_capacity",
        "regulatory_faja_is_not_channel_or_event_footprint",
        "station_activation_is_not_discharge",
        "imerg_context_only",
        "missing_data_is_not_negative",
        "all_exact_outlets_unresolved_in_this_inventory",
    ):
        assert semantics[flag] is True, flag
    assert d["map_updates"]["new_geometries_published"] == 0
    assert d["map_updates"]["new_outlets_published"] == 0
    assert d["map_updates"]["new_collector_reaches_published"] == 0


def test_ambiguous_names_and_administrative_conflicts_remain_unresolved():
    d = _inventory()
    by_id = {u["id"]: u for u in d["units"]}
    ronda = by_id["lima_lurigancho_la_ronda"]
    assert ronda["district"] is None
    assert ronda["province"] is None
    assert ronda["administrative_assignment"] == (
        "UNRESOLVED_CONFLICTING_DOCUMENTARY_LOCATIONS"
    )
    assert len(ronda["administrative_location_leads"]) >= 2
    assert ronda["exact_confluence_coordinate"] is None
    assert by_id["lima_district_unknown_dos_barrios"]["receiver_relation"] == (
        "UNKNOWN_NOT_ASSUMED"
    )
    dos_barrios = by_id["lima_district_unknown_dos_barrios"]
    assert dos_barrios["verified_event_refs"] == []
    # The primary-source archive is in a separate, unmerged PR (#363).
    # A reference to its hashes is provenance, not independent validation
    # within this replay, and cannot promote hydrologic identity or events.
    dependency = dos_barrios["evidence_archive_dependency"]
    assert dependency["status"] == "UNMERGED_PR_363_EXTERNAL_TO_THIS_REPLAY"
    assert dependency["pull_request"] == 363
    assert dependency["archive_bundled_in_this_replay"] is False
    assert dependency["archive_hashes_are_external_provenance_not_independent_replay_validation"] is True
    assert dependency["does_not_promote_hydrologic_identity_or_event"] is True
    assert dos_barrios["identity_adjudication"] != "CONFIRMED_HYDROLOGIC_UNIT"
    assert dos_barrios["map_publishable"] is False
    assert any(
        "Dos Barrios" in g["labels"]
        and "Pablo Patrón/Dos Amigos" in g["labels"]
        and g["status"] == "PENDING_ADJUDICATION"
        for g in d["pending_identity_groups"]
    )


def test_unverified_events_and_station_triggers_do_not_become_flow():
    d = _inventory()
    by_id = {u["id"]: u for u in d["units"]}
    for key in ("lima_lurigancho_quirio", "lima_santa_eulalia_cashahuacra"):
        assert by_id[key]["verified_event_refs"] == []
    for key in ("lima_huaycoloro", "jicamarca_rio_seco"):
        u = by_id[key]
        assert u["verified_event_refs"] == []
        assert u["rainfall_observation_refs"] == []
        assert u["flow_or_stage_observation_refs"] == []
        assert u["station_activation_context_refs"]
    for u in d["units"]:
        for lead in u["unverified_event_leads"]:
            assert lead["usable_as_confirmed_unit_event"] is False
            assert lead["source_text_verified"] is False
    assert by_id["jicamarca_media_luna"]["verified_event_refs"] == [
        "config/phase2_jicamarca_discovery_v0_1.json#/historical_evidence/0"
    ]

    # The 2017 COEN annex is a documentary name sweep, not a measured
    # per-ravine event ledger or proof of collector overflow. Preserve the
    # separate annex labels even where spelling or geography is disputed.
    coen = d["official_2017_coen_ravine_name_sweep"]
    names = coen["names"]
    assert coen["row_count"] == len(names) == 20
    assert [n["annex_row"] for n in names] == list(range(1, 21))
    assert len({n["printed_label"] for n in names}) == len(names)
    assert sum(n["reconciliation"].startswith("EXACT_DOCUMENTARY_LABEL_MATCH") for n in names) == coen["existing_exact_documentary_label_match_count"] == 5
    assert sum(n["reconciliation"] == "POSSIBLE_NAME_VARIANT_UNRESOLVED" for n in names) == coen["unresolved_variant_or_abbreviation_count"] == 6
    assert sum(n["reconciliation"] == "UNMATERIALIZED_NAME_LEAD" for n in names) == coen["unmaterialized_new_name_lead_count"] == 9
    assert coen["per_unit_activation_dates"] is None
    assert coen["observed_flow_or_stage_measurements"] is None
    assert coen["report_is_not_per_unit_event_confirmation"] is True
    assert coen["reported_time_difference_is_not_travel_time_or_causality"] is True
    assert coen["no_child_activation_implies_collector_overflow"] is True
    assert coen["no_alias_merge_or_geographic_adjudication"] is True
    assert coen["original_pdf_sha256"] is None
    assert coen["source_text_verified"] is False
    assert coen["documentary_row_count_increment"] == 0
    assert coen["confirmed_unique_hydrologic_unit_count_increment"] == 0
    assert coen["map_publishable"] is False

    # COEN Annex 06 has 15 unresolved/non-exact names, all preserved in
    # the separate lead ledger. Neither a variant nor a name-only row may
    # disappear, be double-counted, or turn into a measured unit event.
    annex_unresolved = {
        row["printed_label"]
        for row in names
        if not row["reconciliation"].startswith("EXACT_DOCUMENTARY_LABEL_MATCH")
    }
    coen_leads = [
        lead for lead in d["official_unmaterialized_name_leads"]
        if lead.get("source_id") == coen["source_id"]
    ]
    lead_labels = [lead["documentary_name"] for lead in coen_leads]
    assert len(lead_labels) == len(set(lead_labels)) == len(annex_unresolved) == 15
    assert set(lead_labels) == annex_unresolved
    for lead in coen_leads:
        assert lead["map_publishable"] is False
        assert lead["verified_event_refs"] == []
        assert lead["flow_or_stage_observation_refs"] == []
        assert lead["outlet_coordinate"] is None
        assert lead["exact_confluence_coordinate"] is None
        assert lead["counted_as_confirmed_unique_hydrologic_unit"] is False
        assert all(
            event["usable_as_confirmed_unit_event"] is False
            for event in lead["unverified_event_leads"]
        )
    # Two separate documentary mentions of Buenos Aires (COEN annex
    # and SENACE road design) cannot establish an outlet, identity or
    # constructed hydraulic connection.
    crossing_buenos_aires = [
        c for c in d["official_road_crossing_design_leads"]["candidates"]
        if c["documentary_label"] == "Buenos Aires"
    ]
    assert len(crossing_buenos_aires) == 1
    assert crossing_buenos_aires[0]["existing_inventory_id"] is None
    assert crossing_buenos_aires[0]["collector_connection_adjudication"] == "UNRESOLVED"
    for row in names:
        assert row["exact_outlet"] is None
        assert row["exact_confluence"] is None
        assert row["verified_unit_event"] is False
        assert row["map_publishable"] is False

    # INDECI/PNUD 2005 is a name-only sweep without original PDF bytes.
    # Preserve nine labels, six new leads and the pre-existing Acopaya
    # entry without claiming hydrologic identity or vector geometry.
    indeci = d["official_2005_indeci_santa_eulalia_name_sweep"]
    labels_2005 = indeci["labels"]
    assert indeci["documentary_label_count"] == len(labels_2005) == 9
    assert len({row["printed_label"] for row in labels_2005}) == 9
    assert sum(row["reconciliation"] == "EXISTING_DOCUMENTARY_ROW_NO_NEW_UNIT"
               for row in labels_2005) == indeci["existing_inventory_label_count"] == 2
    assert sum(row["reconciliation"] == "EXISTING_UNMATERIALIZED_NAME_LEAD_NO_DUPLICATE"
               for row in labels_2005) == indeci["existing_name_lead_count"] == 1
    new_labels = {
        row["printed_label"] for row in labels_2005
        if row["reconciliation"].startswith("NEW_UNMATERIALIZED_NAME_LEAD")
    }
    assert len(new_labels) == indeci["new_name_lead_count"] == 6
    new_leads = [
        lead for lead in d["official_unmaterialized_name_leads"]
        if lead.get("source_id") == indeci["source_id"]
    ]
    assert len(new_leads) == 6
    assert {lead["documentary_name"] for lead in new_leads} == new_labels
    assert any(
        lead["documentary_name"] == "Acopaya"
        and lead["source_id"] == coen["source_id"]
        for lead in d["official_unmaterialized_name_leads"]
    )
    assert indeci["source_text_verified"] is False
    assert indeci["original_pdf_bytes_archived_in_this_contract"] is False
    assert indeci["original_pdf_sha256"] is None
    assert indeci["name_only_evidence_not_vector"] is True
    assert indeci["no_individually_verified_event_dates"] is True
    assert indeci["documentary_bank_descriptions_not_exact_outlets"] is True
    assert indeci["simultaneous_infiernillo_alcula_blockage_is_hypothesis_not_event"] is True
    assert indeci["confirmed_unique_hydrologic_unit_count_increment"] == 0
    assert indeci["documentary_row_count_increment"] == 0
    assert indeci["map_publishable"] is False
    for lead in new_leads:
        assert lead["source_text_verified"] is False
        assert lead["original_pdf_bytes_archived_in_this_contract"] is False
        assert lead["original_pdf_sha256"] is None
        assert lead["map_publishable"] is False
        assert lead["counted_as_confirmed_unique_hydrologic_unit"] is False
        assert lead["outlet_coordinate"] is None
        assert lead["exact_confluence_coordinate"] is None
        assert lead["verified_event_refs"] == []
        assert lead["flow_or_stage_observation_refs"] == []
    vizcacha = next(lead for lead in new_leads
                    if lead["documentary_name"] == "Vizcacha")
    assert vizcacha["possible_existing_inventory_id_unadjudicated"] == (
        "lima_lurigancho_vizcachera"
    )
    assert vizcacha["alias_adjudication"].startswith("UNRESOLVED")
