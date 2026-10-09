import json
from pathlib import Path

CFG = Path("config/phase2_south_coast_moquegua_tacna_discovery_v0_1.json")

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

PARENTS = {
    "tacna_de_la_concordia": "13152",
    "tacna_hospicio": "13154",
    "tacna_caplina": "13156",
    "tacna_sama": "13158",
    "tacna_locumba": "1316",
    "moquegua_ilo_moquegua": "13172",
    "moquegua_honda": "13178",
    "moquegua_tambo": "1318",
}

UH_CONTEXTS = {
    "tacna_escritos_13153": "13153",
    "tacna_los_molles_13155": "13155",
    "tacna_los_muelles_13157": "13157",
    "tacna_intercuenca_13159": "13159",
    "tacna_intercuenca_13171": "13171",
}


def load():
    return json.loads(CFG.read_text(encoding="utf-8"))


def systems(cfg):
    return {x["discovery_id"]: x for x in cfg["local_discovery_systems"]}


def children(cfg):
    return [c for s in cfg["local_discovery_systems"] for c in s.get("children", [])]


def test_global_safety_contract_is_fail_closed():
    cfg = load()
    for key, value in SAFE.items():
        assert cfg[key] == value

    rules = cfg["global_rules"]
    required_true = [
        "parent_is_context_only",
        "child_activation_does_not_activate_parent",
        "no_geometry_without_reproducible_source",
        "no_synthetic_union_geometry",
        "no_approximate_points",
        "territorial_event_without_named_ravine_cannot_create_child_geometry",
        "district_or_province_name_is_not_hydrographic_assignment",
        "event_state_transfer_forbidden",
        "critical_point_is_not_event",
        "marginal_strip_is_not_event_footprint",
        "evacuation_map_is_not_event_footprint",
        "work_or_design_is_not_historical_capacity",
        "absence_of_report_is_not_negative_control",
        "threshold_transfer_between_basins_forbidden",
        "tributary_activation_does_not_imply_receiver_overflow",
        "same_name_channel_requires_parent_uh_match",
    ]
    for key in required_true:
        assert rules[key] is True
    assert set(rules["mechanisms_must_remain_separate"]) == {
        "FLUVIAL_FLOOD", "DEBRIS_FLOW_HUAICO", "LANDSLIDE", "PLUVIAL", "COASTAL_MARINE"
    }


def test_official_parent_codes_are_context_only():
    cfg = load()
    rows = {x["discovery_id"]: x for x in cfg["official_basin_hierarchy"]}
    assert {k: v["official_unit_code"] for k, v in rows.items()} == PARENTS
    for row in rows.values():
        assert row["entity_role"] == "OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE"
        assert row["identity_status"] == "OFFICIAL_ANA_UNIT_CONFIRMED"
        assert row["geometry_asset"] is None
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None


def test_additional_uh_contexts_are_non_activatable_and_unmapped():
    cfg = load()
    rows = {x["context_id"]: x for x in cfg["official_uh_contexts"]}
    assert {k: v["official_unit_code"] for k, v in rows.items()} == UH_CONTEXTS
    for row in rows.values():
        assert row["entity_role"] == "OFFICIAL_UH_CONTEXT_NON_ACTIVATABLE"
        assert row["geometry_asset"] is None
        assert row["map_publishable"] is False


def test_all_named_children_remain_unmapped_until_geometry_is_reproducible():
    cfg = load()
    rows = children(cfg)
    assert len(rows) == 12
    for row in rows:
        assert row["geometry_asset"] is None
        assert row["map_publishable"] is False
        assert row["activation_gate"] == "BLOCKED"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None


def test_mirave_keeps_collector_topology_but_not_unfrozen_outlet_or_parent():
    cfg = load()
    sys = systems(cfg)["tacna_locumba_ilabaya_local_ravines"]
    assert sys["parent_basin_id"] is None
    assert sys["candidate_parent_basin_id"] == "tacna_locumba"
    by_id = {x["child_id"]: x for x in sys["children"]}
    mirave = by_id["tacna_mirave"]
    assert mirave["collector"] == "río Salado"
    assert "CONFIRMED" in mirave["collector_status"]
    assert mirave["outlet"] is None
    assert set(mirave["event_ids"]) == {"tacna_mirave_2015", "tacna_mirave_2019"}
    assert mirave["map_publishable"] is False


def test_burros_is_not_forced_into_sama_until_exact_uh_match():
    cfg = load()
    sys = systems(cfg)["tacna_sama_coastal_ravines"]
    assert sys["parent_basin_id"] is None
    assert sys["candidate_parent_basin_id"] == "tacna_sama"
    burros = sys["children"][0]
    assert burros["child_id"] == "tacna_quebrada_de_los_burros"
    assert set(burros["event_ids"]) == {"tacna_burros_2021", "tacna_burros_2026"}


def test_chacane_event_is_separate_from_unnamed_pe36a_event():
    cfg = load()
    sys = systems(cfg)["moquegua_torata_local_ravines"]
    chacane = sys["children"][0]
    assert chacane["child_id"] == "moquegua_chacane"
    assert chacane["event_ids"] == ["moquegua_chacane_2024"]
    ev = next(x for x in sys["territorial_events"] if x["event_id"] == "moquegua_torata_pe36a_2024_unnamed")
    assert ev["named_child"] is None
    assert ev["hydrologic_assignment_status"] == "TERRITORIAL_EVENT_PENDING_LOCAL_GEOMETRY"
    assert "Do not transfer" in ev["do_not_infer"]


