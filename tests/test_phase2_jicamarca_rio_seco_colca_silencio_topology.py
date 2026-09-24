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


def test_colca_el_silencio_and_rio_seco_remain_separate_local_components():
    doc = load()
    adj = doc["cross_source_adjudication"]
    assert adj["adjudication"] == "KEEP_COLCA_EL_SILENCIO_AND_RIO_SECO_AS_DISTINCT_LOCAL_COMPONENTS_WHILE_TREATING_THE_ANA_CONFLUENCE_RELATION_AS_DOCUMENTARY_TOPOLOGY_ONLY"
    assert adj["crosswalk_status"] == "PARTIAL_DOCUMENTARY_RELATION_NOT_GEOMETRY_CROSSWALK"
    assert adj["silent_component_collapse_allowed"] is False
    assert adj["frozen_colca_faja_may_be_rebound_to_rio_seco"] is False
    children = {c["child_id"]: c for c in doc["local_hierarchy"]["children"]}
    assert set(children) == {"colca", "el_silencio", "rio_seco"}
    assert children["colca"]["geometry_semantics"] == "QDA_COLCA_REGULATORY_CONTEXT_ONLY"
    assert children["colca"]["activation_geometry"] is False
    assert children["el_silencio"]["geometry_status"].startswith("MISSING_")
    assert children["rio_seco"]["geometry_status"].startswith("MISSING_")


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


def test_next_gate_requires_explicit_component_table_labels_before_geometry():
    doc = load()
    findings = doc["bounded_documentary_findings"]
    assert findings["hydrographic_system_reported_as_ten_tramos"] is True
    assert findings["colca_el_silencio_confluence_relation_documented"] is True
    assert findings["exact_confluence_coordinate_documented_in_bounded_text"] is False
    assert findings["exact_table_to_component_crosswalk_resolved"] is False
    assert findings["frozen_270_hito_table_label_in_existing_archive"] == "Qda. Colca"
    gates = " ".join(doc["next_gate"])
    assert "ten-tramo" in gates
    assert "explicit source label" in gates
