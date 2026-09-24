import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_jicamarca_rio_seco_huaycoloro_monitoring_topology_v0_1.json"
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


def load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_documentary_topology_contract_is_fail_closed():
    doc = load()
    for key, expected in SAFE.items():
        assert doc[key] == expected
    adjudication = doc["cross_source_adjudication"]
    assert adjudication["rio_seco_and_huaycoloro_are_distinct_local_children"] is True
    assert adjudication["documentary_convergence_supported_by_two_igp_public_sources"] is True
    assert adjudication["synthetic_queberada_jicamarca_created"] is False
    assert adjudication["exact_confluence_coordinate"] is None
    assert adjudication["exact_confluence_geometry_resolved"] is False
    assert adjudication["downstream_receiver_identity_resolved_by_this_package"] is False
    assert adjudication["rimac_connection_resolved_by_this_package"] is False
    assert adjudication["map_geometry_created"] is False
    assert adjudication["parent_activation_promoted"] is False
    assert adjudication["receiver_overflow_inferred"] is False


def test_children_remain_separate_and_huaycoloro_is_reused_by_reference():
    doc = load()
    children = {row["component_id"]: row for row in doc["local_hierarchy"]["children"]}
    assert set(children) == {"rio_seco", "huaycoloro"}
    rio = children["rio_seco"]
    assert rio["channel_geometry"] is None
    assert rio["catchment_polygon"] is None
    assert rio["outlet"] is None
    assert rio["confluence"] is None
    assert rio["Q_i_t"] is None
    assert rio["travel_time"] is None
    assert rio["attenuation"] is None
    huay = children["huaycoloro"]
    assert huay["existing_pilot_reference"] == "chosica_huaycoloro"
    assert huay["Q_i_t"] is None
    assert huay["travel_time"] is None
    assert huay["attenuation"] is None


def test_documentary_convergence_does_not_enable_routing_or_receiver_overflow():
    doc = load()
    coupling = doc["collector_coupling"]
    edges = coupling["topology_edges"]
    assert {(e["from_component"], e["to_node"]) for e in edges[:2]} == {
        ("rio_seco", "rio_seco_huaycoloro_local_confluence"),
        ("huaycoloro", "rio_seco_huaycoloro_local_confluence"),
    }
    for edge in edges:
        assert edge["node_coordinate"] is None
        assert edge["routing_enabled"] is False
        assert edge["Q_i_t"] is None
        assert edge["travel_time"] is None
        assert edge["attenuation"] is None
    assert coupling["peak_coincidence"] is None
    assert coupling["hydraulic_capacity"] is None
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
    assert coupling["provider_station_activity_may_set_Q_i_t"] is False
    assert coupling["monitoring_point_spacing_may_set_travel_time"] is False
    assert coupling["communications_distance_may_set_routing_distance"] is False


def test_map_policy_forbids_approximate_confluence_or_new_geometry():
    policy = load()["map_policy"]
    assert policy["publish_new_geometry"] is False
    assert policy["publish_confluence_node"] is False
    assert policy["publish_approximate_point"] is False
    assert policy["publish_parent_composite"] is False
    assert policy["risk_or_alert_coloring"] is False


def test_sources_are_bounded_and_do_not_claim_byte_freeze():
    sources = load()["sources"]
    assert {row["source_id"] for row in sources} == {
        "IGP-REPOSITORY-JICAMARCA-SAT-DESIGN",
        "IGP-JRO-OFFICIAL-ABOUT",
    }
    for row in sources:
        assert row["url"].startswith("https://")
        assert row["source_bytes_sha256"] is None
        assert "NOT_BYTE_FROZEN" in row["source_archive_status"]
        assert row["forbidden_interpretations"]
