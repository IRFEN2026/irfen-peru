import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/lurin_cieneguilla_pachacamac_2017.json"
NOTES = ROOT / "site/data/validation/phase2_research_evidence/lurin_closeout_notes_v0_1.json"


class LurinResearchCloseoutContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.notes = json.loads(NOTES.read_text(encoding="utf-8"))

    def test_closeout_remains_non_operational(self):
        for obj in (self.case, self.notes):
            self.assertEqual(obj["deployment_status"], "RESEARCH_ONLY")
            self.assertFalse(obj["production_use"])
            self.assertFalse(obj["production_ready"])
            self.assertFalse(obj["operational_alerting_enabled"])
            self.assertIsNone(obj["decision_thresholds"])
            self.assertEqual(obj["activation_gate"], "BLOCKED")

    def test_positive_events_can_close_research_without_fake_negative(self):
        self.assertEqual(self.case["case_status"], "CLOSED_RESEARCH_VALIDATION_CASE")
        self.assertTrue(self.case["closure"]["research_validation_closed"])
        self.assertEqual(self.case["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")

    def test_secondary_threshold_claims_are_explicitly_forbidden(self):
        forbidden = " ".join(self.case["threshold_policy"]["forbidden_promotions"]).lower()
        self.assertIn("historical senamhi alert bands", forbidden)
        self.assertIn("25-30 mm/day", forbidden)
        self.assertIn("70-75 m3/s", forbidden)


if __name__ == "__main__":
    unittest.main()
