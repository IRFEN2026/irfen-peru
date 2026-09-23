import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_jicamarca_discovery_v0_1.json"
ARCH=ROOT/"config/phase2_local_activation_hierarchy_v0_1.json"
CENDEHUA=ROOT/"config/phase2_jicamarca_cendehua_event_metadata_v0_1.json"
SOPHY=ROOT/"config/phase2_jicamarca_sophy_access_assessment_v0_1.json"
IDENTITY=ROOT/"config/phase2_jicamarca_identity_source_assessment_v0_1.json"
CANTO=ROOT/"config/phase2_jicamarca_canto_grande_media_luna_assessment_v0_1.json"
INDEX=ROOT/"config/phase2_jicamarca_evidence_index_v0_1.json"

def load(path=CFG):
    return json.loads(path.read_text(encoding="utf-8"))

def assert_safe(c):
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None

def test_fail_closed():
    assert_safe(load())

def test_pending_discovery_inherits_universal_hierarchy_without_candidate_registration():
    c=load(); h=c["hierarchy_binding"]
    assert h["architecture"]=="config/phase2_local_activation_hierarchy_v0_1.json"
    assert h["parent_role"]=="CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert h["parent_activation_state"] is None
    assert h["child_evidence_promotes_parent_activation"] is False
    assert h["candidate_inventory_registration"] is False
    assert ARCH.is_file()

def test_jicamarca_is_not_one_synthetic_ravine():
    c=load()
    assert c["territorial_identity"]["jicamarca_is_single_hydrologic_unit"] is False
    ids={x["child_id"] for x in c["hydrologic_components"]}
    assert {"huaycoloro","rio_seco","canto_grande_media_luna","jicamarca_named_channel"} <= ids
    assert c["map_policy"]["publish_parent_polygon"] is False
    assert c["map_policy"]["approximate_points_for_missing_geometry_forbidden"] is True

def test_huaycoloro_is_referenced_not_duplicated():
    c=load()
    h=next(x for x in c["hydrologic_components"] if x["child_id"]=="huaycoloro")
    assert h["existing_irfen_reference"]=="chosica_huaycoloro"
    assert h["duplicate_new_parent_geometry_forbidden"] is True

def test_unresolved_children_have_no_invented_geometry_or_outlets():
    c=load()
    by={x["child_id"]:x for x in c["hydrologic_components"]}
    for cid in ("rio_seco","canto_grande_media_luna","jicamarca_named_channel"):
        assert by[cid]["geometry_status"].startswith("MISSING_")
        assert by[cid]["outlet_status"].startswith("MISSING_")

def test_historical_evidence_preserves_component_attribution():
    c=load(); ev={x["event_id"]:x for x in c["historical_evidence"]}
    assert ev["JICAMARCA-MEDIA-LUNA-2002"]["component_id"]=="canto_grande_media_luna"
    assert ev["JICAMARCA-HUAYCOLORO2-2023-03-15"]["component_id"]=="huaycoloro"
    assert ev["JICAMARCA-RIOSECO2-2023-03-15"]["component_id"]=="rio_seco"
    assert ev["JICAMARCA-RIOSECO2-2023-03-15"]["reported_sensor_height_m"]==0.43
    assert ev["JICAMARCA-RIOSECO2-2023-03-15"]["reported_discharge_m3_s"] is None
    assert ev["JICAMARCA-VALLE-SAGRADO-2023-03-15"]["status"].endswith("MECHANISM_PARTIAL")
    assert ev["JICAMARCA-VALLE-SAGRADO-2023-03-15"]["local_ravine_attribution"]=="PARTIAL_UNRESOLVED"

def test_monitoring_does_not_import_operational_thresholds():
    c=load()
    cen=next(x for x in c["monitoring_assets"] if x["source_id"]=="IGP-CENDEHUA")
    assert cen["operational_alert_thresholds_imported_to_irfen"] is False
    radar=next(x for x in c["monitoring_assets"] if x["source_id"]=="IGP-SOPHY-XBAND-RADAR")
    assert radar["data_access_status"]=="PUBLIC_PROJECT_METADATA_ONLY_DATA_ACCESS_UNRESOLVED"

def test_bounded_evidence_packages_exist_and_are_safe():
    c=load(); refs=c["evidence_packages"]
    assert refs["cendehua_event_metadata"]=="config/phase2_jicamarca_cendehua_event_metadata_v0_1.json"
    assert refs["sophy_access_assessment"]=="config/phase2_jicamarca_sophy_access_assessment_v0_1.json"
    for p in (CENDEHUA,SOPHY,IDENTITY,CANTO,INDEX):
        assert p.is_file()
        assert_safe(load(p))

def test_cendehua_event_metadata_fails_closed_on_unknown_hydraulics():
    c=load(CENDEHUA)
    ev={x["record_id"]:x for x in c["events"]}
    rs2_14=ev["IGP-RS2-2023-03-14T16:37:37-05:00"]
    hl2=ev["IGP-HL2-2023-03-15T14:44:19-05:00"]
    rs2=ev["IGP-RS2-2023-03-15T16:27:41-05:00"]
    assert rs2_14["reported_discharge_m3_s"] is None
    assert rs2_14["reported_height_m"] is None
    assert hl2["reported_discharge_m3_s"] is None
    assert rs2["reported_discharge_m3_s"] is None
    assert rs2["reported_height_m"]==0.43
    assert rs2["source_reported_height_is_irfen_threshold"] is False
    assert hl2["source_reported_intensity_is_irfen_threshold"] is False
    assert hl2["source_reported_reference_is_reproducible_outlet"] is False
    assert rs2["source_reported_reference_is_reproducible_outlet"] is False
    assert c["known_metadata_conflicts"][0]["status"].startswith("PRESERVE_AS_SOURCE_LABEL_CONFLICT")
    assert c["qa_rules"]["cross_component_relabel_from_press_text_forbidden"] is True

