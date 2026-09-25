import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "config/phase2_casma_n7_geosnirh_probe_v0_1.json"
GAP = ROOT / "config/phase2_casma_n7_geometry_source_gap_v0_1.json"
ASSESSMENT = ROOT / "site/data/phase2/source_assessments/casma_geosnirh_hydrologic_units_v0_1.json"


class CasmaN7SourceProbeContractTests(unittest.TestCase):
    def test_probe_remains_fail_closed(self):
        p = json.loads(PROBE.read_text(encoding="utf-8"))
        self.assertEqual(p["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(p["test_mode"], "TEST_ONLY")
        self.assertFalse(p["production_use"])
        self.assertFalse(p["production_ready"])
        self.assertFalse(p["operational_alerting_enabled"])
        self.assertEqual(p["activation_gate"], "BLOCKED")
        self.assertEqual(p["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(p["decision_thresholds"])
        self.assertIsNone(p["hydraulic_factors"])
        self.assertFalse(p["map_publication_enabled"])

    def test_existing_n7_identity_gate_remains_authoritative(self):
        g = json.loads(GAP.read_text(encoding="utf-8"))
        children = g["identity_status"]["n7_children"]
        self.assertEqual(len(children), 9)
        self.assertTrue(g["identity_status"]["n7_identity_is_documentarily_supported"])
        self.assertTrue(g["identity_status"]["identity_does_not_supply_geometry"])
        self.assertFalse(g["scientific_effect"]["child_geometry_created"])
        self.assertFalse(g["scientific_effect"]["map_publication_enabled"])

    def test_source_candidate_is_bounded_and_not_promoted(self):
        a = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
        self.assertEqual(a["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(a["activation_gate"], "BLOCKED")
        self.assertEqual(a["source_candidate"]["institution"], "Autoridad Nacional del Agua")
        self.assertEqual(a["source_candidate"]["layer_name"], "Unidades Hidrograficas")
        self.assertIn("NIVEL7", a["source_candidate"]["advertised_identity_fields"])
        self.assertEqual(a["source_candidate"]["exact_casma_n7_retrieval_status"], "PENDING")
        d = a["scientific_disposition"]
        self.assertTrue(d["advertised_n7_fields_are_not_proof_of_casma_feature_presence"])
        self.assertTrue(d["exact_feature_identity_required_before_geometry_use"])
        self.assertTrue(d["freeze_source_bytes_and_sha256_before_normalization"])
        self.assertFalse(d["partial_or_ambiguous_results_map_eligible"])

    def test_probe_status_does_not_claim_retrieval(self):
        p = json.loads(PROBE.read_text(encoding="utf-8"))
        self.assertEqual(p["status"], "PROBE_PENDING")
        self.assertIn("retrieval remains pending", p["note"].lower())


if __name__ == "__main__":
    unittest.main()
