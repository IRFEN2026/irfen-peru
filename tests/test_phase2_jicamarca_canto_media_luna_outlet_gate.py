import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_jicamarca_canto_grande_media_luna_assessment_v0_2.json"

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

EXPECTED = {
    "canto_grande_upper_branch": {
        "path": "site/data/phase2/geometries/jicamarca_canto_grande_igp_channel.geojson",
        "source_name": "Qda Canto Grande",
        "objectids": {15404, 18807},
        "blob_sha": "db4b4204cfd5c5b1447ebdfc8aa963f37ee6ab3f",
    },
    "media_luna": {
        "path": "site/data/phase2/geometries/jicamarca_media_luna_igp_channel.geojson",
        "source_name": "Qda Media Luna",
        "objectids": {3351, 11823},
        "blob_sha": "9fbaa8349f29f79b4890dee1a1c2f32b638fd5d4",
    },
}


def load_cfg():
    return json.loads(CFG.read_text(encoding="utf-8"))


def load_asset(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def assert_guards(obj):
    for key, expected in SAFE.items():
        assert obj[key] == expected


def test_v02_preserves_fail_closed_phase2_guards():
    cfg = load_cfg()
    assert_guards(cfg)
    assert cfg["status"] == "OFFICIAL_CHILD_CHANNEL_LINES_FROZEN_CATCHMENTS_JUNCTIONS_AND_OUTLETS_UNRESOLVED"
    sci = cfg["scientific_interpretation"]
    assert sci["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert sci["child_evidence_promotes_parent_activation"] is False
    assert sci["child_activation_implies_rimac_overflow"] is False
    assert sci["synthetic_canto_media_luna_union_geometry_allowed"] is False
    assert sci["synthetic_quebrada_jicamarca_unit_allowed"] is False


def test_official_igp_child_channel_lines_are_frozen_without_outlet_promotion():
    cfg = load_cfg()
    frozen = cfg["frozen_official_channel_assets"]
    assert set(frozen) == set(EXPECTED)
    for child_id, expected in EXPECTED.items():
        row = frozen[child_id]
        assert row["path"] == expected["path"]
        assert row["git_blob_sha"] == expected["blob_sha"]
        assert row["source_name"] == expected["source_name"]
        assert set(row["source_objectids"]) == expected["objectids"]
        assert row["channel_geometry_reproducible"] is True
        assert row["catchment_polygon_reproducible"] is False
        assert row["outlet_or_confluence_reproducible"] is False
        assert row["official_channel_endpoint_is_outlet"] is False
        assert row["source_segments_union_performed"] is False
        assert row["geometry_role"] == "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"

        asset = load_asset(row["path"])
        assert asset["type"] == "FeatureCollection"
        assert asset["properties"]["hydrologic_child_id"] == child_id
        assert asset["properties"]["geometry_role"] == "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"
        assert asset["properties"]["outlet_or_confluence"] is False
        assert asset["properties"]["catchment_polygon"] is False
        assert asset["properties"]["routing_enabled"] is False
        assert asset["properties"]["source_segments_union_performed"] is False
        assert_guards(asset["properties"])
        assert {f["properties"]["source_objectid"] for f in asset["features"]} == expected["objectids"]
        assert {f["properties"]["source_name"] for f in asset["features"]} == {expected["source_name"]}
        for feature in asset["features"]:
            props = feature["properties"]
            assert feature["geometry"]["type"] == "LineString"
            assert props["hydrologic_child_id"] == child_id
            assert props["geometry_role"] == "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"
            assert props["outlet_or_confluence"] is False
            assert props["catchment_polygon"] is False
            assert props["routing_parameter"] is False
            assert props["activation_evidence"] is False
            assert props["risk_or_alert_layer"] is False
            assert_guards(props)


def test_outlet_resolution_gate_forbids_shortcuts_and_fails_closed():
    gate = load_cfg()["outlet_resolution_gate"]
    assert gate["status"].startswith("BLOCKED_")
    assert gate["candidate_generation_promotion_allowed"] is False
    assert all(value is None for value in gate["resolved_outlets"].values())
    assert all(value is None for value in gate["resolved_catchments"].values())

    forbidden = set(gate["forbidden_inputs"])
    required_forbidden = {
        "faja_marginal_endpoints_as_outlets",
        "event_or_impact_footprints_for_geometry_fitting",
        "A6680_as_geometry_calibration_target",
        "city_or_district_centroids_as_outlets",
        "report_image_digitization_as_final_geometry",
        "OSM_or_place_points_as_final_outlets",
        "official_channel_endpoints_assumed_to_be_outlets",
        "contaminated_or_outcome_bearing_artifacts_for_geometry_selection",
        "synthetic_quebrada_jicamarca_union",
    }
    assert required_forbidden <= forbidden

    method = gate["deterministic_method_requirements"]
    assert method["official_channel_line_role"] == "SEARCH_ANCHOR_AND_TOPOLOGIC_CONSTRAINT_ONLY_NOT_OUTLET"
    assert method["candidate_must_be_unique_under_frozen_parameters"] is True
    assert method["source_and_parameter_hashes_required"] is True
    assert method["exact_replay_required"] is True
    assert method["independent_scientific_qa_required"] is True
    assert method["prohibited_source_touch_fails_closed"] is True
    assert method["ambiguous_candidate_fails_closed"] is True
    assert method["missing_dem_or_receiver_geometry_fails_closed"] is True


def test_collector_coupling_remains_unparameterized_until_spatial_gate_passes():
    cfg = load_cfg()
    topo = cfg["topology_model"]
    assert topo["media_luna_exact_junction_coordinate"] is None
    assert topo["canto_grande_exact_outlet_coordinate"] is None
    assert topo["direct_media_luna_to_rimac_connection_assumed"] is False
    assert topo["topology_may_be_used_for_routing_before_geometry_and_outlets"] is False

    coupling = cfg["collector_coupling"]
    assert coupling["routing_status"].startswith("BLOCKED_")
    for child_id in EXPECTED:
        child = coupling[child_id]
        assert child["outlet_or_confluence"] is None
        assert child["Q_i_t"] is None
        assert child["travel_time"] is None
        assert child["attenuation"] is None
        assert child["quality"] == "UNKNOWN"
    assert coupling["collector_stage_or_discharge_response"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["child_activation_implies_canto_grande_parent_activation"] is False
    assert coupling["child_activation_implies_rimac_overflow"] is False


def test_map_policy_exposes_only_reproducible_channel_context():
    mp = load_cfg()["map_policy"]
    assert mp["publish_parent_as_activation_or_risk"] is False
    assert mp["publish_official_child_channel_lines_as_research_context"] is True
    assert mp["publish_child_catchment_polygons_now"] is False
    assert mp["publish_child_outlets_now"] is False
    assert mp["publish_event_footprint_from_channel_geometry"] is False
    assert mp["risk_or_alert_colors_allowed"] is False
    assert mp["parent_style"] == "GRAY_CONTEXT_ONLY"
    assert mp["child_channel_style"] == "RESEARCH_CONTEXT_NO_RISK_COLOR"


def test_2002_event_remains_local_and_is_not_a_geometry_fitting_target():
    event = load_cfg()["bounded_event_evidence"]
    assert event["event_year"] == 2002
    assert event["component_id"] == "media_luna"
    assert event["research_state"] == "IMPACT_CONFIRMED"
    assert event["event_footprint_geometry_available"] is False
    assert event["event_footprint_may_be_digitized_from_report_image"] is False
    assert event["promotes_canto_grande_parent_activation"] is False
    assert event["promotes_rimac_overflow"] is False
