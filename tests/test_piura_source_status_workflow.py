import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PiuraSourceStatusWorkflowTests(unittest.TestCase):
    def test_dispatches_publisher_with_exact_main_sha(self):
        workflow = (
            ROOT / ".github/workflows/piura-source-status.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("actions: write", workflow)
        self.assertIn('EXPECTED_SHA="$(git rev-parse origin/main)"', workflow)
        self.assertIn("gh workflow run publish-committed-data.yml", workflow)
        self.assertIn('-f expected_sha="$EXPECTED_SHA"', workflow)


if __name__ == "__main__":
    unittest.main()
