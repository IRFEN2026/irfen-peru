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

    # An official Esri /find request that completed with zero extracted IDs
    # is a parser/source diagnostic, NOT evidence of hydrologic absence.
    # Freeze that distinction without adding a new pytest collection node.
    probe_refs = [
        (unit["id"], source)
        for unit in d["units"]
        for source in unit["source_refs"]
        if source["source_id"] == "MINAM-MAPSERVER36-FEATUREID-PROBE-2026-10-14"
    ]
    assert len(probe_refs) == 1
    unit_id, probe = probe_refs[0]
    assert unit_id == "lima_huaycoloro"
    assert probe["effective_layer"] == "ServicioActivacionQuebrada/MapServer/36"
    assert probe["query_completed"] is True
    assert probe["find_requests_status"] == "SUCCESS"
    assert probe["huaycoloro_candidate_count"] == 0
    assert probe["rimac_candidate_count"] == 0
    assert probe["zero_candidates_inferred_as_hydrologic_absence"] is False
    assert probe["find_feature_ids_promoted_to_hydrologic_identity"] is False
    assert probe["source_text_verified"] is False
    assert probe["original_source_bytes_archived_in_this_contract"] is False
    assert probe["map_publishable"] is False
    for key in ("artifact_zip_sha256", "raw_payload_sha256", "canonical_payload_sha256"):
        digest = probe[key]
        assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest)


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
    # This isolated replay does not include the primary-source PDF bytes from
    # the separate, unmerged archive PR. A declared SHA-256 is a provenance
    # pointer, not proof that this branch independently verified those bytes.
    # Keep all external citations documentary-only until source recovery and
    # explicit independent QA. Internal config contracts are not PDF evidence.
    for unit in units:
        for source in unit["source_refs"]:
            if source["source_id"].startswith("config/"):
                continue
            assert source["source_text_verified"] is False, unit["id"]
            assert source.get("original_pdf_bytes_archived_in_this_contract") is not True, unit["id"]
            if source.get("original_pdf_sha256") is not None:
                assert source["original_pdf_bytes_archived_in_this_contract"] is False, unit["id"]
                assert source["map_publishable"] is False, unit["id"]
    assert d["counts"]["national_audit_corridor_documentary_rows"] + (
        d["counts"]["jicamarca_additional_documentary_rows"]
    ) == len(units)
    # Official name leads are retained for discovery but never inflate the
    # count of adjudicated catchments or documentary inventory rows.
    # Name-only leads are retained without silently acquiring event, flow,
    # receiver, geometry or routing evidence. Missing GIS is not absence.
    leads = d["official_unmaterialized_name_leads"]
    assert len({lead["documentary_name"] for lead in leads}) == len(leads)
    # ANA's plan supplies eight separate *name leads*, not eight validated
    # catchments. Freeze their exact documentary labels in this replay so
    # later inventory revisions cannot silently drop them or merge numbered
    # Condores labels into the existing Los Condores unit.
    ana_plan_labels = {
        "Huascata", "Panorama", "Caraponguillo", "Los Cóndores 2",
        "Cóndores 1", "Santa Inés 1", "Ñaña", "La Laguna",
    }
    ana_plan_leads = [
        lead for lead in leads
        if lead.get("source_title") == (
            "Plan de intervenciones — identificación de quebradas con población vulnerable"
        )
    ]
    assert {lead["documentary_name"] for lead in ana_plan_leads} == ana_plan_labels
    assert len(ana_plan_leads) == len(ana_plan_labels) == 8
    for lead in ana_plan_leads:
        assert lead["source_text_verified"] is False
        assert lead["original_pdf_sha256"] is None
        assert lead["counted_as_confirmed_unique_hydrologic_unit"] is False
        assert lead["receiver_chain_adjudicated"] is False
        assert lead["map_publishable"] is False
    for name in ("Los Cóndores 2", "Cóndores 1"):
        candidate = next(x for x in ana_plan_leads if x["documentary_name"] == name)
        assert candidate["possible_existing_inventory_id_unadjudicated"] == (
            "lima_chaclacayo_los_condores"
        )
        assert candidate["alias_adjudication"].startswith("UNRESOLVED")
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
    # ANA's Ricardo Palma field-verification news names four candidate
    # ravines; it is neither an activation ledger nor evidence that the
    # announced barriers/diques were built or have measured capacity.
    # In particular, Velasco must not be merged with COEN's Juan Velasco.
    ana_ricardo_palma_names = [
        lead for lead in leads
        if lead.get("source_title") == (
            "Huarochirí: ANA intervendrá con barreras dinámicas y diques en quebradas "
            "Cupiche y La Ronda en distrito Ricardo Palma"
        )
    ]
    assert {lead["documentary_name"] for lead in ana_ricardo_palma_names} == {
        "Montalvo", "Velasco", "La Pascana", "Sol y Campo"
    }
    assert len(ana_ricardo_palma_names) == 4
    for lead in ana_ricardo_palma_names:
        assert lead["source_text_verified"] is False
        assert lead["original_web_text_sha256"] is None
        assert lead["verified_event_refs"] == []
        assert lead["receiver_chain_adjudicated"] is False
        assert lead["map_publishable"] is False
    velasco = next(lead for lead in ana_ricardo_palma_names
                   if lead["documentary_name"] == "Velasco")
    assert velasco["alias_adjudication"] == "UNRESOLVED_NO_EQUIVALENCE_TO_COEN_JUAN_VELASCO"

    # ANA's 6-Nov-2023 press note is an announcement, not evidence of
    # completed protection works, channel identity or observed activation.
    # Keep its two *printed leads* separate from the earlier Santa Ines 1
    # and from any inferred four-catchment split of the grouped label.
    announcement_title = (
        "Ante peligro de huaicos, ANA instalará barreras dinámicas y "
        "diques de contención en 21 quebradas de Lima"
    )
    announcement_leads = [
        lead for lead in leads if lead.get("source_title") == announcement_title
    ]
    assert len(announcement_leads) == 2
    assert {lead["documentary_name"] for lead in announcement_leads} == {
        "Santa Inés 2", "MZ-G, X5-X6, U3 y P-P1"
    }
    assert not any(
        u["documentary_label"] in {"Santa Inés 1", "Santa Inés 2"}
        for u in units
    )
    santa_ines_2 = next(
        lead for lead in announcement_leads
        if lead["documentary_name"] == "Santa Inés 2"
    )
    assert santa_ines_2["alias_adjudication"] == (
        "UNRESOLVED_NOT_MERGED_WITH_SANTA_INES_1"
    )
    grouped = next(
        lead for lead in announcement_leads
        if lead["documentary_name"] == "MZ-G, X5-X6, U3 y P-P1"
    )
    assert grouped["alias_adjudication"] == (
        "UNRESOLVED_GROUPED_PROJECT_LABEL_NOT_FOUR_CONFIRMED_HYDROLOGIC_UNITS"
    )
    assert grouped["documentary_label_as_printed"] == grouped["documentary_name"]
    assert grouped["related_procurement_resolution_url"].endswith(
        "/5878759-0303-2024-ana"
    )
    for lead in announcement_leads:
        assert lead["source_published_date"] == "2023-11-06"
        assert lead["evidence_role"] == (
            "ANNOUNCED_INTERVENTION_AND_DOCUMENTARY_NAME_ONLY_NOT_COMPLETED_WORK_OR_HYDROLOGIC_EVENT"
        )
        assert lead["source_capture_status"] == (
            "OFFICIAL_WEB_TEXT_READ_ORIGINAL_PAGE_BYTES_NOT_FROZEN"
        )
        assert lead["original_web_text_sha256"] is None
        assert lead["source_text_verified"] is False
        assert lead["verified_event_refs"] == []
        assert lead["flow_or_stage_observation_refs"] == []
        assert lead["receiver_chain_adjudicated"] is False
        assert lead["collector_capacity"] is None
        assert lead["collector_overflow_evidence"] is None
        assert lead["map_publishable"] is False
        assert lead["counted_as_confirmed_unique_hydrologic_unit"] is False

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
        # Only the two frozen IGP line-context components may reference a
    # reproducible line contract. A line reference is not a catchment
    # polygon, geodetic outlet, validated junction or publishable layer.
    frozen_line_ids = {
        "jicamarca_canto_grande_upper_branch",
        "jicamarca_media_luna",
    }
    with_line = {
        u["id"] for u in d["units"]
        if u["reproducible_geometry_ref"] is not None
    }
    assert with_line == frozen_line_ids
    for u in d["units"]:
        if u["id"] in frozen_line_ids:
            assert u["reproducible_geometry_ref"] == (
                "config/phase2_jicamarca_igp_channel_line_freeze_v0_1.json"
            )
            assert u["channel_or_catchment_geometry"] == (
                "OFFICIAL_IGP_LINE_CONTEXT_NOT_CATCHMENT"
            )
            assert u["identity_adjudication"] == (
                "SEPARATE_DOCUMENTARY_COMPONENT_NO_EXACT_BOUNDARY"
            )
        else:
            assert u["reproducible_geometry_ref"] is None, u["id"]
        assert u["map_publishable"] is False, u["id"]
        assert u["exact_confluence_coordinate"] is None, u["id"]
        assert u["outlet_coordinate"] is None, u["id"]
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
    # Conflicting district mentions remain separate documentary leads.
    # The inherited audit location is not independently adjudicated;
    # neither archived report title establishes a geodetic channel location.
    locations = ronda["administrative_location_leads"]
    assert any(
        row.get("kind") == "LEGACY_NATIONAL_AUDIT_CROSSWALK"
        and row.get("district") == "Lurigancho-Chosica"
        and row.get("adjudication") == "UNVERIFIED_INHERITED_ROW_LABEL_NOT_EXACT_CHANNEL_LOCATION"
        for row in locations
    )
    assert any(
        row.get("source_id") == "IGP-2020-SIGRID-13867"
        and row.get("district_lead") == "Ricardo Palma"
        and row.get("source_text_verified") is False
        and row.get("adjudication") == "LOCATION_LEAD_ONLY_NOT_IDENTITY_OR_CHANNEL_GEOMETRY"
        for row in locations
    )
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


    # ANA dated works and border reports must remain documentary evidence,
    # not hydraulic measurements or an adjudicated La Ronda location.
    d = _inventory()
    ronda = next(u for u in d["units"] if u["id"] == "lima_lurigancho_la_ronda")
    by_source = {row["source_id"]: row for row in ronda["source_refs"]}
    expected = {
        "ANA-GOBPE-2025-01-06-LA-RONDA-DESCOLMATACION": (
            "2025-01-06",
            "DATED_OFFICIAL_WORKS_STATUS_REPORT_NOT_HYDROLOGIC_EVENT",
            "ANA_REPORTED_CRITICAL_POINT_DESCOLMATATION_COMPLETED_AS_OF_2025_01_06_NOT_CURRENT_CONDITION",
        ),
        "ANA-GOBPE-2026-03-04-LA-RONDA-DIQUES-BOUNDARY": (
            "2026-03-04",
            "DATED_OFFICIAL_WORKS_STATUS_AND_ADMINISTRATIVE_BOUNDARY_REPORT_NOT_HYDROLOGIC_EVENT",
            "ANA_REPORTED_FIRST_DIKE_COMPLETED_SECOND_UNDER_EXECUTION_AS_OF_2026_03_04_NOT_CURRENT_CONDITION",
        ),
    }
    assert set(expected).issubset(by_source)
    assert set(expected).issubset(set(ronda["works_context_refs"]))
    for source_id, (published, role, works_state) in expected.items():
        row = by_source[source_id]
        assert row["source_published_date"] == published
        assert row["evidence_type"] == role
        assert row["reported_work_status"] == works_state
        assert row["source_capture_status"] == (
            "OFFICIAL_WEB_SEARCH_EXCERPT_READ_ORIGINAL_PAGE_BYTES_NOT_FROZEN"
        )
        assert row["source_text_verified"] is False
        assert row["original_web_text_sha256"] is None
        assert row["original_source_bytes_archived_in_this_contract"] is False
        assert row["measured_discharge"] is None
        assert row["collector_capacity"] is None
        assert row["verified_event"] is False
        assert row["map_publishable"] is False

    border = by_source["ANA-GOBPE-2026-03-04-LA-RONDA-DIQUES-BOUNDARY"]
    assert border["reported_location_context"] == (
        "Lurigancho-Chosica (límite con Ricardo Palma)"
    )
    border_leads = [
        row for row in ronda["administrative_location_leads"]
        if row.get("source_id") == border["source_id"]
    ]
    assert len(border_leads) == 1
    assert border_leads[0]["adjudication"] == (
        "BORDER_CONTEXT_ONLY_NO_EXACT_CHANNEL_OR_DISTRICT_ADJUDICATION"
    )
    assert border_leads[0]["source_text_verified"] is False
    assert border_leads[0]["original_web_text_sha256"] is None
    assert ronda["district"] is None
    assert ronda["province"] is None
    assert ronda["administrative_assignment"] == (
        "UNRESOLVED_CONFLICTING_DOCUMENTARY_LOCATIONS"
    )
    assert ronda["receiver_relation"] == "UNKNOWN_NOT_ASSUMED"
    assert ronda["verified_event_refs"] == []
    assert ronda["flow_or_stage_observation_refs"] == []
    assert ronda["reproducible_geometry_ref"] is None
    assert ronda["outlet_coordinate"] is None
    assert ronda["exact_confluence_coordinate"] is None
    assert ronda["travel_time_tau"] is None
    assert ronda["collector_capacity"] is None
    assert ronda["collector_overflow_evidence"] is None
    assert ronda["map_publishable"] is False


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

    # Closed-world gate for this documentary snapshot: an added unit or
    # unreviewed historical lead must not silently gain verified-event status.
    # Media Luna 2002 is a named historical reference, not measured flow or
    # evidence of a downstream Rímac collector overflow.
    verified_by_unit = {
        unit["id"]: unit["verified_event_refs"]
        for unit in d["units"] if unit["verified_event_refs"]
    }
    assert verified_by_unit == {
        "jicamarca_media_luna": [
            "config/phase2_jicamarca_discovery_v0_1.json#/historical_evidence/0"
        ]
    }

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

    # ANA 2025 regulatory faja catalog entries are documentary receiver
    # claims, not geodetically validated outlets or channel geometries.
    # Infiernillo's 2005 homonym must not silently become a merged unit.
    ana_2025 = d["official_2025_ana_santa_eulalia_faja_name_leads"]
    assert ana_2025["source_text_verified"] is False
    assert ana_2025["original_resolution_pdf_bytes_archived_in_this_contract"] is False
    assert ana_2025["original_pdf_sha256"] is None
    assert ana_2025["documentary_row_count_increment"] == 0
    assert ana_2025["confirmed_unique_hydrologic_unit_count_increment"] == 0
    assert ana_2025["receiver_chain_adjudicated"] is False
    assert ana_2025["exact_outlet"] is None
    assert ana_2025["exact_confluence"] is None
    assert ana_2025["travel_time_tau"] is None
    assert ana_2025["discharge_q_i"] is None
    assert ana_2025["collector_capacity"] is None
    assert ana_2025["collector_overflow_evidence"] is None
    assert ana_2025["map_publishable"] is False
    assert {"Infiernillo", "San Juan"} <= {
        row["documentary_label"] for row in ana_2025["records"]
    }
    for row in ana_2025["records"]:
        assert row["identity_relation_to_prior_lead"] == "PENDING_HOMONYM_NOT_MERGED"
        assert row["receiver_adjudication"] == (
            "DOCUMENTARY_CLAIM_ONLY_NOT_GEODETICALLY_VERIFIED"
        )
        assert row["outlet_coordinate"] is None
        assert row["exact_confluence_coordinate"] is None
        assert row["channel_geometry"] is None
        assert row["catchment_geometry"] is None
        assert row["verified_event_refs"] == []
        assert row["flow_or_stage_observation_refs"] == []
        assert row["map_publishable"] is False

    # ANA RD 1226-2025 is regulatory/inspection evidence, not a vector
    # outlet, a proven 2023 Montalvo alias, measured capacity or a huaico.
    # Its own Paihua/San Pedro-Montalvo discrepancy must remain visible.
    montalvo_leads = [
        lead for lead in d["official_unmaterialized_name_leads"]
        if lead["documentary_name"] == "Montalvo"
    ]
    assert len(montalvo_leads) == 1
    montalvo = montalvo_leads[0]
    assert montalvo["alias_adjudication"].startswith("UNRESOLVED")
    assert montalvo["verified_event_refs"] == []
    assert montalvo["map_publishable"] is False
    regulatory = montalvo["additional_official_2025_regulatory_receiver_context"]
    assert regulatory["source_document"] == "Resolución Directoral N.° 1226-2025-ANA-AAA.CF"
    assert regulatory["named_watercourse_in_resolution"] == "Quebrada San Pedro – Montalvo"
    assert regulatory["relation_to_2023_montalvo_name_lead"] == (
        "UNRESOLVED_NO_HYDROLOGIC_ALIAS_ADJUDICATION"
    )
    assert "Paihua" in regulatory["source_internal_name_discrepancy"]
    assert regulatory["outlet_field_observation_date"] == "2025-09-05"
    assert regulatory["outlet_observation_is_not_current_hydraulic_measurement"] is True
    assert regulatory["regulatory_faja_length_km"] == 2.74
    assert regulatory["regulatory_faja_boundary_marker_count"] == 61
    assert regulatory["boundary_markers_are_not_reproducible_channel_geometry"] is True
    assert regulatory["original_pdf_bytes_archived_in_this_contract"] is False
    assert regulatory["original_pdf_sha256"] is None
    assert regulatory["source_text_verified"] is False
    assert regulatory["receiver_chain_adjudicated"] is False
    assert regulatory["work_or_design_not_capacity_or_event"] is True
    for field in (
        "exact_outlet_coordinate", "exact_confluence_coordinate",
        "catchment_geometry", "channel_geometry", "measured_discharge",
        "travel_time_tau", "collector_capacity", "collector_overflow_evidence",
    ):
        assert regulatory[field] is None, field
    assert regulatory["map_publishable"] is False
    assert regulatory["documentary_row_count_increment"] == 0
    assert regulatory["confirmed_unique_hydrologic_unit_count_increment"] == 0

    # ANIN 2026 design scope must remain distinct from works, observed
    # capacity, unique ravine counts and downstream collector overflow.
    # Append to an existing test to avoid altering the frozen pytest manifest.
    anin = d["official_2026_anin_rimac_design_status"]
    source_id = "ANIN-GOBPE-2026-02-27-RIMAC-23-QUEBRADAS-DESIGN"
    assert anin["source_id"] == source_id
    assert anin["publication_date"] == "2026-02-27"
    assert anin["source_text_verified"] is False
    assert anin["original_source_bytes_archived_in_this_contract"] is False
    assert anin["original_web_text_sha256"] is None
    assert anin["source_semantics"] == (
        "SEPARATE_RIVER_AND_RAVINE_PROJECT_DESIGN_SCOPES_NOT_AS_BUILT_NOT_MEASURED_HYDRAULICS"
    )
    river = anin["rimac_river_project"]
    assert river["reported_design_reach_count"] == 10
    assert river["reported_approximate_scope_length_km"] == 63.5
    assert river["exact_reach_geometries"] is None
    assert river["observed_overflow_reaches"] is None
    assert river["measured_hydraulic_capacity"] is None
    assert river["adjudication"] == "DESIGN_EXTENT_ONLY_NOT_OVERFLOW_REACH_GEOMETRY"
    ravines = anin["ravine_protection_project"]
    assert ravines["reported_design_scope_ravine_count"] == 23
    assert ravines["complete_named_list_available"] is False
    assert ravines["scope_count_is_confirmed_unique_catchments"] is False
    assert ravines["works_completed_inferred"] is False
    assert ravines["exact_outlets"] is None
    assert ravines["measured_capacity"] is None
    assert len(ravines["named_examples"]) == 5
    expected_labels = {
        "Quirio": "lima_lurigancho_quirio",
        "Pedregal": "lima_lurigancho_pedregal_san_antonio",
        "Cusipata": "lima_chaclacayo_cusipata",
        "Huascarán": "lima_chaclacayo_huascaran",
        "Cóndores": "lima_chaclacayo_los_condores",
    }
    assert {
        example["documentary_label"]: example["inventory_id"]
        for example in ravines["named_examples"]
    } == expected_labels
    by_id = {unit["id"]: unit for unit in d["units"]}
    for example in ravines["named_examples"]:
        unit = by_id[example["inventory_id"]]
        source = [s for s in unit["source_refs"] if s["source_id"] == source_id]
        assert len(source) == 1
        assert source_id in unit["works_context_refs"]
        assert source[0]["evidence_type"] == "OFFICIAL_DESIGN_SCOPE_NOT_AS_BUILT"
        assert source[0]["relation_to_inventory_label"] == example["relation_to_inventory_label"]
        assert source[0]["source_text_verified"] is False
        assert source[0]["original_web_text_sha256"] is None
        assert source[0]["map_publishable"] is False
        assert unit["outlet_coordinate"] is None
        assert unit["exact_confluence_coordinate"] is None
        assert unit["map_publishable"] is False
    cond = next(e for e in ravines["named_examples"] if e["documentary_label"] == "Cóndores")
    assert cond["relation_to_inventory_label"] == "POSSIBLE_VARIANT_NOT_ALIAS_ADJUDICATED"
    assert anin["identity_adjudicated"] is False
    assert anin["cross_project_receiver_edges_adjudicated"] is False
    assert anin["documentary_row_count_increment"] == 0
    assert anin["confirmed_unique_hydrologic_unit_count_increment"] == 0
    assert anin["collector_overflow_evidence"] is None
    assert anin["decision_thresholds"] is None
    assert anin["hydraulic_factors"] is None
    assert anin["map_publishable"] is False
