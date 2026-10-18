"""Fail-closed tests for the Rímac corridor documentary inventory.

Documentary rows are not a count of unique hydrologic catchments.
A source mention, regulatory faja, work or event is not publishable GIS geometry.
"""
import copy
import importlib.util
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

    # Historical context is not a confirmed Cashahuacra event. Keep the
    # 2015-03-23 attribution fail-closed until independently verified.
    cash = next(u for u in d["units"] if u["id"] == "lima_santa_eulalia_cashahuacra")
    assert cash["verified_event_refs"] == []
    leads = [x for x in cash["unverified_event_leads"] if x["date_or_period"] == "2015-03-23"]
    assert len(leads) == 1
    assert leads[0]["source_text_verified"] is False
    assert leads[0]["unit_attribution"] == "HISTORICAL_CONTEXT_REQUIRES_ATTRIBUTION_CHECK"
    assert leads[0]["usable_as_confirmed_unit_event"] is False

    # Quirio historical-table dates remain leads until unit attribution and
    # original-source provenance are independently verified. Calendar dates
    # in a regional table do not establish confirmed local events.
    quirio = next(u for u in d["units"] if u["id"] == "lima_lurigancho_quirio")
    assert quirio["verified_event_refs"] == []
    historical_leads = [
        lead for lead in quirio["unverified_event_leads"]
        if lead["source_id"] == "IGP-IT-001-2023"
    ]
    assert historical_leads
    assert all(
        lead["unit_attribution"] == "REPORT_TABLE_UNVERIFIED_TERRITORIAL_CONTEXT_IN_MAIN"
        and lead["source_text_verified"] is False
        and lead["usable_as_confirmed_unit_event"] is False
        for lead in historical_leads
    )

    # Media Luna's separately documented 2002 debris-flow event is not an
    # IGP station-trigger record and must not be silently reattributed.
    media_luna = next(u for u in d["units"] if u["id"] == "jicamarca_media_luna")
    assert media_luna["verified_event_refs"] == [
        "config/phase2_jicamarca_discovery_v0_1.json#/historical_evidence/0"
    ]

    # IGP station triggers are instrumental observations, not confirmed
    # quebrada events, measured discharge, or collector overflow.
    for unit_id in ("lima_huaycoloro", "jicamarca_rio_seco"):
        unit = next(u for u in d["units"] if u["id"] == unit_id)
        assert unit["verified_event_refs"] == []
        assert unit["rainfall_observation_refs"] == []
        assert unit["flow_or_stage_observation_refs"] == []
        assert unit["station_activation_context_refs"] == [
            "config/phase2_igp2023_jicamarca_station_activation_events_v0_1.json"
        ]
        assert unit["collector_overflow_evidence"] is None
    for unit in d["units"]:
        for ref in unit["verified_event_refs"]:
            assert "phase2_igp2023_jicamarca_station_activation_events" not in str(ref)

    # No documentary row may silently gain a verified event merely because
    # a historical table, station trigger or district report names the area.
    # Media Luna has a separate, explicitly cited 2002 debris-flow contract;
    # adding any other confirmed event requires evidence review and test update.
    for unit in d["units"]:
        if unit["id"] != "jicamarca_media_luna":
            assert unit["verified_event_refs"] == []
        station_refs = set(unit.get("station_activation_context_refs", []))
        for evidence_field in (
            "verified_event_refs",
            "rainfall_observation_refs",
            "flow_or_stage_observation_refs",
        ):
            assert station_refs.isdisjoint(unit[evidence_field])

    # Apply the same fail-closed contract to every documentary event lead,
    # not just Cashahuacra. A district list, station activation or historical
    # table mention cannot silently become a verified per-quebrada event.
    for unit in d["units"]:
        for lead in unit["unverified_event_leads"]:
            assert lead["date_or_period"] and lead["source_id"]
            assert lead["source_text_verified"] is False
            assert lead["usable_as_confirmed_unit_event"] is False
            if "event_ledger_entry_allowed" in lead:
                assert lead["event_ledger_entry_allowed"] is False
            if "event_lead_state" in lead:
                assert lead["event_lead_state"] == "EVENT_LEAD_UNVERIFIED"


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
        # Every documentary variant remains a non-adjudicated label. A
        # shared name or sector mention cannot become a hydrologic alias
        # merely because it appears in the master crosswalk.
        for variant in unit["documentary_variants"]:
            assert variant["label"] and variant["source_id"]
            assert variant["alias_adjudication"] == "PENDING_NOT_MERGED"

        # Event leads must be traceable to a source on this same row;
        # unresolved event context is not independently verified evidence.
        source_ids = {source["source_id"] for source in unit["source_refs"]}
        for lead in unit["unverified_event_leads"]:
            assert lead["source_id"] in source_ids
        for source in unit["source_refs"]:
            assert source["source_id"]
            assert isinstance(source["source_text_verified"], bool)

        # A work, a faja and a mapped exposure are different evidence
        # categories. A repeated institutional source ID may represent
        # separate documents, but only when their URLs are distinct.
        works = unit.get("works_context_refs", [])
        exposure = unit.get("exposure_refs", [])
        assert not set(works).intersection(exposure)
        for refs, accepted_types in (
            (works, {"WORKS"}),
            (exposure, {"FAJA", "CRITICAL_POINT"}),
        ):
            for source_id in set(refs):
                matching = [
                    src for src in unit["source_refs"]
                    if src["source_id"] == source_id
                ]
                multiplicity = refs.count(source_id)
                assert len(matching) >= multiplicity
                assert all(src["evidence_type"] in accepted_types for src in matching)
                if multiplicity > 1:
                    urls = [src.get("source_url") for src in matching]
                    assert all(urls)
                    assert len(set(urls)) >= multiplicity


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
    # Documentary role clues cannot silently adjudicate a shared channel,
    # sector alias, outlet or map geometry, even when an IGP figure names both.
    for group in groups:
        for lead in group.get("role_evidence_leads", []):
            assert lead["source_id"] and lead["source_url"]
            assert lead["printed_page_locators"] and lead["observed_documentary_phrases"]
            assert lead["source_text_verified"] is False
            assert lead["original_pdf_bytes_archived_in_this_contract"] is False
            assert lead["original_pdf_sha256"] is None
            assert lead["adjudication"] == "DOCUMENTARY_ROLE_LEAD_ONLY_NO_ALIAS_OR_GEOMETRY_PROMOTION"
            assert lead["map_publishable"] is False

    corrales = next(g for g in groups if "lima_lurigancho_corrales" in g["inventory_ids"])
    assert corrales["status"] == "PENDING_ADJUDICATION"
    assert set(corrales["inventory_ids"]) == {
        "lima_lurigancho_corrales", "lima_lurigancho_rayos_de_sol"
    }
    assert len(corrales["role_evidence_leads"]) == 1
    role = corrales["role_evidence_leads"][0]
    assert role["source_id"] == "IGP-IT-001-2023"
    assert role["printed_page_locators"] == [50, 66]
    assert role["observed_documentary_phrases"] == [
        "Quebrada Corrales (Rayos del Sol)",
        "Rayos del Sol (Quebrada Corrales)",
    ]
    for unit in d["units"]:
        if unit["id"] in corrales["inventory_ids"]:
            assert unit["map_publishable"] is False
            assert unit["exact_confluence_coordinate"] is None
            assert unit["outlet_coordinate"] is None


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

    # Official SENACE road-chainage excerpts are unverified design leads,
    # not geodetic outlets, built works, measured hydraulic capacity or
    # evidence of a collector overflow. This augments an existing test node
    # so the fixed pytest collection manifest needs no regeneration.
    road = d["official_road_crossing_design_leads"]
    assert road["source_text_verified"] is False
    assert road["original_pdf_bytes_archived_in_this_contract"] is False
    assert road["original_pdf_sha256"] is None
    assert road["road_chainage_is_not_outlet_or_geodetic_coordinate"] is True
    assert road["project_design_is_not_constructed_work_or_measured_hydraulic_capacity"] is True
    assert road["no_alias_or_receiver_chain_adjudication"] is True
    assert road["confirmed_unique_hydrologic_unit_count_increment"] == 0
    assert road["documentary_row_count_increment"] == 0
    assert road["candidates"]
    inventory_ids = {u["id"] for u in d["units"]}
    for crossing in road["candidates"]:
        assert crossing["road_crossing_chainage_km_text"]
        assert crossing["geometry_ref"] is None
        assert crossing["outlet_coordinate"] is None
        assert crossing["exact_confluence_coordinate"] is None
        assert crossing["collector_connection_adjudication"] == "UNRESOLVED"
        assert crossing["observed_event_evidence"] is None
        assert crossing["measured_discharge"] is None
        assert crossing["travel_time_tau"] is None
        assert crossing["capacity_evidence"] is None
        assert crossing["map_publishable"] is False
        if crossing["existing_inventory_id"] is None:
            assert crossing["status"].startswith("NEW_NAME_LEAD_NOT_COUNTED")
        else:
            assert crossing["existing_inventory_id"] in inventory_ids

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


