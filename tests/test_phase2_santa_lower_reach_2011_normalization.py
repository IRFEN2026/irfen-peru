import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/ancash_santa_lower_reach_2011_normalization_v0_1.json"

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


class SantaLowerReach2011NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_phase2_guards_remain_fail_closed(self):
        for key, expected in SAFE.items():
            self.assertEqual(self.doc[key], expected)
        self.assertEqual(self.doc["status"], "RESEARCH_ONLY_SOURCE_NORMALIZATION_CRS_WITHHELD")

    def test_native_axis_is_preserved_but_not_map_geometry(self):
        axis = self.doc["native_axis_points"]
        self.assertEqual(len(axis), 51)
        self.assertEqual(axis[0]["chainage"], "1+000")
        self.assertEqual(axis[-2]["chainage"], "50+000")
        self.assertEqual(axis[-1]["chainage"], "50+000")
        self.assertNotEqual(
            (axis[-2]["easting"], axis[-2]["northing"]),
            (axis[-1]["easting"], axis[-1]["northing"]),
        )
        crs = self.doc["crs_gate"]
        self.assertFalse(crs["explicit_crs_or_datum_verified_in_source_text"])
        self.assertFalse(crs["transformation_to_map_crs_allowed"])
        self.assertFalse(crs["map_eligible"])
        self.assertEqual(crs["status"], "WITHHELD_SOURCE_CRS_NOT_EXPLICITLY_VERIFIED")
        self.assertFalse(self.doc["map_policy"]["native_coordinate_ledger_is_map_geometry"])
        self.assertFalse(self.doc["map_policy"]["publish_to_map"])

    def test_critical_points_are_context_not_event_outcomes(self):
        points = self.doc["critical_points"]
        self.assertEqual(len(points), 24)
        sectors = {x["sector"] for x in points}
        self.assertTrue({"Chingana", "San Bartolo", "Vinzos", "Suchiman", "Tablones"}.issubset(sectors))
        self.assertFalse(self.doc["map_policy"]["critical_point_is_observed_event"])
        self.assertFalse(self.doc["map_policy"]["floodplain_model_is_observed_event_footprint"])

    def test_design_values_are_not_capacity_or_thresholds(self):
        h = self.doc["hydraulic_context"]
        self.assertTrue(h["design_context_only"])
        self.assertEqual(h["stable_width_methods_m"], [122, 162, 208, 228, 142])
        self.assertEqual(h["adopted_average_stable_width_m"], 172)
        self.assertEqual(h["gumbel_design_flows_m3s"]["10_year"], 976)
        self.assertEqual(h["gumbel_design_flows_m3s"]["25_year"], 1177)
        self.assertEqual(h["gumbel_design_flows_m3s"]["50_year"], 1327)
        self.assertFalse(h["provider_values_are_irfen_thresholds"])
        self.assertFalse(h["design_values_are_current_capacity"])
        self.assertFalse(h["works_are_historical_capacity"])
        self.assertFalse(self.doc["map_policy"]["design_flow_is_operational_threshold"])

    def test_source_hash_is_not_invented(self):
        self.assertEqual(self.doc["source"]["source_hash_status"], "NOT_FROZEN_PENDING_ARCHIVE")


if __name__ == "__main__":
    unittest.main()
