import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "site/data/scientific_status.json"
MASTER = ROOT / "site/data/validation/phase2_master_state_v08.json"


class ScientificStatusResearchPortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))
        cls.master = json.loads(MASTER.read_text(encoding="utf-8"))

    def test_operational_scope_remains_three_pilots(self):
        self.assertFalse(self.status["production_use"])
        self.assertFalse(self.status["production_ready"])
        self.assertEqual(
            [zone["id"] for zone in self.status["zones"]],
            ["san_ildefonso", "lima_east", "catacaos"],
        )
        stop_rule = self.status["core_release_status"]["stop_rule"]
        self.assertIn("No ampliar el ámbito operativo", stop_rule)
        self.assertIn("RESEARCH_ONLY", stop_rule)

    def test_research_portfolio_mirrors_master_state(self):
        p = self.status["research_validation_portfolio"]
        summary = self.master["portfolio_summary"]
        self.assertEqual(p["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(p["production_use"])
        self.assertFalse(p["production_ready"])
        self.assertFalse(p["operational_alerting_enabled"])
        self.assertIsNone(p["decision_thresholds"])
        self.assertEqual(p["activation_gate"], "BLOCKED")
        self.assertEqual(
            p["closed_research_validation_cases"],
            summary["closed_research_validation_cases"],
        )
        self.assertEqual(
            p["in_review_research_validation_cases"],
            summary["in_review_research_validation_cases"],
        )
        self.assertEqual(
            p["phase2_registered_candidates"],
            summary["phase2_registered_candidates"],
        )
        self.assertEqual(
            p["phase2_contracts_approved"],
            summary["phase2_contracts_approved"],
        )
        self.assertEqual(
            p["phase2_operational_candidates"],
            summary["phase2_operational_candidates"],
        )

    def test_case_lists_match_master_state_and_pedregal_stays_open(self):
        p = self.status["research_validation_portfolio"]
        closed = sorted(
            case["case_id"]
            for case in self.master["cases"]
            if case["case_status"] == "CLOSED_RESEARCH_VALIDATION_CASE"
        )
        in_review = sorted(
            case["case_id"]
            for case in self.master["cases"]
            if case["case_status"] == "IN_REVIEW_RESEARCH_VALIDATION_CASE"
        )
        self.assertEqual(sorted(p["closed_cases"]), closed)
        self.assertEqual(sorted(p["in_review_cases"]), in_review)
        self.assertEqual(in_review, ["pedregal_san_antonio_2015"])
        self.assertTrue(self.master["guardrails"]["pedregal_clean_room_sealed_until_safe_unblind"])

    def test_phase2_closeouts_do_not_count_as_operational_promotion(self):
        p = self.status["research_validation_portfolio"]
        self.assertEqual(p["phase2_contracts_approved"], 0)
        self.assertEqual(p["phase2_operational_candidates"], 0)
        self.assertIn("separate from zone-contract approval", p["interpretation"])
        self.assertEqual(
            self.status["components"]["research_validation_master_state"],
            "data/validation/phase2_master_state_v08.json",
        )


if __name__ == "__main__":
    unittest.main()