def _dos_barrios_validator():
    spec = importlib.util.spec_from_file_location(
        "irfen_rimac_dos_barrios_validator", ROOT / "scripts/validate_phase2_rimac_dos_barrios_identity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = _dos_barrios_validator()


def test_dos_barrios_is_registered_only_on_archived_verifiable_evidence():
    """Dos Barrios is IDENTITY_ONLY because archived, page-cited quotes name it; nothing hydrologic follows."""
    reg, rimac, audit, manifest = V.load_all()
    assert V.validate(reg, rimac, audit, manifest) == []
    assert V.main() == 0
    unit = next(u for u in rimac["units"] if u["id"] == V.RID)
    assert unit["documentary_label"] == "Dos Barrios" and unit["map_publishable"] is False
    assert {ref["source_id"] for ref in unit["source_refs"]} == {
        "INGEMMET-A6608-2012-LA-RONDA-LOS-CONDORES", "SENAMHI-2020-QDAS-SANTO-DOMINGO-CANTUTA",
        "VILLACORTA-2018-UPM-THESIS-INGEMMET-TE0306",
    }
    assert all(len(ref["archived_sha256"]) == 64 for ref in unit["source_refs"])
    resolved = [r for r in rimac["resolved_name_leads"] if r["requested_name"] == "Dos Barrios"]
    assert len(resolved) == 1 and resolved[0]["historical_sweep_result"] == "NO_SOURCE_FOUND_IN_THIS_SWEEP"
    assert reg["quotes"]["SEN-P3-ADJACENCY"]["page"] == 17 and reg["quotes"]["SEN-P3-ADJACENCY"]["printed_page_label"] == "3"


def test_dos_barrios_registration_fails_without_verifiable_archive_evidence():
    reg, rimac, audit, manifest = V.load_all()
    bad = copy.deepcopy(reg)
    bad["sources"]["SENAMHI-2020-QDAS-SANTO-DOMINGO-CANTUTA"]["sha256"] = "0" * 64
    assert any("sha256" in e or "SHA-256" in e for e in V.validate(bad, rimac, audit, manifest))
    bad = copy.deepcopy(reg)
    bad["quotes"]["SEN-P3-ADJACENCY"]["text"] = "La quebrada Santo Domingo se encuentra contigua a la quebrada Dos Barrios."
    assert any("SEN-P3-ADJACENCY" in e and "verbatim" in e for e in V.validate(bad, rimac, audit, manifest))
    bad = copy.deepcopy(reg)
    for att in bad["candidate"]["identity_basis"]["attestations"]:
        att["quote_ids"] = ["SEN-P3-STUDY-AREA"] if att["source_id"].startswith("SENAMHI") else ["TE-P85-CITATION"]
    assert any("no quote contains" in e for e in V.validate(bad, rimac, audit, manifest))
    bad = copy.deepcopy(reg)
    bad["candidate"]["identity_basis"]["attestations"] = [
        a for a in bad["candidate"]["identity_basis"]["attestations"]
        if bad["sources"][a["source_id"]]["source_class"] != "PRIMARY_INSTITUTIONAL"
    ]
    assert any("primary institutional" in e for e in V.validate(bad, rimac, audit, manifest))
    bad_rimac = copy.deepcopy(rimac)
    next(u for u in bad_rimac["units"] if u["id"] == V.RID)["source_refs"][0]["archived_sha256"] = None
    assert any("archived SHA-256" in e for e in V.validate(reg, bad_rimac, audit, manifest))


def test_dos_barrios_gets_no_location_geometry_confluence_or_event_by_inference():
    reg, rimac, audit, manifest = V.load_all()
    for mutate in (
        lambda r: r["candidate"].__setitem__("district", "Lurigancho-Chosica"),
        lambda r: r["candidate"].__setitem__("receiver_relation", "RIMAC_LEFT_BANK_CONFLUENCE"),
        lambda r: r["candidate"].__setitem__("events_attributed", [{"date": "2012-04-05"}]),
        lambda r: r["candidate"]["historical_period_mentions"][0].__setitem__("usable_as_confirmed_unit_event", True),
        lambda r: r["relations_recorded_not_adopted"][0].__setitem__("status", "SAME_CHANNEL"),
    ):
        bad = copy.deepcopy(reg)
        mutate(bad)
        assert V.validate(bad, rimac, audit, manifest)
    for field, value in (("exact_confluence_coordinate", [314700, 8679000]), ("reproducible_geometry_ref", "x.geojson"),
                         ("map_publishable", True), ("district", "Ricardo Palma")):
        bad_rimac = copy.deepcopy(rimac)
        next(u for u in bad_rimac["units"] if u["id"] == V.RID)[field] = value
        assert V.validate(reg, bad_rimac, audit, manifest), field
    bad_audit = copy.deepcopy(audit)
    row = next(r for r in bad_audit["candidates"] if r["inventory_id"] == V.RID)
    row["state_flags"] = ["EVENT_EVIDENCE"]
    assert V.validate(reg, rimac, bad_audit, manifest)


def test_dos_barrios_is_not_left_both_as_lead_and_unit_or_merged_with_dos_amigos():
    reg, rimac, audit, manifest = V.load_all()
    bad_rimac = copy.deepcopy(rimac)
    bad_rimac["requested_unresolved_name_leads"].append({"requested_name": "Dos Barrios", "result": "NO_SOURCE_FOUND_IN_THIS_SWEEP", "note": "x"})
    assert any("unresolved lead" in e for e in V.validate(reg, bad_rimac, audit, manifest))
    bad_rimac = copy.deepcopy(rimac)
    group = next(g for g in bad_rimac["pending_identity_groups"] if V.RID in g["inventory_ids"])
    group["status"] = "MERGED"
    assert any("pending" in e for e in V.validate(reg, bad_rimac, audit, manifest))
    assert not any(u["documentary_label"] == "Pablo Patrón/Dos Amigos" and u["id"] == V.RID for u in rimac["units"])


def test_a6608_slash_heading_is_not_a_channel_equivalence():
    """INGEMMET A6608 §5.6 'Quebrada Dos Barrios / Pablo Patrón': Pablo Patrón is a sector on the fan, not an alias."""
    reg, rimac, audit, manifest = V.load_all()
    assert reg["quotes"]["A6-P30-HEADING"]["text"].startswith("5.6 QUEBRADA DOS BARRIOS /PABLO PATRÓN")
    assert reg["sources"]["INGEMMET-A6608-2012-LA-RONDA-LOS-CONDORES"]["sha256"] == (
        "b710247572a7a83efed53be0f0f565cc4971eb542f43f2881cbefc7bba0b5927"
    )
    statuses = {tuple(r["labels"]): r["status"] for r in reg["relations_recorded_not_adopted"]}
    assert statuses[("Dos Barrios", "Pablo Patrón (sector)")] == "PABLO_PATRON_IS_A_SECTOR_ON_THE_LOWER_FAN_PER_A6608"
    assert statuses[("Dos Barrios", "Pablo Patrón/Dos Amigos")] == "UNRESOLVED"
    assert statuses[("Dos Barrios", "Mariscal Castilla")] == "UNRESOLVED"
    for mutate in (
        lambda r: next(x for x in r["relations_recorded_not_adopted"] if "Pablo Patrón (sector)" in x["labels"]).__setitem__("channel_equivalence", "SAME_CHANNEL"),
        lambda r: next(x for x in r["relations_recorded_not_adopted"] if "Pablo Patrón/Dos Amigos" in x["labels"]).__setitem__("status", "SAME_CHANNEL"),
        lambda r: next(x for x in r["relations_recorded_not_adopted"] if "Mariscal Castilla" in x["labels"]).__setitem__("status", "ALIAS_CONFIRMED"),
        lambda r: next(x for x in r["relations_recorded_not_adopted"] if "Pablo Patrón (sector)" in x["labels"]).__setitem__("quote_ids", ["A6-P30-HEADING"]),
        lambda r: r["candidate"]["identity_basis"].__setitem__(
            "attestations", [a for a in r["candidate"]["identity_basis"]["attestations"] if not a["source_id"].startswith("INGEMMET-A6608")]),
        lambda r: r["candidate"]["historical_period_mentions"][0].__setitem__("event_lead_eligible", True),
    ):
        bad = copy.deepcopy(reg)
        mutate(bad)
        assert V.validate(bad, rimac, audit, manifest)
    bad_rimac = copy.deepcopy(rimac)
    next(u for u in bad_rimac["units"] if u["id"] == V.RID)["documentary_variants"] = [{"label": "Pablo Patrón"}]
    assert any("variant" in e for e in V.validate(reg, bad_rimac, audit, manifest))
    groups = [g for g in rimac["pending_identity_groups"] if V.RID in g["inventory_ids"]]
    assert len(groups) == 2 and all(g["status"] == "PENDING_ADJUDICATION" for g in groups)


def test_a6608_event_lead_is_unverified_and_never_promoted_or_ledgered():
    """QA-authorised: 2012-04-05 is an EVENT_LEAD_UNVERIFIED from A6608 §5.6, not a validated or operational event."""
    reg, rimac, audit, manifest = V.load_all()
    lead = reg["candidate"]["event_leads"][0]
    assert (lead["event_date"], lead["state"], lead["source_text_verified"]) == ("2012-04-05", "EVENT_LEAD_UNVERIFIED", False)
    assert reg["candidate"]["classification"]["identity_state"] == "IDENTITY_ONLY"
    row = next(r for r in audit["candidates"] if r["inventory_id"] == V.RID)
    assert row["state_flags"] == ["EVENT_LEAD_UNVERIFIED"] and row["verified_event_dates"] == []
    assert row["event_lead_dates_unverified"] == ["2012-04-05"] and row["map_eligible"] is False
    for mutate in (
        lambda r: r["candidate"]["event_leads"][0].__setitem__("source_text_verified", True),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("verification", {"locator": "p. 30"}),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("event_ledger_entry_allowed", True),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("promotion_to_event_evidence_allowed", True),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("usable_as_confirmed_unit_event", True),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("event_date", "2011-10-01"),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("date_warning", ""),
        lambda r: r["candidate"]["event_leads"][0].__setitem__("source_id", "SENAMHI-2020-QDAS-SANTO-DOMINGO-CANTUTA"),
        lambda r: r["candidate"]["event_leads"].append(dict(r["candidate"]["event_leads"][0], event_date="2015-03-23")),
    ):
        bad = copy.deepcopy(reg)
        mutate(bad)
        assert V.validate(bad, rimac, audit, manifest)
    for mutate in (
        lambda r: r.__setitem__("state_flags", ["EVENT_EVIDENCE"]),
        lambda r: r.__setitem__("verified_event_dates", ["2012-04-05"]),
        lambda r: next(i for i in r["evidence"] if i["evidence_type"] == "EVENT").__setitem__("source_text_verified", True),
        lambda r: r.__setitem__("map_eligible", True),
    ):
        bad_audit = copy.deepcopy(audit)
        mutate(next(x for x in bad_audit["candidates"] if x["inventory_id"] == V.RID))
        assert V.validate(reg, rimac, bad_audit, manifest)
    ledger = json.loads((ROOT / "config/historical_events.json").read_text(encoding="utf-8"))
    assert "dos barrios" not in json.dumps(ledger, ensure_ascii=False).lower()
