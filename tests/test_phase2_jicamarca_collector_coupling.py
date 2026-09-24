import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_jicamarca_collector_coupling_v0_1.json"
DISCOVERY = ROOT / "config/phase2_jicamarca_discovery_v0_1.json"
ARCH = ROOT / "config/phase2_collector_coupling_architecture_v0_1.json"
HIER = ROOT / "config/phase2_local_activation_hierarchy_v0_1.json"
MONITORING_TOPOLOGY = "config/phase2_jicamarca_rio_seco_huaycoloro_monitoring_topology_v0_1.json"

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


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_contract_and_upstream_architecture_exist_and_are_safe():
    doc = load(CONTRACT)
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert ARCH.exists()
    assert HIER.exists()
    assert DISCOVERY.exists()
    assert doc["architecture_ref"] == "config/phase2_collector_coupling_architecture_v0_1.json"
    assert doc["local_hierarchy_ref"] == "config/phase2_local_activation_hierarchy_v0_1.json"
    assert doc["discovery_ref"] == "config/phase2_jicamarca_discovery_v0_1.json"


def test_parent_is_context_only_and_synthetic_jicamarca_activation_is_forbidden():
    doc = load(CONTRACT)
    parent = doc["parent_context"]
    assert parent["role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert parent["activation_state"] is None
    assert parent["child_evidence_promotes_parent_activation"] is False
    assert parent["synthetic_jicamarca_activation_unit_allowed"] is False
    forbidden = " ".join(doc["forbidden"]).lower()
    assert "synthetic quebrada jicamarca" in forbidden
    assert "parent activation" in forbidden


def test_local_children_remain_separate_and_huaycoloro_is_reference_only():
    doc = load(CONTRACT)
    rows = {r["local_unit_id"]: r for r in doc["tributaries"]}
    assert set(rows) == {
        "huaycoloro",
        "rio_seco",
        "canto_grande_upper_branch",
        "media_luna",
        "jicamarca_named_channel",
    }
    assert rows["huaycoloro"]["source_local_geometry_contract_or_explicit_missing_status"] == "EXISTING_IRFEN_REFERENCE:chosica_huaycoloro"
    assert rows["huaycoloro"]["source_geometry_status"] == "REFERENCE_ONLY_NOT_DUPLICATED"
    assert rows["rio_seco"]["source_geometry_status"] == "MISSING_PENDING_INDEPENDENT_RIO_SECO_GEOMETRY"
    assert rows["rio_seco"]["source_local_geometry_contract_or_explicit_missing_status"]["quarantined_geometry"] == "ANA_QDA_COLCA_FAJA_DO_NOT_USE_AS_RIO_SECO"
    assert rows["jicamarca_named_channel"]["source_geometry_status"] == "MISSING_PENDING_IDENTITY_RESOLUTION"


def test_no_outlet_is_inferred_from_station_labels_or_channel_endpoints():
    doc = load(CONTRACT)
    rows = {r["local_unit_id"]: r for r in doc["tributaries"]}
    assert rows["rio_seco"]["source_outlet_or_explicit_missing_status"]["station_labels_are_outlets"] is False
    assert rows["canto_grande_upper_branch"]["source_outlet_or_explicit_missing_status"]["channel_endpoint_is_outlet"] is False
    assert rows["media_luna"]["source_outlet_or_explicit_missing_status"]["channel_endpoint_is_outlet"] is False
    for row in rows.values():
        status = row["source_outlet_or_explicit_missing_status"]
        if isinstance(status, dict) and "location" in status:
            assert status["location"] is None


def test_temporal_and_hydraulic_quantities_remain_null_until_reproducible_inputs_exist():
    doc = load(CONTRACT)
    for row in doc["tributaries"]:
        assert row["q_i_t"] is None
        assert row["travel_time_tau"] is None
        assert row["routing_method"] is None
        assert row["attenuation_or_storage"] is None
        assert row["hydraulic_distance"] is None
        assert row["collector_effect_state"] == "NO_EVIDENCE"
    for cell in doc["collector_coupling_matrix"]:
        assert cell["q_i_t"] is None
        assert cell["travel_time_tau"] is None
        assert cell["attenuation_or_storage"] is None
        assert cell["collector_effect_state"] == "NO_EVIDENCE"
        assert cell["validation_status"] == "BLOCKED"
    assert doc["collector_balance_status"]["calculation_performed"] is False
    assert doc["collector_balance_status"]["downstream_flow_estimate"] is None
    assert doc["hydrologic_routing"]["method"] is None
    assert doc["hydraulic_model"]["method"] is None


def test_same_day_2023_sensor_detections_are_not_peak_coincidence_or_rimac_overflow():
    doc = load(CONTRACT)
    pairing = doc["event_pairing_gate"]["same_day_direct_flow_records"][0]
    assert pairing["date"] == "2023-03-15"
    assert set(pairing["records"]) == {
        "IGP-HL2-2023-03-15T14:44:19-05:00",
        "IGP-RS2-2023-03-15T16:27:41-05:00",
    }
    assert pairing["peak_coincidence_inferred"] is False
    assert pairing["shared_routing_basis_available"] is False
    assert pairing["receiver_response_observed"] is False
    assert pairing["may_infer_rimac_overflow"] is False
    valle = doc["event_pairing_gate"]["valle_sagrado_2023"]
    assert valle["research_state"] == "IMPACT_CONFIRMED"
    assert valle["local_component_attribution"] == "PARTIAL_UNRESOLVED"
    assert valle["may_feed_back_to_geometry_selection"] is False
    assert valle["may_imply_rimac_overflow"] is False


def test_media_luna_documentary_topology_does_not_become_exact_confluence():
    doc = load(CONTRACT)
    rows = {r["local_unit_id"]: r for r in doc["tributaries"]}
    media = rows["media_luna"]
    assert media["immediate_receiver"] == "canto_grande_local_receiver"
    assert media["receiver_confluence_or_explicit_missing_status"]["status"] == "DOCUMENTARY_TOPOLOGY_TO_CANTO_GRANDE_EXACT_JUNCTION_UNRESOLVED"
    assert media["receiver_confluence_or_explicit_missing_status"]["location"] is None
    matrix = {(r["local_unit_id"], r["collector_id"]): r for r in doc["collector_coupling_matrix"]}
    cell = matrix[("media_luna", "canto_grande_local_receiver")]
    assert cell["connectivity"] == "DOCUMENTARY_TOPOLOGY_ONLY_EXACT_NODE_UNRESOLVED"
    assert cell["validation_status"] == "BLOCKED"


def test_map_semantics_do_not_promote_risk_or_new_fake_geometry():
    doc = load(CONTRACT)
    rimac = next(c for c in doc["collector_targets"] if c["collector_id"] == "rimac_mainstem_receiver")
    assert rimac["geometry"] is None
    assert rimac["map_eligible"] is False
    assert rimac["capacity_status"] == "UNKNOWN"
    canto = next(c for c in doc["collector_targets"] if c["collector_id"] == "canto_grande_local_receiver")
    assert canto["geometry_role"] == "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"
    assert canto["activation_state"] is None
    assert (ROOT / canto["geometry"]).exists()


def test_monitored_rio_seco_huaycoloro_topology_is_traceable_but_does_not_promote_coupling():
    doc = load(CONTRACT)
    assert doc["monitoring_topology_ref"] == MONITORING_TOPOLOGY
    topology = ROOT / MONITORING_TOPOLOGY
    assert topology.is_file()
    monitored = load(topology)
    for key, expected in SAFE.items():
        assert monitored[key] == expected
    rows = {r["local_unit_id"]: r for r in doc["tributaries"]}
    for child in ("huaycoloro", "rio_seco"):
        node = rows[child]["receiver_confluence_or_explicit_missing_status"]
        assert MONITORING_TOPOLOGY in node["provenance"]
        assert node["location"] is None
        assert node["is_receiver_confluence"] is False
        assert rows[child]["ultimate_receiver_connection_status"] == "UNRESOLVED_NOT_ASSUMED"
        assert rows[child]["q_i_t"] is None
        assert rows[child]["travel_time_tau"] is None
        assert rows[child]["attenuation_or_storage"] is None
    adjudication = monitored["cross_source_adjudication"]
    assert adjudication["exact_confluence_coordinate"] is None
    assert adjudication["exact_confluence_geometry_resolved"] is False
    assert adjudication["downstream_receiver_identity_resolved_by_this_package"] is False
    assert adjudication["rimac_connection_resolved_by_this_package"] is False
    assert adjudication["receiver_overflow_inferred"] is False