def test_ilo_and_pacocha_events_do_not_create_fake_children():
    cfg = load()
    sys = systems(cfg)["moquegua_ilo_pacocha_coastal_events"]
    assert sys["children"] == []
    assert len(sys["territorial_events"]) == 2
    for ev in sys["territorial_events"]:
        assert ev["named_child"] is None
        assert ev["hydrologic_assignment_status"] == "TERRITORIAL_EVENT_PENDING_LOCAL_GEOMETRY"
        assert ev["do_not_infer"]


def test_tarata_generic_quebrada_seca_wording_does_not_create_child():
    cfg = load()
    sys = systems(cfg)["tacna_tarata_local_ravines"]
    assert sys["children"] == []
    ev = sys["territorial_events"][0]
    assert ev["named_child"] is None
    assert "proper hydronym" in ev["do_not_infer"]


def test_general_sanchez_cerro_is_not_forced_into_one_parent_basin():
    cfg = load()
    sys = systems(cfg)["moquegua_general_sanchez_cerro_local_events"]
    assert sys["parent_basin_id"] is None
    assert sys["candidate_parent_basin_id"] is None
    volc = next(x for x in sys["children"] if x["child_id"] == "moquegua_volcanmayo")
    assert volc["event_ids"] == ["moquegua_volcanmayo_2026"]
    assert len(sys["territorial_events"]) == 3
    assert all(x["named_child"] is None for x in sys["territorial_events"])


def test_event_catalog_is_bounded_and_never_transfers_state():
    cfg = load()
    events = {x["event_id"]: x for x in cfg["event_catalog"]}
    assert set(events) == {
        "tacna_ataspaca_2020",
        "tacna_mirave_2015",
        "tacna_mirave_2019",
        "tacna_pachana_2015",
        "tacna_burros_2021",
        "tacna_burros_2026",
        "moquegua_chacane_2024",
        "moquegua_volcanmayo_2026",
    }
    assert all(x["event_state_transfer_allowed"] is False for x in events.values())


def test_source_provenance_never_fakes_hashes():
    cfg = load()
    assert cfg["source_catalog"]
    for src in cfg["source_catalog"]:
        assert src["official"] is True
        assert src["url"].startswith("https://")
        assert src["forbidden_use"]
        if src["content_sha256"] is None:
            assert "NOT_ARCHIVED" in src["provenance_status"]
        else:
            assert len(src["content_sha256"]) == 64
            int(src["content_sha256"], 16)


def test_hydrography_probes_are_fail_closed():
    cfg = load()
    probes = {x["target"]: x for x in cfg["hydrography_probe_contracts"]}
    assert set(probes) == {
        "tacna_mirave",
        "tacna_quebrada_de_los_burros",
        "moquegua_chacane",
        "moquegua_volcanmayo",
        "tacna_calientes_pachia",
    }
    for row in probes.values():
        assert row["status"] == "PLANNED_FAIL_CLOSED_NOT_EXECUTED"
        assert row["map_publishable"] is False
        assert row["event_state_transferred"] is False
        assert row["match_policy"] == "EXACT_CHILD_NAME_PLUS_OFFICIAL_UH_GEOMETRY_INTERSECTION_REQUIRED"


def test_calientes_evacuacion_map_is_context_not_event_footprint():
    cfg = load()
    sys = systems(cfg)["tacna_caplina_local_ravines"]
    cal = next(x for x in sys["children"] if x["child_id"] == "tacna_calientes_pachia")
    assert cal["evidence_state"] == "EVACUATION_AND_INUNDATION_CONTEXT_NOT_EVENT"
    assert cal["map_publishable"] is False
    src = next(x for x in cfg["source_catalog"] if x["source_id"] == "ANA-INDECI-CALIENTES-PACHIA-2015")
    assert "not a historical event footprint" in src["forbidden_use"]


def test_map_policy_blocks_unreproducible_geometry_and_risk_semantics():
    cfg = load()
    policy = cfg["map_policy"]
    assert policy["children"] == "PUBLISH_ONLY_WITH_REPRODUCIBLE_GEOMETRY"
    assert policy["missing_geometry_is_not_drawn"] is True
    assert policy["territorial_event_without_named_child_is_not_drawn_as_ravine"] is True
    assert policy["risk_colours_forbidden"] is True
    assert policy["alert_semantics_forbidden"] is True


def test_summary_counts_are_consistent_and_zero_operational():
    cfg = load()
    s = cfg["summary"]
    assert s["official_parent_basins_registered"] == 8
    assert s["official_additional_uh_contexts_registered"] == 5
    assert s["local_discovery_systems_registered"] == 7
    assert s["named_local_children_registered"] == 12
    assert s["direct_event_records_registered"] == 8
    assert s["territorial_events_without_named_child_registered"] == 7
    assert s["map_publishable_children"] == 0
    assert s["new_operational_zones"] == 0
