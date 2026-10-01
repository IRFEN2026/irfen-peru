import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_santa_eulalia_receiver_chain_v0_1.json"
W1 = ROOT / "site/data/phase2/geometries/w1_santa_eulalia_rimac.geojson"
W1_VALIDATION = ROOT / "site/data/phase2/geometries/w1_santa_eulalia_rimac_validation.json"
SNAPSHOT = ROOT / "site/data/phase2/sources/w1_santa_eulalia_rimac_source_snapshot.json"

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

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def git_blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\\0".encode("ascii") + data).hexdigest()

def test_contract_is_fail_closed():
    doc = load(CONTRACT)
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["parent_role"] == "CONTEXT_CONTAINER_NON_ACTIVATABLE"
    assert doc["parent_activation_state"] is None

def test_pinned_inputs_match_repository_blobs():
    doc = load(CONTRACT)
    actual = {row["path"]: row for row in doc["input_sources"]}
    expected = {
        "site/data/phase2/geometries/w1_santa_eulalia_rimac.geojson": W1,
        "site/data/phase2/geometries/w1_santa_eulalia_rimac_validation.json": W1_VALIDATION,
        "site/data/phase2/sources/w1_santa_eulalia_rimac_source_snapshot.json": SNAPSHOT,
    }
    assert set(actual) == set(expected)
    for path, file_path in expected.items():
        assert actual[path]["git_blob_sha"] == git_blob_sha(file_path)
        assert actual[path]["outcome_source"] is False

def test_fajas_remain_context_not_channel_or_footprint():
    doc = load(CONTRACT)
    w1 = load(W1)
    features = {f["properties"]["unit_id"]: f for f in w1["features"]}
    collectors = {row["collector_id"]: row for row in doc["collector_contexts"]}
    assert features["santa_eulalia_faja_2004"]["properties"]["hydrologic_role"] == "official_river_faja_marginal"
    assert features["rimac_faja_2020"]["properties"]["hydrologic_role"] == "official_river_faja_marginal"
    for row in collectors.values():
        assert row["geometry_ref"]["geometry_role"] == "OFFICIAL_REGULATORY_FAJA_MARGINAL_CONTEXT_NOT_CHANNEL_AXIS"
        assert row["channel_axis_status"] == "MISSING_NOT_INFERRED_FROM_FAJA"
        assert row["exact_confluence_geometry_status"] == "UNRESOLVED"
        assert row["capacity_status"] == "UNKNOWN"
        assert row["counts_as_event_footprint"] is False

def test_source_hashes_are_pinned():
    doc = load(CONTRACT)
    snapshot = load(SNAPSHOT)
    collectors = {row["collector_id"]: row for row in doc["collector_contexts"]}
    assert collectors["santa_eulalia_mainstem_context"]["source_wkt_sha256"] == snapshot["sources"]["ANA-FM-SANTA-EULALIA-6063"]["wkt_sha256"]
    assert collectors["rimac_mainstem_context"]["source_wkt_sha256"] == snapshot["sources"]["ANA-FM-RIMAC-9803"]["wkt_sha256"]

def test_local_units_reach_santa_context_without_exact_confluence_promotion():
    doc = load(CONTRACT)
    validation = load(W1_VALIDATION)
    rows = {row["local_unit_id"]: row for row in doc["local_receiver_chains"]}
    assert set(rows) == {"cashahuacra", "shingolay"}
    for unit_id, row in rows.items():
        assert validation["checks"][unit_id]["downstream_reaches_santa_eulalia_faja"] is True
        assert row["immediate_receiver"] == "santa_eulalia_mainstem_context"
        assert row["immediate_receiver_evidence"]["exact_channel_confluence_confirmed"] is False
        assert row["immediate_receiver_evidence"]["regulatory_faja_is_channel_axis"] is False
        assert row["immediate_receiver_evidence"]["is_receiver_confluence"] is False
        assert row["ultimate_receiver"] == "rimac_mainstem_context"
        assert row["ultimate_receiver_chain_evidence"]["exact_channel_confluence_confirmed"] is False
        assert row["ultimate_receiver_chain_evidence"]["hydraulic_connection_reproduced"] is False
        assert row["collector_effect_state"] == "NO_EVIDENCE"
        for field in ("q_i_t", "travel_time_tau", "routing_method", "attenuation_or_storage", "hydraulic_distance"):
            assert row[field] is None

def test_santa_to_rimac_remains_context_only():
    doc = load(CONTRACT)
    validation = load(W1_VALIDATION)
    chain = doc["collector_chain_context"]
    assert validation["checks"]["santa_eulalia_rimac_intersection_expected_at_confluence"] is True
    assert chain["connectivity_classification"] == "REGULATORY_CORRIDOR_INTERSECTION_CONTEXT_ONLY"
    assert chain["exact_channel_confluence_confirmed"] is False
    assert chain["channel_axis_to_channel_axis_intersection_reproduced"] is False
    assert chain["routing_performed"] is False
    assert chain["receiver_response_observed"] is False
    assert chain["overflow_inferred"] is False

def test_no_fake_map_geometry_or_operational_semantics():
    doc = load(CONTRACT)
    assert doc["map_updates"]["new_geometries_published"] == 0
    assert doc["map_updates"]["new_nodes_published"] == 0
    forbidden = " ".join(doc["forbidden"]).lower()
    assert "faja marginal as channel centreline" in forbidden
    assert "exact surface confluence" in forbidden
    assert "overflow" in forbidden
    assert "travel time" in forbidden
    assert "thresholds" in forbidden
