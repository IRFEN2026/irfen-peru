import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUARMEY = ROOT / "site/data/validation/phase2_discovery_evidence/ancash_huarmey_initial_context_2017_2026.json"
CHICAMA = ROOT / "site/data/validation/phase2_discovery_evidence/lalibertad_chicama_initial_context_2010_2026.json"

class NorthCoastInitialEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.huarmey = json.loads(HUARMEY.read_text(encoding="utf-8"))
        cls.chicama = json.loads(CHICAMA.read_text(encoding="utf-8"))

    def _assert_closed(self, e):
        self.assertEqual(e["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(e["test_mode"], "TEST_ONLY")
        self.assertFalse(e["production_use"])
        self.assertFalse(e["production_ready"])
        self.assertFalse(e["operational_alerting_enabled"])
        self.assertEqual(e["activation_gate"], "BLOCKED")
        self.assertIsNone(e["decision_thresholds"])
        self.assertIsNone(e["hydraulic_factors"])

    def test_both_evidence_packages_remain_fail_closed(self):
        self._assert_closed(self.huarmey)
        self._assert_closed(self.chicama)

    def test_huarmey_and_culebras_are_not_merged(self):
        sep = self.huarmey["component_separation"]
        self.assertTrue(sep["rio_huarmey_distinct_component"])
        self.assertTrue(sep["rio_culebras_distinct_component"])
        self.assertFalse(sep["combined_geometry_allowed"])
        self.assertFalse(sep["cross_basin_hydraulic_transfer_validated"])

    def test_huarmey_critical_points_are_context_not_events(self):
        ctx = self.huarmey["critical_point_context"]["ana_2021"]
        self.assertEqual(ctx["rio_huarmey_points_reported"], 6)
        self.assertEqual(ctx["rio_culebras_points_reported"], 2)
        self.assertEqual(ctx["role"], "CRITICAL_POINT_CONTEXT_NOT_EVENT_COUNT")

    def test_chicama_hydraulic_study_is_not_threshold(self):
        h = self.chicama["hydraulic_context"]
        self.assertEqual(h["role"], "HISTORICAL_HYDRAULIC_STUDY_CONTEXT_NOT_IRFEN_THRESHOLD")
        self.assertFalse(h["native_model_files_verified"])
        self.assertIsNone(self.chicama["decision_thresholds"])

    def test_chicama_river_and_ravines_stay_separate(self):
        sep = self.chicama["component_separation"]
        self.assertTrue(sep["rio_chicama_distinct_component"])
        self.assertTrue(sep["named_ravines_distinct_components"])
        self.assertFalse(sep["ravine_to_river_event_routing_validated"])
        self.assertFalse(sep["current_intervention_state_is_historical_capacity"])

if __name__ == "__main__":
    unittest.main()
