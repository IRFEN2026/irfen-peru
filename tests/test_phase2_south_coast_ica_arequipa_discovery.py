import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_south_coast_ica_arequipa_discovery_v0_1.json"
COMPLETENESS = ROOT / "config/phase2_south_coast_ica_arequipa_hydrographic_completeness_v0_1.json"
EVENTS_2019 = ROOT / "config/phase2_ica_2019_named_events_v0_1.json"
ADJUDICATION = ROOT / "config/phase2_south_coast_ica_arequipa_pytest_adjudication_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

EXPECTED_BASINS = {
    "ica_san_juan_matagente": "137532",
    "ica_topara": "137534",
    "ica_pisco": "13752",
    "ica_ica": "1374",
    "ica_rio_grande_palpa_nasca": "1372",
    "arequipa_pescadores_caraveli": "13712",
    "arequipa_atico": "13714",
    "arequipa_chaparra": "137154",
    "arequipa_chala": "137156",
    "arequipa_yauca": "13716",
    "arequipa_acari": "13718",
    "arequipa_ocona": "136",
    "arequipa_camana_majes_colca": "134",
    "arequipa_quilca_vitor_chili": "132",
    "arequipa_tambo": "1318",
    # Added by the hydrographic-completeness addendum (commit e9278551), after this
    # expectation was last written (30d25ce1). Both are official ANA units; see
    # config/phase2_south_coast_ica_arequipa_pytest_adjudication_v0_1.json (F1).
    "arequipa_choclon": "137152",
    "arequipa_honda": "137158",
}

# Parents that entered the inventory through the completeness addendum and therefore
# must stay traceable to it (provenance guard, not just a count).
ADDENDUM_PARENTS = {"arequipa_choclon": "137152", "arequipa_honda": "137158"}

UNNAMED = "TERRITORIAL_EVENT_PENDING_LOCAL_GEOMETRY"
MULTI_NAMED = "NAMED_CHILDREN_CONFIRMED_TOPOLOGY_PARTIAL"


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def systems(cfg):
    return {x["discovery_id"]: x for x in cfg["local_discovery_systems"]}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def all_children(cfg):
    return [c for s in cfg["local_discovery_systems"] for c in s.get("children", [])]


def test_global_safety_contract_is_fail_closed():
    cfg = load()
    for key, value in SAFE.items():
        assert cfg[key] == value

    rules = cfg["global_rules"]
    assert rules["parent_is_context_only"] is True
    assert rules["child_activation_does_not_activate_parent"] is True
    assert rules["no_synthetic_union_geometry"] is True
    assert rules["no_approximate_points"] is True
    assert rules["territorial_event_without_named_ravine_cannot_create_child_geometry"] is True
    assert rules["critical_point_is_not_event"] is True
    assert rules["intervention_is_not_event"] is True
    assert rules["work_or_design_is_not_historical_capacity"] is True
    assert rules["marginal_strip_is_not_event_footprint"] is True
    assert rules["absence_of_report_is_not_negative_control"] is True
    assert rules["threshold_transfer_between_basins_forbidden"] is True
    assert rules["tributary_activation_does_not_imply_receiver_overflow"] is True
    assert rules["same_name_receiver_must_not_be_conflated_with_official_basin"] is True


