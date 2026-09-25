import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_rimac_corrales_coupling_v0_1.json"
NODES = ROOT / "site/data/phase2/geometries/rimac_corrales_coupling_nodes_v0_1.geojson"

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

EXPECTED_BLOBS = {
    "anchor_registry_blob": "b1ab25c5f2ca06e29e0b712a6a709924d8dbb8a5",
    "method_contract_blob": "1bad9f05d36f405f477e6fb5e392c736a5447bd0",
    "outlet_candidate_blob": "b80f6f314e3f7759dbd41b5dc1250f2b473c2414",
    "catchment_report_blob": "7eb9e21d470b2a1c0943d7f448f195a3d28ddb50",
    "freeze_registry_blob": "d2577c4dfd81fdd8ee372e16277054006b28c079",
}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_corrales_contract_is_fail_closed_and_static_only():
    doc = load(CONTRACT)
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["parent_id"] == "lima_este_santa_eulalia_rimac"
    assert doc["local_unit_id"] == "corrales"
    assert doc["territorial_target_label"] == "rayos_de_sol"
    assert doc["source_ref"] == "agent/chosica-2015-multibasin-v0.1"
    assert doc["collector_id"] == "rimac_mainstem_receiver"
    assert doc["collector_effect_state"] == "HYDROLOGICALLY_CONNECTED"
    assert doc["q_i_t"] is None
    assert doc["travel_time_tau"] is None
    assert doc["routing_method"] is None
    assert doc["attenuation_or_storage"] is None
    assert doc["capacity_status"] == "UNKNOWN"
    assert doc["receiver_response_observed"] is False

def test_source_artifacts_are_exactly_pinned():
    doc = load(CONTRACT)
    assert doc["source_artifacts"] == EXPECTED_BLOBS
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in doc["source_artifacts"].values())

def test_static_anchor_and_d8_intersection_coordinates_are_frozen():
    doc = load(CONTRACT)
    assert doc["static_anchor"] == {
        "lon": -76.68075049654043,
        "lat": -11.922865103815958,
    }
    node = doc["receiver_intersection"]
    assert node["lon"] == -76.68083293
    assert node["lat"] == -11.92442315
    assert node["classification"] == "REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION"
    assert node["official_surface_confluence_confirmed"] is False

def test_map_nodes_are_context_only_and_not_alerts_or_event_footprints():
    geo = load(NODES)
    props = geo["properties"]
    for key, expected in SAFE.items():
        assert props[key] == expected
    assert props["default_visibility"] is False
    assert props["carries_risk_classification"] is False
    assert props["carries_alert_values"] is False
    assert props["counts_as_event_footprint"] is False
    assert props["counts_as_complete_candidate_geometry"] is False

    features = {f["properties"]["unit_id"]: f for f in geo["features"]}
    assert set(features) == {
        "corrales_r5_channel_anchor",
        "corrales_rimac_d8_intersection",
    }
    anchor = features["corrales_r5_channel_anchor"]
    assert anchor["geometry"] == {
        "type": "Point",
        "coordinates": [-76.68075049654043, -11.922865103815958],
    }
    intersection = features["corrales_rimac_d8_intersection"]
    assert intersection["geometry"] == {
        "type": "Point",
        "coordinates": [-76.68083293, -11.92442315],
    }
    ip = intersection["properties"]
    assert ip["collector_effect_state"] == "HYDROLOGICALLY_CONNECTED"
    assert ip["official_surface_confluence_confirmed"] is False
    assert ip["source_blob_sha"] == EXPECTED_BLOBS["outlet_candidate_blob"]

def test_rayos_de_sol_remains_territorial_label_not_hydrologic_unit():
    doc = load(CONTRACT)
    assert doc["local_unit_id"] == "corrales"
    assert doc["territorial_target_label"] == "rayos_de_sol"
    geo = load(NODES)
    for feature in geo["features"]:
        props = feature["properties"]
        assert props["hydrologic_unit_id"] == "corrales"
        assert props["territorial_target_label"] == "rayos_de_sol"
