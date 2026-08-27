import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "v08-scheduler-fallback.yml"


class V08SchedulerFallbackWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()

    def test_trigger_is_scoped_to_authenticated_owner_and_dedicated_issue(self):
        self.assertIn("issues:", self.text)
        self.assertIn("types: [opened, edited, reopened]", self.text)
        self.assertIn("github.actor == 'IRFEN2026'", self.text)
        self.assertIn("[automation] IRFEN v0.8 evidence sweep", self.text)
        self.assertIn("IRFEN_V08_EVIDENCE_SWEEP", self.text)

    def test_permissions_are_minimal_for_dispatch(self):
        self.assertIn("contents: read", self.text)
        self.assertIn("actions: write", self.text)
        self.assertNotIn("contents: write", self.text)

    def test_fallback_requires_four_hours_without_schedule_events(self):
        self.assertIn("event=schedule&per_page=1", self.text)
        self.assertIn("schedule_age_seconds < 14400", self.text)

    def test_safety_contract_is_checked_before_dispatch(self):
        self.assertIn('contract.get("production_use") is False', self.text)
        self.assertIn('["san_ildefonso", "chosica", "catacaos"]', self.text)
        self.assertIn("all v0.8 recommendations remain TEST_ONLY", self.text)
        self.assertIn("phase-2 candidates remain RESEARCH_ONLY", self.text)

    def test_only_closeout_collectors_are_dispatched_with_cooldowns(self):
        expected = {
            "igp-cendehua-probe.yml:5400",
            "goes19-rrqpe-probe.yml:5400",
            "senamhi-nacara-probe.yml:5400",
            "imerg-early-probe.yml:5400",
            "shadow-validation.yml:7200",
            "official-outcome-evidence.yml:25200",
            "piura-source-status.yml:90000",
            "update-and-deploy.yml:90000",
            "geos-forecast.yml:90000",
        }
        for item in expected:
            self.assertIn(f'"{item}"', self.text)
        self.assertEqual(self.text.count('gh workflow run "$workflow"'), 1)
        self.assertIn('--ref main', self.text)


if __name__ == "__main__":
    unittest.main()
