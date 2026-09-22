import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/canete_official_geometry_hydraulic_context_2025_2026.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_canete.json"

class CaneteResearchContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_guardrails_remain_closed(self):
        e = self.evidence
        c = self.contract
        self.assertEqual(e["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(e["test_mode"], "TEST_ONLY")
        self.assertFalse(e["production_use"])
        self.assertFalse(e["production_ready"])
        self.assertFalse(e["operational_alerting_enabled"])
        self.assertIsNone(e["decision_thresholds"])
        self.assertEqual(e["activation_gate"], "BLOCKED")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")

    def test_regulatory_geometries_are_bounded(self):
        s = self.evidence["spatial_context"]
        self.assertEqual(s["rio_canete_rd0858_2025"]["length_km"], 17.2)
        self.assertEqual(s["rio_canete_rd0858_2025"]["georeferenced_markers_total"], 122)
        self.assertEqual(s["rio_canete_huallampi_rd0274_2025"]["georeferenced_markers_total"], 35)
        self.assertEqual(s["jacayita_rd0396_2025"]["main_channel_markers_total"], 43)
        self.assertIn("NOT_EVENT_FOOTPRINT", s["rio_canete_rd0858_2025"]["role"])
        self.assertIn("NOT_EVENT_FOOTPRINT", s["jacayita_rd0396_2025"]["role"])

    def test_river_and_ravines_remain_separate(self):
        sep = self.evidence["component_separation"]
        self.assertTrue(sep["rio_canete_distinct_component"])
        self.assertTrue(sep["named_ravines_distinct_components"])
        self.assertFalse(sep["river_ravine_cross_routing_validated"])
        self.assertFalse(sep["whole_basin_machine_readable_geometry_normalized"])

    def test_only_bounded_assets_advance(self):
        c = self.contract["assets"]
        self.assertEqual(c["geometry"]["status"], "PARTIAL")
        self.assertIsNone(c["geometry"]["path"])
        self.assertEqual(c["exposure"]["status"], "PARTIAL")
        self.assertEqual(c["hydraulic_context"]["status"], "PARTIAL")
        self.assertEqual(c["historical_events"]["status"], "MISSING")
        self.assertEqual(c["observations"]["status"], "MISSING")
        self.assertEqual(c["forecast"]["status"], "CANDIDATE")

    def test_current_mitigation_is_not_backcast(self):
        r = self.evidence["current_mitigation_context"]["ramadilla_2025"]
        self.assertFalse(r["historical_backcast_allowed"])
        self.assertFalse(r["observed_capacity_inference_allowed"])

    def test_no_threshold_or_negative_control_fabrication(self):
        forbidden = set(self.evidence["forbidden_uses"])
        self.assertIn("operational threshold derivation", forbidden)
        self.assertIn("negative-control inference from missing reports", forbidden)
        self.assertFalse(self.evidence["observations_status"]["verified_negative_controls_available"])

if __name__ == "__main__":
    unittest.main()
