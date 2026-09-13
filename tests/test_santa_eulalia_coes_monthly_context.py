import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/coes_santa_eulalia_sheque_monthly_flow_1994_2007.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"


class SantaEulaliaCoesMonthlyContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_evidence_is_research_only_and_non_operational(self):
        e = self.evidence
        self.assertEqual(e["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(e["test_mode"], "TEST_ONLY")
        self.assertFalse(e["production_use"])
        self.assertFalse(e["production_ready"])
        self.assertFalse(e["operational_alerting_enabled"])
        self.assertIsNone(e["decision_thresholds"])
        self.assertEqual(e["evidence_class"], "HISTORICAL_MONTHLY_NATURAL_FLOW_CONTEXT_ONLY")
        self.assertEqual(e["temporal_resolution"], "MONTHLY_MEAN_ONLY")

    def test_2007_candidate_is_not_promoted_to_verified_negative(self):
        link = self.evidence["candidate_control_link"]
        self.assertEqual(link["case_id"], "santa_eulalia_2007_02_13")
        self.assertEqual(
            link["research_role_after_this_evidence"],
            "INTERMEDIATE_NO_DAMAGE_CONTROL_CANDIDATE_WITH_MONTHLY_HYDROLOGIC_CONTEXT",
        )
        self.assertFalse(link["verified_negative_control"])
        self.assertFalse(link["observed_event_day_discharge"])
        self.assertFalse(link["observed_event_day_level"])
        self.assertFalse(link["event_day_rainfall_available_here"])
        self.assertFalse(link["antecedent_24h_72h_rainfall_available_here"])
        self.assertEqual(self.evidence["monthly_series_2007_m3s"]["feb"], 18.7)

    def test_contract_remains_draft_blocked_and_partial(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "DRAFT")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["hazard_model"]["mechanism_status"], "TO_BE_RESOLVED")
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["assets"]["observations"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["hydraulic_context"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["forecast"]["status"], "CANDIDATE")

    def test_monthly_context_cannot_resolve_event_day_gate(self):
        unsupported = set(self.evidence["interpretation"]["not_supported"])
        for item in {
            "daily_or_hourly_discharge_on_2007_02_13",
            "event_peak_discharge_on_2007_02_13",
            "hydrologic_negative_control_confirmation",
            "operational_threshold_derivation",
            "production_alerting",
        }:
            self.assertIn(item, unsupported)
        self.assertEqual(self.evidence["remaining_gate"]["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()