def test_official_south_coast_parent_codes_are_explicit_and_non_activatable():
    cfg = load()
    basins = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    assert set(basins) == set(EXPECTED_BASINS)
    for basin_id, code in EXPECTED_BASINS.items():
        row = basins[basin_id]
        assert row["official_unit_code"] == code
        assert row["entity_role"] == "OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
        assert row["identity_status"] == "OFFICIAL_ANA_UNIT_CONFIRMED"
        assert row["parent_geometry_asset"] is None
        assert row["parent_map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None
    codes = [x["official_unit_code"] for x in cfg["official_basin_hierarchy"]]
    assert len(codes) == len(set(codes))
    assert cfg["summary"]["official_parent_basins_registered"] == len(basins) == len(EXPECTED_BASINS)


def test_every_local_child_is_withheld_until_geometry_is_reproducible():
    cfg = load()
    children = all_children(cfg)
    assert len(children) == 23
    assert cfg["summary"]["named_local_children_registered"] == 23
    assert cfg["summary"]["map_publishable_children"] == 0
    assert cfg["summary"]["new_operational_zones"] == 0
    for child in children:
        assert child["geometry_asset"] is None
        assert child["map_publishable"] is False
        assert child["activation_gate"] == "BLOCKED"
        assert child["decision_thresholds"] is None
        assert child["hydraulic_factors"] is None

    policy = cfg["map_policy"]
    assert policy["children"] == "PUBLISH_ONLY_WITH_REPRODUCIBLE_GEOMETRY"
    assert policy["missing_geometry_is_not_drawn"] is True
    assert policy["risk_colours_forbidden"] is True
    assert policy["alert_semantics_forbidden"] is True


def test_cansas_is_bound_to_ica_basin_but_rpas_and_faja_are_not_promoted():
    cfg = load()
    sys = systems(cfg)["ica_ica_local_ravines"]
    assert sys["parent_basin_id"] == "ica_ica"
    children = {x["child_id"]: x for x in sys["children"]}
    cansas = children["ica_cansas"]
    assert cansas["evidence_state"] == "IMPACT_CONFIRMED"
    assert cansas["geometry_status"] == "OFFICIAL_RPAS_AND_REGULATORY_GEOMETRY_AVAILABLE_NOT_FROZEN"
    assert cansas["geometry_asset"] is None
    assert cansas["map_publishable"] is False
    note = cansas["event_attribution_note"].lower()
    assert "not event footprints" in note
    assert "not" in note and "hydraulic capacity" in note

    source = next(x for x in cfg["source_catalog"] if x["source_id"] == "ANA-CANSAS-FAJA-2018")
    forbidden = source["forbidden_use"].lower()
    assert "not an observed event footprint" in forbidden
    assert "historical capacity" in forbidden


def test_pisco_local_rio_grande_is_not_conflated_with_ana_cuenca_grande():
    cfg = load()
    sys = systems(cfg)["ica_pisco_local_ravines"]
    assert sys["parent_basin_id"] == "ica_pisco"
    # The Huancano event stays unnamed and unbound: the two children registered in this
    # system are ANA critical-point identities (see the Quitasol/Paracas tests below),
    # not the unnamed quebrada of this event and not the locally named Río Grande.
    assert {x["child_id"] for x in sys["children"]} == {"ica_quitasol", "ica_paracas"}
    assert len(sys["territorial_events"]) == 1
    ev = sys["territorial_events"][0]
    assert ev["event_id"] == "ica_huancano_2026_02_20"
    assert ev["named_child"] is None
    assert not ev.get("named_children")
    assert ev["hydrologic_assignment_status"] == UNNAMED
    for child in sys["children"]:
        assert not set(child["source_ids"]) & set(ev["source_ids"])
        assert "grande" not in child["name"].lower()
    assert "Río Grande" in ev["receiver_reference"]
    guard = ev["do_not_infer"]
    assert "ANA Cuenca Grande UH 1372" in guard

    grande = next(x for x in cfg["official_basin_hierarchy"] if x["discovery_id"] == "ica_rio_grande_palpa_nasca")
    assert grande["official_unit_code"] == "1372"


def test_yauca_del_rosario_event_is_attributed_only_to_named_children():
    cfg = load()
    sys = systems(cfg)["ica_rio_grande_local_ravines"]
    children = {x["child_id"]: x for x in sys["children"]}
    assert set(children) == {"ica_san_jose_de_curis", "ica_san_isidro_de_macchanga"}
    assert all(x["evidence_state"] == "IMPACT_CONFIRMED" for x in children.values())
    assert all("RIO_CHICO_AND_RIO_GRANDE" in x["outlet_status"] for x in children.values())
    assert all(x["outlet"] is None for x in children.values())


def test_arequipa_metropolitan_torrenteras_are_independent_and_unmapped():
    cfg = load()
    sys = systems(cfg)["arequipa_metropolitana_torrenteras"]
    assert sys["parent_basin_id"] == "arequipa_quilca_vitor_chili"
    children = {x["child_id"]: x for x in sys["children"]}
    expected_2026 = {
        "arequipa_chullo",
        "arequipa_los_incas",
        "arequipa_anas_huayco",
        "arequipa_san_lazaro",
        "arequipa_el_pato",
    }
    assert expected_2026 <= set(children)
    for child_id in expected_2026:
        child = children[child_id]
        assert "INGEMMET-A7737-AREQUIPA-2026" in child["source_ids"]
        assert child["geometry_asset"] is None
        assert child["outlet"] is None
        assert child["map_publishable"] is False

    for child_id in ("arequipa_anascoy", "arequipa_gamarra", "arequipa_panteon"):
        assert children[child_id]["evidence_state"] == "IMPACT_CONFIRMED"


def test_direct_arequipa_event_children_are_bounded_and_not_operational():
    cfg = load()
    by_id = {x["child_id"]: x for x in all_children(cfg)}
    for child_id in (
        "arequipa_anascoy",
        "arequipa_gamarra",
        "arequipa_panteon",
        "arequipa_ranrata",
        "arequipa_alca",
        "arequipa_umahuato",
        "arequipa_allachaya",
    ):
        child = by_id[child_id]
        assert child["evidence_state"] == "IMPACT_CONFIRMED"
        assert child["map_publishable"] is False
        assert child["activation_gate"] == "BLOCKED"


def test_lucha_is_territorial_event_not_invented_quebrada():
    cfg = load()
    sys = systems(cfg)["arequipa_ocona_cotahuasi_local_ravines"]
    assert all("lucha" not in x["child_id"].lower() for x in sys["children"])
    assert all("lucha" not in x["name"].lower() for x in sys["children"])
    ev = next(x for x in sys["territorial_events"] if x["event_id"] == "arequipa_lucha_2025")
    assert ev["named_child"] is None
    assert "Localidad Lucha" in ev["territorial_reference"]
    assert not ev.get("named_children")
    assert ev["hydrologic_assignment_status"] == UNNAMED
    # Canonical wording is two sentences, so the prohibition starts with a capital
    # "Do not". The semantic content is pinned exactly; only letter case is normalised.
    guard = ev["do_not_infer"]
    assert guard == (
        "Lucha is a territorial locality in this source. Do not create or name a child "
        "'Quebrada Lucha' without independent hydrologic evidence."
    )
    assert "do not create or name a child 'quebrada lucha'" in guard.lower()
    assert "territorial locality" in guard


def test_unnamed_territorial_events_never_create_geometry_by_implication():
    cfg = load()
    for sys in cfg["local_discovery_systems"]:
        for ev in sys.get("territorial_events", []):
            assert ev["do_not_infer"]
            assert ev["hydrologic_assignment_status"] in {UNNAMED, MULTI_NAMED}
            named = ([ev["named_child"]] if ev["named_child"] else []) + list(ev.get("named_children", []))
            if not named:
                # Hard rule: no identified quebrada -> pending status, nothing bound.
                assert ev["hydrologic_assignment_status"] == UNNAMED
            else:
                # A named status is only legitimate with an explicit binding to children
                # registered in the same system and backed by the event's own source.
                assert ev["hydrologic_assignment_status"] == MULTI_NAMED
                children = {x["child_id"]: x for x in sys["children"]}
                for child_id in named:
                    assert set(ev["source_ids"]) <= set(children[child_id]["source_ids"])
            assert ("named_children" in ev) == (ev["hydrologic_assignment_status"] == MULTI_NAMED)
        # Neither kind of event may create geometry, outlet, publication or activation.
        for child in sys["children"]:
            assert child["geometry_asset"] is None
            assert child["outlet"] is None
            assert child["map_publishable"] is False
            assert child["activation_gate"] == "BLOCKED"


def test_yauca_del_rosario_is_the_only_multi_named_event_and_binds_exactly_its_source_children():
    cfg = load()
    multi = [
        (sys, ev)
        for sys in cfg["local_discovery_systems"]
        for ev in sys.get("territorial_events", [])
        if ev["hydrologic_assignment_status"] == MULTI_NAMED
    ]
    assert [ev["event_id"] for _, ev in multi] == ["ica_yauca_rosario_2024_03_16"]
    sys, ev = multi[0]
    assert ev["named_child"] is None
    assert ev["named_children"] == ["ica_san_jose_de_curis", "ica_san_isidro_de_macchanga"]
    assert set(ev["named_children"]) == {x["child_id"] for x in sys["children"]}
    for child in sys["children"]:
        assert child["name"] in ev["statement"]
    assert "Do not create child geometry, outlet or threshold" in ev["do_not_infer"]


def test_unnamed_events_bind_no_child_and_no_child_claims_their_source():
    cfg = load()
    for sys in cfg["local_discovery_systems"]:
        for ev in sys.get("territorial_events", []):
            if ev["hydrologic_assignment_status"] != UNNAMED:
                continue
            assert ev["named_child"] is None
            assert "named_children" not in ev
            for child in all_children(cfg):
                assert not set(child["source_ids"]) & set(ev["source_ids"]), (ev["event_id"], child["child_id"])


def test_source_provenance_never_fakes_hashes():
    cfg = load()
    assert cfg["source_catalog"]
    for src in cfg["source_catalog"]:
        assert src["official"] is True
        assert src["url"].startswith("https://")
        sha = src["content_sha256"]
        if sha is None:
            status = src["provenance_status"]
            assert "NOT_ARCHIVED" in status or "PENDING_ARCHIVE" in status
        else:
            assert len(sha) == 64
            int(sha, 16)
        assert src["forbidden_use"]


def test_geometry_work_queue_prioritizes_reproducible_sources_not_approximation():
    cfg = load()
    queue = cfg["next_geometry_work_packages"]
    assert [x["priority"] for x in queue] == [1, 2, 3, 4, 5]
    assert queue[0]["target"] == "ica_cansas"
    assert queue[1]["target"] == "arequipa_metropolitana_torrenteras"
    assert "freeze" in queue[0]["goal"].lower()
    assert cfg["global_rules"]["no_approximate_points"] is True


def test_ica_pisco_quitasol_and_paracas_are_parent_bound_but_not_events():
    cfg = load()
    sys = systems(cfg)["ica_pisco_local_ravines"]
    children = {x["child_id"]: x for x in sys["children"]}
    for child_id in ("ica_quitasol", "ica_paracas"):
        child = children[child_id]
        assert child["identity_status"] == "OFFICIAL_ANA_CRITICAL_POINT_NAME_AND_PARENT_CONFIRMED"
        assert child["evidence_state"] == "CRITICAL_POINT_CONTEXT_NOT_EVENT"
        assert child["geometry_asset"] is None
        assert child["map_publishable"] is False
        assert child["activation_gate"] == "BLOCKED"


def test_pisco_critical_point_identity_event_and_geometry_stay_separate():
    cfg = load()
    sys = systems(cfg)["ica_pisco_local_ravines"]
    sources = {x["source_id"]: x for x in cfg["source_catalog"]}
    src = sources["ANA-ICA-CRITICAL-POINTS-DU015-2023"]
    assert src["official"] is True and src["content_sha256"] is None
    assert "Qda. Quitasol — Cuenca Pisco" in src["supports"]
    assert "Qda. Paracas — Cuenca Pisco" in src["supports"]
    forbidden = src["forbidden_use"].lower()
    for phrase in ("not an observed activation event", "event footprint", "catchment polygon", "hydraulic capacity", "threshold"):
        assert phrase in forbidden
    probes = {x["child_name"]: x for x in cfg["hydrography_probe_contracts"]}
    for child_id in ("ica_quitasol", "ica_paracas"):
        child = next(x for x in sys["children"] if x["child_id"] == child_id)
        # identity: one official ANA source, bound to Cuenca Pisco only
        assert child["source_ids"] == ["ANA-ICA-CRITICAL-POINTS-DU015-2023"]
        # critical point is not an event
        assert "IMPACT" not in child["evidence_state"] and "FLOW" not in child["evidence_state"]
        assert "not an observed activation event" in child["event_attribution_note"]
        # identity is not geometry
        assert child["geometry_status"] == "NAMED_BUT_REPRODUCIBLE_GEOMETRY_NOT_FROZEN"
        assert child["outlet_status"] == "UNKNOWN" and child["outlet"] is None
        probe = probes[child["name"]]
        assert probe["status"] == "PLANNED_FAIL_CLOSED_NOT_EXECUTED"
        assert probe["map_publishable"] is False and probe["event_state_transferred"] is False
        assert child["decision_thresholds"] is None and child["hydraulic_factors"] is None

    # The 2019 INDECI record that names "Quebrada Quitasol" is a historical event kept in
    # its own overlay with parent assignment pending. It must not be transferred onto the
    # critical-point identity, and the critical point must not upgrade that event.
    events = {e["id"]: e for e in load_json(EVENTS_2019)["events"]}
    hist = events["ica_huancano_huayanto_quitasol_remanso_2019_02_10"]
    assert "Quebrada Quitasol" in hist["reported_names"]
    assert hist["parent_assignment"] == "PENDING_REPRODUCIBLE_HYDROGRAPHIC_ADJUDICATION"
    assert hist["geometry_asset"] is None and hist["map_publishable"] is False
    assert "child_id" not in hist and "named_child" not in hist
    quitasol = next(x for x in sys["children"] if x["child_id"] == "ica_quitasol")
    assert "INDECI-ICA-IE472-2019" not in quitasol["source_ids"]
    assert all("Paracas" not in n for e in events.values() for n in e["reported_names"])


def test_addendum_parents_are_traceable_to_official_ana_sources():
    cfg = load()
    comp = load_json(COMPLETENESS)
    basins = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    additions = {x["discovery_id"]: x for x in comp["official_parent_additions"]}
    assert set(additions) == set(ADDENDUM_PARENTS)
    assert comp["summary"]["official_parent_additions"] == len(ADDENDUM_PARENTS)
    supported = {code for s in comp["sources"] if s["official"] for code in s["supports"]}
    course_text = " ".join(x for s in comp["sources"] for x in s["supports"])
    for basin_id, code in ADDENDUM_PARENTS.items():
        assert basins[basin_id]["official_unit_code"] == additions[basin_id]["official_unit_code"] == code
        assert basins[basin_id]["name"] == additions[basin_id]["name"]
        assert code in supported
        assert f"{additions[basin_id]['official_course_context']['name']} {code}" in course_text
        assert basins[basin_id]["must_not_merge_with"]
    assert "Quequeña" in additions["arequipa_honda"]["homonym_guard"]
    for s in comp["sources"]:
        assert s["content_sha256"] is None  # never fake a hash for a non-archived source
        assert "NOT_ARCHIVED" in s["provenance_status"]


def test_intercuenca_count_is_derived_from_inventory_and_matches_addendum():
    cfg = load()
    comp = load_json(COMPLETENESS)
    rows = cfg["official_intercuenca_contexts"]
    codes = [x["official_unit_code"] for x in rows]
    assert len(codes) == len(set(codes))
    assert cfg["summary"]["official_intercuenca_contexts_registered"] == len(rows)
    assert comp["summary"]["canonical_intercuenca_contexts_required"] == len(rows)
    assert set(codes) == {x["official_unit_code"] for x in comp["official_intercuenca_contexts"]}
    parent_codes = {x["official_unit_code"] for x in cfg["official_basin_hierarchy"]}
    assert not set(codes) & parent_codes
    supported = {code for s in comp["sources"] if s["official"] for code in s["supports"]}
    for row in rows:
        assert row["official_unit_code"] in supported
        assert row["entity_role"] == "OFFICIAL_INTERCUENCA_CONTEXT_NON_ACTIVATABLE"
        assert row["identity_status"] in {"OFFICIAL_ANA_UNIT_CONFIRMED", "OFFICIAL_ANA_UNIT_AND_COURSE_CONFIRMED"}
        assert (row["identity_status"] == "OFFICIAL_ANA_UNIT_AND_COURSE_CONFIRMED") == bool(row["course_context"])
        assert row["geometry_asset"] is None
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None and row["hydraulic_factors"] is None


def test_pytest_adjudication_record_is_fail_closed_and_matches_inventory():
    cfg = load()
    adj = load_json(ADJUDICATION)
    for key, value in SAFE.items():
        assert adj[key] == value
    assert [x["finding_id"] for x in adj["findings"]] == ["F1", "F2", "F3", "F4", "F5"]
    for finding in adj["findings"]:
        assert finding["verdict"] in {"TEST_EXPECTATION_STALE", "TEST_AND_STATE_UNDERSPECIFIED"}
        assert finding["evidence"] and finding["change"] and finding["limitations"] is not None
    live = adj["live_official_reference"]
    assert live["byte_frozen"] is False and live["content_sha256"] is None
    observed = live["observed_codigo_nombre"]
    for row in cfg["official_basin_hierarchy"] + cfg["official_intercuenca_contexts"]:
        assert row["official_unit_code"] in observed, row["discovery_id"]
    assert adj["summary"]["new_operational_zones"] == 0
    assert adj["summary"]["geometry_assets_published"] == 0
    assert adj["summary"]["states_relaxed"] == 0
    assert any(x["item_id"] == "OPEN-137539" for x in adj["open_scientific_items"])


def test_catambo_is_registered_from_ana_works_context_without_capacity_inference():
    cfg = load()
    sys = systems(cfg)["ica_ica_local_ravines"]
    children = {x["child_id"]: x for x in sys["children"]}
    catambo = children["ica_catambo"]
    assert catambo["identity_status"] == "OFFICIAL_ANA_WORKS_PACKAGE_NAME_CONFIRMED"
    assert catambo["evidence_state"] == "OFFICIAL_CHANNEL_IDENTITY_CONTEXT_NO_EVENT_ASSIGNED"
    assert catambo["geometry_asset"] is None
    assert catambo["outlet"] is None
    assert catambo["map_publishable"] is False


def test_rio_seco_intercuenca_is_not_forced_into_pisco_or_ica_basin():
    cfg = load()
    contexts = {x["discovery_id"]: x for x in cfg["official_intercuenca_contexts"]}
    row = contexts["ica_intercuenca_13751_rio_seco"]
    assert row["official_unit_code"] == "13751"
    assert row["entity_role"] == "OFFICIAL_INTERCUENCA_CONTEXT_NON_ACTIVATABLE"
    assert row["course_context"][0]["official_course_code"] == "137516"
    assert row["course_context"][0]["name"] == "Río Seco"
    assert row["course_context"][0]["map_publishable"] is False
    assert row["activation_gate"] == "BLOCKED"
    assert set(row["must_not_merge_with"]) == {"ica_pisco", "ica_ica"}


def test_arequipa_metro_response_names_are_context_not_activation_timing():
    cfg = load()
    sys = systems(cfg)["arequipa_metropolitana_torrenteras"]
    children = {x["child_id"]: x for x in sys["children"]}
    for child_id in ("arequipa_roncero", "arequipa_huarangal", "arequipa_ojo_del_buey"):
        child = children[child_id]
        assert child["identity_status"] == "OFFICIAL_INDECI_RESPONSE_NAME_CONFIRMED"
        assert child["evidence_state"] == "POST_EVENT_RESPONSE_CONTEXT_NOT_DIRECT_ACTIVATION_TIMING"
        assert child["geometry_asset"] is None
        assert child["outlet"] is None
        assert child["map_publishable"] is False


def test_pending_hydrologic_adjudication_never_creates_child_geometry():
    cfg = load()
    pending = {x["candidate_id"]: x for x in cfg["pending_hydrologic_adjudication"]}
    expected = {
        "ica_san_ignacio_palpa",
        "ica_sacramento_palpa",
        "ica_nuevo_vista_alegre_nasca",
        "ica_ayapana_de_tulin_sector_2025",
        "arequipa_quechualla_chaupo_2026",
        "arequipa_quechualla_aytinco_2026",
    }
    assert set(pending) == expected
    for row in pending.values():
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["do_not_infer"]

    ayapana = pending["ica_ayapana_de_tulin_sector_2025"]
    assert ayapana["identity_status"] == "TERRITORIAL_SECTOR_ONLY_NOT_A_NAMED_RAVINE"
    assert ayapana["geometry_status"] == "NO_CHILD_GEOMETRY_ALLOWED"
    assert "Quebrada Ayapana" in ayapana["do_not_infer"]


def test_new_local_children_have_fail_closed_ana_probe_contracts():
    cfg = load()
    probes = {(x["child_name"], x["expected_parent_uh_code"]) for x in cfg["hydrography_probe_contracts"]}
    assert len(probes) == 23
    assert ("Quebrada San José de Curis", None) in probes
    assert ("Quebrada San Isidro de Macchanga", None) in probes
    expected = {
        ("Quebrada Catambo", "1374"),
        ("Quebrada Quitasol", "13752"),
        ("Quebrada Paracas", "13752"),
        ("Quebrada Roncero", "132"),
        ("Quebrada Huarangal", "132"),
        ("Quebrada Ojo del Buey", "132"),
    }
    assert expected <= probes
    assert cfg["summary"]["local_hydrography_probe_contracts_registered"] == 23
    unresolved_systems = {
        x["discovery_id"] for x in cfg["local_discovery_systems"] if x["parent_basin_id"] is None
    }
    assert unresolved_systems == {"ica_rio_grande_local_ravines"}
    for probe in cfg["hydrography_probe_contracts"]:
        assert probe["status"] == "PLANNED_FAIL_CLOSED_NOT_EXECUTED"
        assert probe["map_publishable"] is False
        assert probe["event_state_transferred"] is False
        unresolved = probe["discovery_system_id"] in unresolved_systems
        if unresolved:
            # Parent UH is not presupposed for systems whose parent is unresolved.
            assert probe["expected_parent_uh_code"] is None
            assert probe["expected_parent_discovery_id"] is None
            assert probe["match_policy"] == "EXACT_NAME_REQUIRED_PARENT_UH_READ_FROM_OFFICIAL_RESULT_NOT_PRESUPPOSED"
            assert "no fallback by receiver name, proximity or district name" in probe["notes"]
        else:
            assert probe["expected_parent_uh_code"]
            assert probe["match_policy"] == "EXACT_NAME_PLUS_PARENT_UH_REQUIRED_FOR_ACCEPTANCE"


def test_ranrata_2026_direct_event_is_added_without_geometry_promotion():
    cfg = load()
    sys = systems(cfg)["arequipa_ocona_cotahuasi_local_ravines"]
    ranrata = next(x for x in sys["children"] if x["child_id"] == "arequipa_ranrata")
    assert "INDECI-TOMEPAMPA-RANRATA-2026" in ranrata["source_ids"]
    assert ranrata["map_publishable"] is False
    assert ranrata["geometry_asset"] is None


def test_expansion_summary_remains_research_only_and_zero_operational_zones():
    cfg = load()
    assert cfg["summary"]["named_local_children_registered"] == 23
    assert cfg["summary"]["map_publishable_children"] == 0
    # Was a literal 1 written before the completeness addendum registered the full
    # official intercuenca context. Derived from the inventory instead of hard-coded;
    # the 14 codes are pinned individually in the dedicated intercuenca test.
    assert cfg["summary"]["official_intercuenca_contexts_registered"] == len(cfg["official_intercuenca_contexts"]) == 14
    assert cfg["summary"]["named_local_children_registered"] == len(all_children(cfg))
    assert cfg["summary"]["official_parent_basins_registered"] == len(cfg["official_basin_hierarchy"]) == 17
    assert cfg["summary"]["pending_hydrologic_adjudications"] == 6
    assert cfg["summary"]["new_operational_zones"] == 0


# --- Parent binding of the Yauca del Rosario ravines (withdrawn 2026-10-03) -----------

UNRESOLVED_PARENT = "UNRESOLVED_PARENT_HYDROGRAPHIC_ASSIGNMENT"
BINDING_RELATION = "CHANNEL_BELONGS_TO_PARENT_UH"
BINDING_KEYS = {"child_id", "channel_name", "parent_basin_id", "parent_uh_code", "relation", "statement"}
NAME_PREFIXES = ("Quebrada / torrentera ", "Quebrada ", "Qda. ", "Río ")


def _basin_name_tokens(basin):
    """Proper-name tokens of an official basin, e.g. 'Cuenca Grande / Río Grande–Palpa–Nasca' -> {'grande', ...}."""
    import re

    stop = {"cuenca", "río", "rio", "de", "del", "la", "el", "y"}
    return {w for w in re.split(r"[^0-9a-záéíóúñü]+", basin["name"].lower()) if w and w not in stop}


def _receiver_text(system):
    parts = []
    for ev in system.get("territorial_events", []):
        parts += [ev.get("receiver_reference") or "", ev.get("statement") or ""]
    for child in system.get("children", []):
        parts.append((child.get("outlet_status") or "").replace("_", " "))
    return " ".join(parts).lower()


def _proper_name(child):
    name = child["name"]
    for prefix in NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def explicit_parent_bindings(cfg, system):
    """(child_id, source_id) pairs that explicitly prove the parent binding the system asserts.

    A source counts only through a dedicated `parent_binding_assertions` entry, and only if
    every link of the chain is present and consistent:
      1. the child cites the source;
      2. the entry names that child by id and by its exact registered name;
      3. the entry names the system's own parent_basin_id;
      4. the entry's UH code equals that basin's official_unit_code;
      5. the relation is CHANNEL_BELONGS_TO_PARENT_UH;
      6. the statement is verbatim one of the source's `supports` and contains both the UH
         code and the ravine's proper name.
    The issuing institution, the document type and generic wording are never criteria.
    """
    parent = system.get("parent_basin_id")
    if parent is None:
        return []
    basins = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    sources = {x["source_id"]: x for x in cfg["source_catalog"]}
    code = basins[parent]["official_unit_code"]
    proven = []
    for child in system.get("children", []):
        for sid in child["source_ids"]:
            source = sources.get(sid)
            if source is None:
                continue  # a source absent from the catalog proves nothing
            for a in source.get("parent_binding_assertions", []):
                if (
                    set(a) == BINDING_KEYS
                    and a["child_id"] == child["child_id"]
                    and a["channel_name"] == child["name"]
                    and a["parent_basin_id"] == parent
                    and a["parent_uh_code"] == code
                    and a["relation"] == BINDING_RELATION
                    and a["statement"] in source["supports"]
                    and f"UH {code}" in a["statement"]
                    and _proper_name(child) in a["statement"]
                ):
                    proven.append((child["child_id"], sid))
    return proven


def receiver_homonym_bindings(cfg):
    """Systems bound to an official basin whose name also appears as a reported receiver
    ('Río <name>') without explicit evidence of that concrete parent binding.
    Such a binding may rest on the receiver name alone and is forbidden."""
    import re

    basins = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    offenders = []
    for system in cfg["local_discovery_systems"]:
        parent = system.get("parent_basin_id")
        if parent is None:
            continue
        text = _receiver_text(system)
        homonym = any(re.search(r"r[ií]o " + re.escape(tok) + r"\b", text) for tok in _basin_name_tokens(basins[parent]))
        if homonym and not explicit_parent_bindings(cfg, system):
            offenders.append(system["discovery_id"])
    return offenders


def _ica_with_children(children_sources):
    """Copy of the inventory where ica_ica_local_ravines (receiver 'Río Ica', parent Cuenca
    Ica) keeps only the given children, each restricted to the given sources."""
    import copy

    cfg = copy.deepcopy(load())
    system = systems(cfg)["ica_ica_local_ravines"]
    kept = []
    for child in system["children"]:
        if child["child_id"] in children_sources:
            wanted = children_sources[child["child_id"]]
            assert set(wanted) <= set(child["source_ids"]), "controls must use real, already-cited sources"
            child["source_ids"] = list(wanted)
            kept.append(child)
    assert len(kept) == len(children_sources)
    system["children"] = kept
    return cfg


def test_receiver_name_alone_never_binds_a_system_to_a_homonymous_official_basin():
    cfg = load()
    assert cfg["global_rules"]["same_name_receiver_must_not_be_conflated_with_official_basin"] is True
    assert receiver_homonym_bindings(cfg) == []
    # The only homonym-exposed bound system is Ica ('Río Ica' under Cuenca Ica), and it is
    # exempt through exactly one explicit binding, not through the issuer of its sources.
    ica = systems(cfg)["ica_ica_local_ravines"]
    assert "río ica" in _receiver_text(ica)
    assert explicit_parent_bindings(cfg, ica) == [("ica_cansas", "ANA-CANSAS-UH1374-2025")]


def test_only_sources_with_a_traceable_statement_carry_parent_binding_assertions():
    cfg = load()
    basins = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    children = {x["child_id"]: x for x in all_children(cfg)}
    carriers = {}
    for source in cfg["source_catalog"]:
        for a in source.get("parent_binding_assertions", []):
            carriers.setdefault(source["source_id"], []).append(a)
            assert set(a) == BINDING_KEYS
            assert a["relation"] == BINDING_RELATION
            assert a["statement"] in source["supports"]
            assert a["channel_name"] == children[a["child_id"]]["name"]
            assert a["parent_uh_code"] == basins[a["parent_basin_id"]]["official_unit_code"]
            assert f"UH {a['parent_uh_code']}" in a["statement"]
            assert source["source_id"] in children[a["child_id"]]["source_ids"]
    assert set(carriers) == {"ANA-CANSAS-UH1374-2025"}
    # Marginal-strip, works, critical-point and administrative sources carry none.
    for sid in (
        "ANA-CANSAS-FAJA-2018",
        "ANA-CANSAS-FAJA-MOD-2019",
        "ANA-CANSAS-FAJA-2020-TRACE-2024",
        "ANA-LA-YESERA-FAJA-2019",
        "ANA-TORTOLITA-FAJA-2019",
        "ANA-ICA-CATAMBO-CANSAS-TDR-2023",
        "ANA-ICA-CRITICAL-POINTS-DU015-2023",
        "ANA-HYDRO-UH-PACIFIC-2025",
    ):
        source = next(x for x in cfg["source_catalog"] if x["source_id"] == sid)
        assert source["institution"].startswith("Autoridad Nacional del Agua")
        assert "parent_binding_assertions" not in source


def test_uncatalogued_source_ids_are_a_pinned_open_item_and_never_binding_evidence():
    # Known provenance gap (OPEN-UNCATALOGUED-SOURCE-IDS): two ids cited by Ica children have
    # no source_catalog entry. Pinned so the gap cannot grow silently; closing it means
    # cataloguing the sources and emptying this set, not deleting the citations.
    cfg = load()
    catalog = {x["source_id"] for x in cfg["source_catalog"]}
    cited = {sid for child in all_children(cfg) for sid in child["source_ids"]}
    assert cited - catalog == {"INDECI-CANSAS-HISTORICAL-PLAN", "ANA-CENEPRED-ICA-VULNERABLE-MAPS"}
    open_ids = {x["item_id"] for x in load_json(ADJUDICATION)["open_scientific_items"]}
    assert "OPEN-UNCATALOGUED-SOURCE-IDS" in open_ids
    # An uncatalogued id whose name starts with 'ANA' still proves no parent binding.
    cfg = _ica_with_children({"ica_la_yesera": ["ANA-CENEPRED-ICA-VULNERABLE-MAPS"]})
    assert receiver_homonym_bindings(cfg) == ["ica_ica_local_ravines"]


def test_negative_control_ana_marginal_strip_does_not_suppress_the_detector():
    for faja in (
        {"ica_cansas": ["ANA-CANSAS-FAJA-2018"]},
        {"ica_cansas": ["ANA-CANSAS-FAJA-2018", "ANA-CANSAS-FAJA-MOD-2019", "ANA-CANSAS-FAJA-2020-TRACE-2024"]},
        {"ica_la_yesera": ["ANA-LA-YESERA-FAJA-2019"], "ica_tortolita": ["ANA-TORTOLITA-FAJA-2019"]},
    ):
        cfg = _ica_with_children(faja)
        assert explicit_parent_bindings(cfg, systems(cfg)["ica_ica_local_ravines"]) == []
        assert receiver_homonym_bindings(cfg) == ["ica_ica_local_ravines"]


def test_negative_control_ana_works_tdr_does_not_suppress_the_detector():
    for works in (
        {"ica_catambo": ["ANA-ICA-CATAMBO-CANSAS-TDR-2023"]},
        {"ica_catambo": ["ANA-ICA-CATAMBO-CANSAS-TDR-2023"], "ica_cansas": ["ANA-CANSAS-FAJA-2018"]},
    ):
        cfg = _ica_with_children(works)
        assert receiver_homonym_bindings(cfg) == ["ica_ica_local_ravines"]
    # The TDR names 'Quebrada Cansas identity' and 'Río Ica works context': a name plus a
    # receiver in a works package is still not a statement of UH membership.
    tdr = next(x for x in load()["source_catalog"] if x["source_id"] == "ANA-ICA-CATAMBO-CANSAS-TDR-2023")
    assert "Río Ica works context" in tdr["supports"]


def test_negative_control_ana_critical_point_does_not_become_parent_binding():
    import copy

    cfg = copy.deepcopy(load())
    pisco = systems(cfg)["ica_pisco_local_ravines"]
    assert receiver_homonym_bindings(cfg) == []  # not exposed: its receiver is a local 'Río Grande'
    # Expose it to a homonymous receiver. Its children cite only the ANA critical-point list,
    # whose supports even name the basin ('Qda. Quitasol — Cuenca Pisco'): still not a binding.
    pisco["territorial_events"][0]["receiver_reference"] = "Río Pisco"
    assert {sid for c in pisco["children"] for sid in c["source_ids"]} == {"ANA-ICA-CRITICAL-POINTS-DU015-2023"}
    assert explicit_parent_bindings(cfg, pisco) == []
    assert receiver_homonym_bindings(cfg) == ["ica_pisco_local_ravines"]
    # And the critical point stays what it is.
    for child in pisco["children"]:
        assert child["evidence_state"] == "CRITICAL_POINT_CONTEXT_NOT_EVENT"


def test_positive_control_explicit_uh_statement_supports_the_cansas_binding_only():
    import copy

    # Cansas alone, with only the explicit UH 1374 source: binding to Cuenca Ica holds.
    cfg = _ica_with_children({"ica_cansas": ["ANA-CANSAS-UH1374-2025"]})
    ica = systems(cfg)["ica_ica_local_ravines"]
    assert explicit_parent_bindings(cfg, ica) == [("ica_cansas", "ANA-CANSAS-UH1374-2025")]
    assert receiver_homonym_bindings(cfg) == []

    def tampered(mutate):
        c = _ica_with_children({"ica_cansas": ["ANA-CANSAS-UH1374-2025"]})
        source = next(x for x in c["source_catalog"] if x["source_id"] == "ANA-CANSAS-UH1374-2025")
        mutate(c, source, source["parent_binding_assertions"][0])
        return receiver_homonym_bindings(c)

    flagged = ["ica_ica_local_ravines"]
    # Every link of the chain is required.
    assert tampered(lambda c, s, a: a.update(parent_uh_code="1372")) == flagged
    assert tampered(lambda c, s, a: a.update(parent_basin_id="ica_pisco")) == flagged
    assert tampered(lambda c, s, a: a.update(child_id="ica_catambo")) == flagged
    assert tampered(lambda c, s, a: a.update(channel_name="Quebrada Catambo")) == flagged
    assert tampered(lambda c, s, a: a.update(relation="NAME_IDENTITY_ONLY")) == flagged
    assert tampered(lambda c, s, a: a.update(statement="Cansas is in Cuenca Ica UH 1374")) == flagged  # not in supports
    assert tampered(lambda c, s, a: s.update(supports=["Cansas identity"])) == flagged
    assert tampered(lambda c, s, a: s.pop("parent_binding_assertions")) == flagged
    assert tampered(lambda c, s, a: a.pop("relation")) == flagged

    # The statement is about Cuenca Ica: it cannot support a binding to another basin.
    cfg = _ica_with_children({"ica_cansas": ["ANA-CANSAS-UH1374-2025"]})
    ica = systems(cfg)["ica_ica_local_ravines"]
    ica["parent_basin_id"] = "ica_rio_grande_palpa_nasca"
    ica["territorial_events"][0]["receiver_reference"] = "Río Grande"
    assert receiver_homonym_bindings(cfg) == ["ica_ica_local_ravines"]

    # Nor does it travel to another system's children.
    cfg = copy.deepcopy(load())
    yauca = systems(cfg)["ica_rio_grande_local_ravines"]
    yauca["parent_basin_id"] = "ica_ica"
    yauca["territorial_events"][0]["receiver_reference"] = "Río Ica"
    for child in yauca["children"]:
        child["source_ids"] = child["source_ids"] + ["ANA-CANSAS-UH1374-2025"]
    assert receiver_homonym_bindings(cfg) == ["ica_rio_grande_local_ravines"]


def test_receiver_homonym_detector_rejects_the_withdrawn_yauca_binding_and_its_variants():
    import copy

    # Restoring the withdrawn parent must be caught.
    cfg = copy.deepcopy(load())
    system = systems(cfg)["ica_rio_grande_local_ravines"]
    system["parent_basin_id"] = "ica_rio_grande_palpa_nasca"
    assert receiver_homonym_bindings(cfg) == ["ica_rio_grande_local_ravines"]

    # Same pattern on another system: the Huancano report names a local 'Río Grande'.
    cfg = copy.deepcopy(load())
    pisco = systems(cfg)["ica_pisco_local_ravines"]
    pisco["parent_basin_id"] = "ica_rio_grande_palpa_nasca"
    assert receiver_homonym_bindings(cfg) == ["ica_pisco_local_ravines"]

    # Being unresolved is not a finding, and unresolved systems never count as proven.
    cfg = load()
    yauca = systems(cfg)["ica_rio_grande_local_ravines"]
    assert explicit_parent_bindings(cfg, yauca) == []
    assert "ica_rio_grande_local_ravines" not in receiver_homonym_bindings(cfg)


def test_yauca_del_rosario_parent_is_explicitly_unresolved_and_not_transferred():
    cfg = load()
    system = systems(cfg)["ica_rio_grande_local_ravines"]
    assert system["parent_basin_id"] is None
    assert system["parent_assignment_status"] == UNRESOLVED_PARENT
    pa = system["parent_assignment"]
    assert pa["status"] == UNRESOLVED_PARENT
    assert pa["withdrawn_parent_basin_id"] == "ica_rio_grande_palpa_nasca"
    assert pa["withdrawn_parent_uh_code"] == "1372"
    assert pa["reassigned_to"] is None
    assert pa["candidate_parent_basin_ids"] == []
    assert pa["discovery_id_is_legacy_label_not_basin_assertion"] is True
    assert "receiver name" in pa["withdrawal_reason"]
    assert "UH 1372" in system["homonym_guard"] and "any other official basin" in system["homonym_guard"]

    ev = system["territorial_events"][0]
    assert "Río Grande" in ev["receiver_reference"] and "unresolved" in ev["receiver_reference"]
    assert "ANA Cuenca Grande UH 1372" in ev["do_not_infer"]
    assert ev["hydrologic_assignment_status"] == MULTI_NAMED

    # The event evidence itself is untouched; only the basin claim is withdrawn.
    for child in system["children"]:
        assert child["parent_assignment_status"] == UNRESOLVED_PARENT
        assert child["identity_status"] == "OFFICIAL_NAME_CONFIRMED"
        assert child["evidence_state"] == "IMPACT_CONFIRMED"
        assert child["source_ids"] == ["INDECI-YAUCA-ROSARIO-2024"]
        assert child["geometry_asset"] is None and child["outlet"] is None
        assert child["map_publishable"] is False
        assert child["activation_gate"] == "BLOCKED"
        assert child["decision_thresholds"] is None and child["hydraulic_factors"] is None
    for key in ("activation_gate", "decision_thresholds", "hydraulic_factors"):
        assert system[key] == SAFE[key]

    # The official basin row stays as context and is not altered by the withdrawal.
    grande = next(x for x in cfg["official_basin_hierarchy"] if x["discovery_id"] == "ica_rio_grande_palpa_nasca")
    assert grande["official_unit_code"] == "1372"
    assert cfg["summary"]["local_systems_with_unresolved_parent_assignment"] == 1
    assert cfg["summary"]["new_operational_zones"] == 0
    assert cfg["summary"]["map_publishable_children"] == 0


def test_every_system_has_either_a_registered_parent_or_an_explicit_unresolved_state():
    cfg = load()
    basins = {x["discovery_id"] for x in cfg["official_basin_hierarchy"]}
    unresolved = 0
    for system in cfg["local_discovery_systems"]:
        if system["parent_basin_id"] is None:
            unresolved += 1
            assert system["parent_assignment_status"] == UNRESOLVED_PARENT
            assert system["parent_assignment"]["reassigned_to"] is None
        else:
            assert system["parent_basin_id"] in basins
            assert system.get("parent_assignment_status") != UNRESOLVED_PARENT
    assert unresolved == cfg["summary"]["local_systems_with_unresolved_parent_assignment"]


def test_parent_binding_adjudication_record_matches_state_and_claims_no_proof():
    cfg = load()
    rec = load_json(ADJUDICATION)["parent_binding_adjudication"]
    system = systems(cfg)[rec["system"]]
    assert rec["result"] == "NOT_DEMONSTRATED_BINDING_WITHDRAWN"
    assert rec["resulting_state"] == system["parent_assignment_status"] == UNRESOLVED_PARENT
    assert rec["reassigned_to"] is None
    for attempt in rec["official_evidence_attempted"]:
        assert attempt["content_sha256"] is None  # nothing was byte-frozen; never fake a hash
        assert attempt["outcome"] not in {"PARENT_UH_CONFIRMED", "DEMONSTRATED"}
    ctx = rec["contextual_observation_not_evidence"]
    assert ctx["use"].startswith("NOT_EVIDENCE_FOR_ASSIGNMENT")
    assert "ica_ica" not in system["parent_assignment"]["candidate_parent_basin_ids"]
    summary = load_json(ADJUDICATION)["summary"]
    assert summary["parent_bindings_withdrawn"] == 1 and summary["parent_bindings_reassigned"] == 0
