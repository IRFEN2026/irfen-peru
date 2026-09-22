import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/acari_official_risk_geodynamic_context_2014_2025.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/arequipa_acari_san_agustin.json"

class AcariResearchContextTests(unittest.TestCase):
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

    def test_ana_counts_are_not_conflated_with_acari_district(self):
        ctx = self.evidence["official_context"]["ana_2024"]
        self.assertEqual(ctx["total_critical_points_reported"], 24)
        self.assertEqual(ctx["very_high_risk_points_reported"], 6)
        self.assertEqual(ctx["acari_high_risk_points_reported"], 10)
        self.assertIn("not equivalent", ctx["assessment_scope"])

    def test_san_agustin_is_not_invented(self):
        sep = self.evidence["component_separation"]
        self.assertFalse(sep["quebrada_san_agustin_geometry_resolved"])
        self.assertFalse(sep["quebrada_san_agustin_hydraulic_identity_resolved"])
        self.assertFalse(sep["river_to_ravine_routing_validated"])
        self.assertEqual(self.contract["assets"]["geometry"]["status"], "MISSING")

    def test_only_bounded_assets_advance(self):
        c = self.contract["assets"]
        self.assertEqual(c["exposure"]["status"], "PARTIAL")
        self.assertEqual(c["hydraulic_context"]["status"], "PARTIAL")
        self.assertEqual(c["historical_events"]["status"], "MISSING")
        self.assertEqual(c["observations"]["status"], "MISSING")
        self.assertEqual(c["forecast"]["status"], "CANDIDATE")

    def test_no_threshold_or_negative_control_fabrication(self):
        forbidden = set(self.evidence["forbidden_uses"])
        self.assertIn("operational threshold derivation", forbidden)
        self.assertIn("negative-control inference from missing reports", forbidden)
        self.assertFalse(self.evidence["observations_status"]["verified_negative_controls_available"])

if __name__ == "__main__":
    unittest.main()
