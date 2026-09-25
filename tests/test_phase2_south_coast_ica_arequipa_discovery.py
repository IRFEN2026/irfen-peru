import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_south_coast_ica_arequipa_discovery_v0_1.json"

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
}


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def systems(cfg):
    return {x["discovery_id"]: x for x in cfg["local_discovery_systems"]}


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
    assert sys["children"] == []
    ev = sys["territorial_events"][0]
    assert ev["named_child"] is None
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
    assert "do not create or name a child 'Quebrada Lucha'" in ev["do_not_infer"]


def test_unnamed_territorial_events_never_create_geometry_by_implication():
    cfg = load()
    for sys in cfg["local_discovery_systems"]:
        for ev in sys.get("territorial_events", []):
            if ev["named_child"] is None:
                assert ev["hydrologic_assignment_status"] == "TERRITORIAL_EVENT_PENDING_LOCAL_GEOMETRY"
                assert ev["do_not_infer"]


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
    for probe in cfg["hydrography_probe_contracts"]:
        assert probe["status"] == "PLANNED_FAIL_CLOSED_NOT_EXECUTED"
        assert probe["map_publishable"] is False
        assert probe["event_state_transferred"] is False
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
    assert cfg["summary"]["official_intercuenca_contexts_registered"] == 1
    assert cfg["summary"]["pending_hydrologic_adjudications"] == 6
    assert cfg["summary"]["new_operational_zones"] == 0
