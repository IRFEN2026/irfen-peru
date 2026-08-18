from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/review-v08-external-evidence.yml"
CONTRACT = ROOT / "config/v08_external_validation_contract.json"


class ExternalEvidenceReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_workflow_is_manual_and_uses_traceable_actor(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("REVIEWED_BY: ${{ github.actor }}", self.text)
        self.assertNotIn("reviewer:\n", self.text)

    def test_all_contractual_pilots_and_items_are_selectable(self):
        for pilot in self.contract["pilots"]:
            self.assertIn(f"- {pilot['zone_id']}", self.text)
            for evidence_id in pilot["required_evidence_ids"]:
                self.assertIn(f"- {evidence_id}", self.text)

    def test_decision_is_closed_and_conservative_by_default(self):
        self.assertIn("default: REJECTED", self.text)
        self.assertIn("- REJECTED", self.text)
        self.assertIn("- ACCEPTED", self.text)
        self.assertIn("confirm_requirement_fully_satisfied:", self.text)

    def test_replacement_is_explicit_and_publication_is_commit_pinned(self):
        self.assertIn("replace_existing_review:", self.text)
        self.assertGreaterEqual(self.text.count("default: false"), 2)
        self.assertIn('echo "commit_sha=$(git rev-parse HEAD)"', self.text)
        self.assertIn('-f expected_sha="$EXPECTED_SHA"', self.text)


if __name__ == "__main__":
    unittest.main()
