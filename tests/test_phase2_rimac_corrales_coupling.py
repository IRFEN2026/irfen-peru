import json
import re
import unittest
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


class TestRimacCorralesStaticCoupling(unittest.TestCase):
    def test_corrales_contract_is_fail_closed_and_static_only(self):
        doc = load(CONTRACT)
        for key, expected in SAFE.items():
            self.assertEqual(doc[key], expected)
        self.assertEqual(doc["parent_id"], "lima_este_santa_eulalia_rimac")
        self.assertEqual(doc["local_unit_id"], "corrales")
        self.assertEqual(doc["territorial_target_label"], "rayos_de_sol")
        self.assertEqual(doc["source_ref"], "agent/chosica-2015-multibasin-v0.1")
        self.assertEqual(doc["collector_id"], "rimac_mainstem_receiver")
        self.assertEqual(doc["collector_effect_state"], "HYDROLOGICALLY_CONNECTED")
        self.assertIsNone(doc["q_i_t"])
        self.assertIsNone(doc["travel_time_tau"])
        self.assertIsNone(doc["routing_method"])
        self.assertIsNone(doc["attenuation_or_storage"])
        self.assertEqual(doc["capacity_status"], "UNKNOWN")
        self.assertFalse(doc["receiver_response_observed"])

    def test_source_artifacts_are_exactly_pinned(self):
        doc = load(CONTRACT)
        self.assertEqual(doc["source_artifacts"], EXPECTED_BLOBS)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in doc["source_artifacts"].values()))

    def test_static_anchor_and_d8_intersection_coordinates_are_frozen(self):
        doc = load(CONTRACT)
        self.assertEqual(doc["static_anchor"], {
            "lon": -76.68075049654043,
            "lat": -11.922865103815958,
        })
        node = doc["receiver_intersection"]
        self.assertEqual(node["lon"], -76.68083293)
        self.assertEqual(node["lat"], -11.92442315)
        self.assertEqual(node["classification"], "REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION")
        self.assertFalse(node["official_surface_confluence_confirmed"])

    def test_map_nodes_are_context_only_and_not_alerts_or_event_footprints(self):
        geo = load(NODES)
        props = geo["properties"]
        for key, expected in SAFE.items():
            self.assertEqual(props[key], expected)
        self.assertFalse(props["default_visibility"])
        self.assertFalse(props["carries_risk_classification"])
        self.assertFalse(props["carries_alert_values"])
        self.assertFalse(props["counts_as_event_footprint"])
        self.assertFalse(props["counts_as_complete_candidate_geometry"])

        features = {f["properties"]["unit_id"]: f for f in geo["features"]}
        self.assertEqual(set(features), {
            "corrales_r5_channel_anchor",
            "corrales_rimac_d8_intersection",
        })
        self.assertEqual(features["corrales_r5_channel_anchor"]["geometry"], {
            "type": "Point",
            "coordinates": [-76.68075049654043, -11.922865103815958],
        })
        intersection = features["corrales_rimac_d8_intersection"]
        self.assertEqual(intersection["geometry"], {
            "type": "Point",
            "coordinates": [-76.68083293, -11.92442315],
        })
        ip = intersection["properties"]
        self.assertEqual(ip["collector_effect_state"], "HYDROLOGICALLY_CONNECTED")
        self.assertFalse(ip["official_surface_confluence_confirmed"])
        self.assertEqual(ip["source_blob_sha"], EXPECTED_BLOBS["outlet_candidate_blob"])

    def test_rayos_de_sol_remains_territorial_label_not_hydrologic_unit(self):
        doc = load(CONTRACT)
        self.assertEqual(doc["local_unit_id"], "corrales")
        self.assertEqual(doc["territorial_target_label"], "rayos_de_sol")
        geo = load(NODES)
        for feature in geo["features"]:
            props = feature["properties"]
            self.assertEqual(props["hydrologic_unit_id"], "corrales")
            self.assertEqual(props["territorial_target_label"], "rayos_de_sol")


if __name__ == "__main__":
    unittest.main()