def test_sophy_metadata_does_not_fabricate_rainfall_or_coverage():
    c=load(SOPHY); access=c["data_access_assessment"]
    assert c["status"]=="PUBLIC_PROJECT_METADATA_ONLY_DATA_ACCESS_UNRESOLVED"
    assert access["public_machine_readable_archive_identified"] is False
    assert access["public_research_download_endpoint_identified"] is False
    assert access["documented_api_identified"] is False
    assert access["raw_or_level2_data_retrieved"] is False
    assert access["qa_reproducible"] is False
    assert access["subcatchment_rainfall_reconstruction_allowed"] is False
    assert "infer rainfall values from project-page metadata" in c["forbidden"]
    assert "treat nominal radar range as verified event coverage" in c["forbidden"]

def test_official_jicamarca_relation_is_documented_but_geometry_stays_blocked():
    c=load(IDENTITY)
    assert c["status"]=="OFFICIAL_HYDROLOGIC_RELATION_DOCUMENTED_GEOMETRY_UNRESOLVED"
    assert c["conclusion"].startswith("JICAMARCA_IS_OFFICIAL_SUBBASIN_AND_DOWNSTREAM_NAMING_CONTEXT")
    topo=c["topology_status"]
    assert topo["official_parent_subbasin_id"]=="1375542"
    assert topo["huaycoloro_rio_seco_union"]=="OFFICIALLY_DESCRIBED_TOPOLOGY_COORDINATES_UNRESOLVED"
    assert topo["exact_union_coordinate"] is None
    assert topo["jicamarca_named_channel_relationship"]=="DOWNSTREAM_NAMING_RELATION_DOCUMENTED_EXACT_LINE_GEOMETRY_UNRESOLVED"
    gp=c["geometry_policy"]
    assert gp["official_parent_subbasin_is_local_activation_geometry"] is False
    assert gp["standalone_jicamarca_local_polygon_allowed"] is False
    assert gp["approximate_confluence_point_allowed"] is False
    assert gp["union_of_child_polygons_allowed"] is False

def test_canto_grande_media_luna_evidence_does_not_digitize_report_figures():
    c=load(CANTO); ident=c["bounded_identity_evidence"]
    assert ident["canto_grande_subbasin_officially_named"] is True
    assert ident["media_luna_named_as_separate_ravine"] is True
    assert ident["canto_grande_and_media_luna_described_as_two_main_branches"] is True
    assert ident["media_luna_geometry_reproducible_from_source"] is False
    assert ident["canto_grande_geometry_reproducible_from_source"] is False
    ev=c["bounded_event_evidence"]
    assert ev["event_year"]==2002
    assert ev["component_id"]=="media_luna"
    assert ev["research_state"]=="IMPACT_CONFIRMED"
    assert ev["event_footprint_geometry_available"] is False
    policy=c["local_unit_policy"]
    assert policy["child_evidence_promotes_parent_activation"] is False
    assert policy["synthetic_union_forbidden"] is True
    assert policy["approximate_polygon_from_report_figure_forbidden"] is True
    assert policy["approximate_outlet_from_report_figure_forbidden"] is True

def test_evidence_index_forbids_promotion_side_effects():
    c=load(INDEX)
    assert c["map_effect"]=="NONE_UNTIL_INDEPENDENT_REPRODUCIBLE_CHILD_GEOMETRY_EXISTS"
    assert c["collector_effect"]=="NO_Q_TRAVEL_TIME_ATTENUATION_OR_RECEIVER_RESPONSE_PROMOTION"
    packages={x["path"]:x for x in c["packages"]}
    assert packages["config/phase2_jicamarca_cendehua_event_metadata_v0_1.json"]["may_infer_discharge"] is False
    assert packages["config/phase2_jicamarca_sophy_access_assessment_v0_1.json"]["may_infer_rainfall_before_data_access"] is False
    assert packages["config/phase2_jicamarca_identity_source_assessment_v0_1.json"]["may_create_synthetic_jicamarca_unit"] is False
    assert packages["config/phase2_jicamarca_canto_grande_media_luna_assessment_v0_1.json"]["may_digitize_report_figure_as_geometry"] is False

def test_collector_coupling_remains_unknown_until_reproducible_routing():
    c=load()["collector_coupling"]
    assert c["tributary_activation_implies_receiver_overflow"] is False
    assert c["routing_status"].startswith("BLOCKED_")
    for child in c["children"].values():
        assert child["outlet_or_confluence"] is None
        assert child["Q_i_t"] is None
        assert child["travel_time"] is None
        assert child["attenuation"] is None
        assert child["quality"]=="UNKNOWN"
    assert c["collector_stage_or_discharge_response"] is None
    assert c["peak_coincidence"] is None
    assert c["hydraulic_capacity"] is None
