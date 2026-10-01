"""Source-reported numbers in Rimac/Jicamarca context contracts stay provenance.

ANIN reports a 10.5 km engineered Huaycoloro channel; SENAMHI 2023 reports
75.48 m3/s at Chosica and >100 m3/s downstream. None of these may become a
capacity, threshold, routing input, travel time or receiver response.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANIN = ROOT / "config/phase2_anin2023_2026_huaycoloro_engineered_channel_context_v0_1.json"
SENAMHI = ROOT / "config/phase2_senamhi2023_rimac_downstream_hazard_context_v0_1.json"
GUARDS = {
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


class TestContextNumericGuards(unittest.TestCase):
    def test_guards(self):
        for path in (ANIN, SENAMHI):
            doc = load(path)
            for key, value in GUARDS.items():
                self.assertEqual(doc[key], value, f"{path.name}:{key}")

    def test_anin_engineered_channel_is_not_capacity_or_geometry(self):
        doc = load(ANIN)
        hyd = doc["hydraulic_adjudication"]
        self.assertEqual(hyd["observed_capacity"], "UNKNOWN")
        self.assertEqual(hyd["overflow_state"], "UNKNOWN")
        for key in ("design_capacity", "discharge_threshold", "stage_threshold",
                    "travel_time_tau", "q_i_t", "receiver_response"):
            self.assertIsNone(hyd[key], key)
        for key in ("design_intent_establishes_observed_capacity", "completion_establishes_observed_capacity",
                    "reported_protection_objective_establishes_no_overflow_guarantee", "routing_enabled"):
            self.assertIs(hyd[key], False, key)
        geo = doc["temporal_geometry_adjudication"]
        self.assertIsNone(geo["exact_post_work_channel_axis_geometry"])
        self.assertIs(geo["map_publish_enabled_from_this_contract"], False)
        self.assertTrue(all(value is False for value in doc["guards"].values()))
        self.assertEqual(doc["map_updates"]["new_geometries_published"], 0)

    def test_senamhi_2023_discharge_is_observation_not_parameter(self):
        doc = load(SENAMHI)
        obs = doc["mainstem_observation"]
        self.assertEqual(obs["reported_discharge_m3_s"], 75.48)
        self.assertIs(obs["official_level_is_irfen_decision_threshold"], False)
        agg = doc["downstream_aggregate_context"]
        self.assertIs(agg["individual_quebrada_contributions_available"], False)
        for key in ("individual_quebrada_q_i_t", "travel_time_tau", "routing_method"):
            self.assertIsNone(agg[key], key)
        self.assertIs(agg["may_calibrate_child_to_receiver_transfer"], False)
        self.assertIs(agg["may_be_used_as_receiver_capacity"], False)
        adj = doc["adjudication"]
        self.assertIs(adj["supports_general_downstream_quebrada_to_rimac_contribution_context"], True)
        for key, value in adj.items():
            if key != "supports_general_downstream_quebrada_to_rimac_contribution_context":
                self.assertIs(value, False, key)
        self.assertEqual(doc["map_updates"]["new_geometries_published"], 0)


if __name__ == "__main__":
    unittest.main()
