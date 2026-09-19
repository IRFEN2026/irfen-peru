import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/palpa_changuillo_2023_2026.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/palpa_changuillo_official_context_2023_2026.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/ica_palpa_changuillo.json"


# Revalidated against advancing main before merge.
# Revalidated after Pedregal clean-room PR #176 merge.
class PalpaChanguilloResearchCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_closeout_is_research_only_and_blocked(self):
        c = self.case
        self.assertEqual(c["case_status"], "CLOSED_RESEARCH_VALIDATION_CASE")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["activation_gate"], "BLOCKED")

    def test_positive_controls_cover_independent_components_and_time_slices(self):
        ids = {row["control_id"] for row in self.case["positive_controls"]}
        self.assertEqual(ids, {
            "PALPA-MULTIRIVER-2023-01-31",
            "PALPA-VISCAS-2023-02-03",
            "CHANGUILLO-COYUNGO-2023-12-30",
            "EL-INGENIO-PAPAGALLO-2025-03-09",
            "CHANGUILLO-INGENIO-2026-02-17",
            "EL-INGENIO-CARAHUARCO-2026-04-01",
        })

    def test_no_negative_is_fabricated(self):
        self.assertEqual(self.case["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")
        self.assertEqual(self.case["negative_control_status"]["verified_negative_controls"], [])
        self.assertEqual(self.evidence["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")

    def test_components_remain_separate(self):
        sep = self.case["mechanism_separation"]
        self.assertTrue(sep["rio_palpa_distinct_component"])
        self.assertTrue(sep["rio_viscas_distinct_component"])
        self.assertTrue(sep["rio_grande_distinct_component"])
        self.assertTrue(sep["rio_ingenio_distinct_component"])
        self.assertTrue(sep["local_changuillo_huaicos_distinct_component"])
        self.assertFalse(sep["cross_component_routing_validated"])
        self.assertFalse(sep["corridor_is_single_hydraulic_unit"])

    def test_coyungo_ravine_identity_is_not_invented(self):
        sep = self.case["mechanism_separation"]
        self.assertFalse(sep["coyungo_named_ravine_resolved"])
        row = next(r for r in self.evidence["confirmed_positive_outcomes"]
                   if r["case_id"] == "CHANGUILLO-COYUNGO-2023-12-30")
        self.assertIn("does not identify a single named ravine", row["mechanism_caution"])

    def test_defense_failure_does_not_become_capacity_rule(self):
        row = next(r for r in self.evidence["confirmed_positive_outcomes"]
                   if r["case_id"] == "EL-INGENIO-PAPAGALLO-2025-03-09")
        self.assertEqual(row["classification"], "CONFIRMED_POSITIVE_RIVER_OVERFLOW_AFTER_DEFENSE_FAILURE")
        self.assertIn("not generalized", row["mechanism_caution"])

    def test_critical_points_are_context_not_event_footprints(self):
        for row in self.evidence["critical_reach_context"].values():
            role = row["role"]
            self.assertIn("CONTEXT", role)
            self.assertTrue(
                "NOT_EVENT_FOOTPRINT" in role or "NOT_HISTORICAL_CAPACITY_TRUTH" in role,
                role,
            )

    def test_contract_remains_draft_blocked_and_unpromoted(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "DRAFT")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["hazard_model"]["mechanism_status"], "TO_BE_RESOLVED")
        self.assertEqual(c["assets"]["geometry"]["status"], "MISSING")

    def test_no_threshold_or_hydraulic_transfer(self):
        self.assertIsNone(self.evidence["decision_thresholds"])
        forbidden = set(self.evidence["forbidden_uses"])
        self.assertIn("operational threshold derivation", forbidden)
        self.assertIn("cross-river hydraulic transfer", forbidden)


if __name__ == "__main__":
    unittest.main()
