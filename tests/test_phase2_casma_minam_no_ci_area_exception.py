from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
ASSESSMENT = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"


class TestCasmaNoCIAreaException(unittest.TestCase):
    def test_casma_descendant_recovery_has_no_ci_only_area_exception(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("diagnostic_bypass", source)
        self.assertNotIn("is_bounded_ci_probe", source)

    def test_casma_descendant_drift_remains_fail_closed(self):
        d = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
        self.assertEqual(d["status"], "FAIL_CLOSED_DESCENDANT_ATTRIBUTE_DRIFT")
        self.assertIs(d["findings"]["strict_2007_attribute_equivalence_passed"], False)
        self.assertIs(d["findings"]["map_publication_authorized"], False)
        self.assertIs(d["production_use"], False)
        self.assertIs(d["production_ready"], False)
        self.assertIs(d["operational_alerting_enabled"], False)
        self.assertEqual(d["activation_gate"], "BLOCKED")
        self.assertIsNone(d["decision_thresholds"])
        self.assertIsNone(d["hydraulic_factors"])


if __name__ == "__main__":
    unittest.main()
