import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_jicamarca_rio_seco_colca_silencio_topology_v0_1.json"


def load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_phase2_scientific_guards_remain_fail_closed():
    doc = load()
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_mode"] == "TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None


def test_ten_tramo_inventory_is_frozen_by_explicit_source_label():
    doc = load()
    findings = doc["bounded_documentary_findings"]
    assert findings["hydrographic_system_reported_as_ten_tramos"] is True
    assert findings["summary_tramo_inventory_resolved"] is True
    assert findings["summary_tramo_count"] == 10
    assert findings["main_summary_tramo_label"] == "Qda Colca"
    assert findings["rio_seco_specific_summary_tramo_present"] is False
    assert findings["rio_seco_specific_segment_crosswalk_resolved"] is False
    assert findings["generic_resolution_scope_label_may_override_component_table_label"] is False
    assert findings["frozen_270_hito_table_label_in_existing_archive"] == "Qda. Colca"

    rows = doc["official_tramo_inventory"]
    assert len(rows) == 10
    assert [row["tramo_index"] for row in rows] == list(range(1, 11))
    assert rows[0]["source_label"] == "Qda Colca"
    assert rows[0]["reported_length_km"] == 26.0
    assert rows[0]["reported_hitos_total"] == 270
    assert rows[0]["is_independently_labelled_rio_seco"] is False
    assert not any(row["is_independently_labelled_rio_seco"] for row in rows)
    assert not any(row["source_label"].casefold().strip() == "rio seco" for row in rows)

    families = [row["component_family"] for row in rows]
    assert families.count("colca") == 7
    assert families.count("el_silencio") == 3
    assert doc["inventory_interpretation"]["rio_seco_family_explicit_tramo_count"] == 0


def test_el_silencio_and_colca_branches_remain_independent_source_rows():
    rows = load()["official_tramo_inventory"]
    labels = {row["source_label"] for row in rows}
    assert labels == {
        "Qda Colca",
        "Qda. El Silencio",
        "Qda. El Silencio 01",
        "Qda. El Silencio 02",
        "Qda. Colca Derecha 01",
        "Qda. Colca Izquierda 01",
        "Qda. Colca Izquierda 02",
        "Qda. Colca Izquierda 03",
        "Qda. Colca Izquierda 04",
        "Qda. Colca Izquierda 05",
    }
    silencio_02 = next(row for row in rows if row["source_label"] == "Qda. El Silencio 02")
    assert silencio_02["reported_hitos_total"] is None
    assert silencio_02["reported_hitos_right_margin"] is None
    assert silencio_02["reported_hitos_left_margin"] is None
    assert silencio_02["hito_count_parse_status"] == "AMBIGUOUS_PDF_TABLE_LAYOUT_NOT_FROZEN"
    assert load()["inventory_interpretation"]["summary_rows_are_not_event_footprints"] is True
    assert load()["inventory_interpretation"]["table_start_end_coordinates_are_not_outlets_or_confluences"] is True


def test_colca_el_silencio_and_rio_seco_remain_separate_local_components():
    doc = load()
    adj = doc["cross_source_adjudication"]
    assert adj["adjudication"] == "KEEP_COLCA_EL_SILENCIO_AND_RIO_SECO_AS_DISTINCT_LOCAL_COMPONENTS_WHILE_TREATING_THE_ANA_CONFLUENCE_RELATION_AS_DOCUMENTARY_TOPOLOGY_ONLY"
    assert adj["crosswalk_status"] == "TEN_TRAMO_COMPONENT_LABELS_FROZEN_NO_EXPLICIT_RIO_SECO_TRAMO_CROSSWALK"
    assert adj["silent_component_collapse_allowed"] is False
    assert adj["frozen_colca_faja_may_be_rebound_to_rio_seco"] is False
    children = {c["child_id"]: c for c in doc["local_hierarchy"]["children"]}
    assert set(children) == {"colca", "el_silencio", "rio_seco"}
    assert children["colca"]["geometry_semantics"] == "QDA_COLCA_REGULATORY_CONTEXT_ONLY"
    assert children["colca"]["activation_geometry"] is False
    assert children["el_silencio"]["geometry_status"] == "EXPLICIT_ANA_SUMMARY_IDENTITY_AVAILABLE_FULL_COORDINATE_LEDGER_PENDING_FREEZE"
    assert children["el_silencio"]["activation_geometry"] is False
    assert children["rio_seco"]["geometry_status"] == "MISSING_NO_EXPLICIT_RIO_SECO_TRAMO_IN_ANA_TEN_TRAMO_SUMMARY"
    assert children["rio_seco"]["activation_geometry"] is False


def test_documentary_topology_cannot_invent_geometry_or_routing():
    doc = load()
    relation = doc["local_hierarchy"]["documentary_relation"]
    assert relation["node_coordinate"] is None
    assert relation["geometry_resolved"] is False
    assert relation["routing_resolved"] is False
    assert relation["children_may_be_union_geometry"] is False
    assert relation["child_evidence_promotes_parent_activation"] is False
    coupling = doc["collector_coupling"]
    assert coupling["rimac_mainstem_connection"] == "UNRESOLVED_NOT_ASSUMED"
    assert coupling["hydraulic_capacity"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
    for key in ("colca_to_local_confluence", "el_silencio_to_local_confluence"):
        row = coupling[key]
        assert row["outlet_or_confluence"] is None
        assert row["Q_i_t"] is None
        assert row["travel_time"] is None
        assert row["attenuation"] is None
        assert row["quality"] == "UNKNOWN"
    rio = coupling["rio_seco_downstream_relation"]
    assert rio["channel_geometry"] is None
    assert rio["Q_i_t"] is None
    assert rio["travel_time"] is None
    assert rio["attenuation"] is None


def test_map_remains_context_only_and_no_new_geometry_is_published():
    doc = load()
    policy = doc["map_policy"]
    assert policy["new_geometry_published_by_this_package"] is False
    assert policy["publish_colca_faja_as_rio_seco"] is False
    assert policy["publish_el_silencio_before_reproducible_geometry"] is False
    assert policy["publish_rio_seco_before_reproducible_geometry"] is False
    assert policy["publish_confluence_as_approximate_point"] is False
    assert policy["parent_jicamarca_risk_or_alert_symbology_allowed"] is False
    assert policy["risk_or_alert_symbology_allowed"] is False


def test_next_gate_advances_to_full_ledgers_and_independent_rio_seco_geometry():
    doc = load()
    gates = " ".join(doc["next_gate"])
    assert "complete coordinate ledgers" in gates
    assert "Qda. El Silencio" in gates
    assert "CENDEHUA-monitored Río Seco" in gates
    assert "no independently labelled Río Seco tramo" in gates
    assert "extract and freeze the complete ten-tramo ANA table inventory" not in gates
