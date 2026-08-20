from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseEvidenceChainTests(unittest.TestCase):
    def test_builders_wire_verification_to_scorecard_to_rc(self):
        score_builder = (ROOT / "scripts/build_v08_scorecard.py").read_text(encoding="utf-8")
        rc_builder = (ROOT / "scripts/build_v08_rc_status.py").read_text(encoding="utf-8")
        self.assertIn('"sha256": sha256_file(verification_path)', score_builder)
        self.assertIn('declared_verification != actual_verification', rc_builder)
        self.assertIn('"sha256": scorecard_hash', rc_builder)
        self.assertIn('"sha256": actual_verification', rc_builder)

    def test_live_smoke_recomputes_chain_and_enforces_non_decrease(self):
        smoke = (ROOT / ".github/workflows/live-smoke-test.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", smoke)
        self.assertIn("github.event.workflow_run.id", smoke)
        self.assertIn("silent_decrease_forbidden", smoke)
        self.assertIn("sha256('data/forecast/verification.json')", smoke)
        self.assertIn("sha256('data/v08_scorecard.json')", smoke)


if __name__ == "__main__":
    unittest.main()
