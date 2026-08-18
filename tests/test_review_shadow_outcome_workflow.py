from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/review-shadow-outcome.yml"


class ReviewShadowOutcomeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_and_uses_traceable_actor(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("REVIEWED_BY: ${{ github.actor }}", self.text)
        self.assertNotIn("reviewed_by:\n", self.text)

    def test_label_is_closed_choice_with_conservative_default(self):
        self.assertIn("default: UNCERTAIN", self.text)
        for label in ("UNCERTAIN", "EVENT", "NONE"):
            self.assertIn(f"- {label}", self.text)

    def test_none_and_replacement_require_explicit_booleans(self):
        self.assertIn("comprehensive_none_coverage:", self.text)
        self.assertIn("replace_existing_review:", self.text)
        self.assertGreaterEqual(self.text.count("default: false"), 2)

    def test_publication_uses_exact_persisted_commit(self):
        self.assertIn('echo "commit_sha=$(git rev-parse HEAD)"', self.text)
        self.assertIn('-f expected_sha="$EXPECTED_SHA"', self.text)


if __name__ == "__main__":
    unittest.main()
