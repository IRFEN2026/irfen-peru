import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/cashahuacra_santa_eulalia_2015.json"
SOURCE = ROOT / "site/data/validation/phase2_research_evidence/ingemmet_chosica_santa_eulalia_2015.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"


class Cashahuacra2015ResearchCloseoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_closeout_is_research_only_and_non_operational(self):
        c = self.case
        self.assertEqual(c["case_status"], "CLOSED_RESEARCH_VALIDATION_CASE")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["activation_gate"], "BLOCKED")
        self.assertTrue(c["closure"]["research_validation_closed"])
        self.assertTrue(c["closure"]["production_blocked"])

    def test_primary_field_outcome_is_cashahuacra_only(self):
        self.assertEqual(self.source["event_scope"]["cashahuacra_outcome"], "CONFIRMED_POSITIVE_FIELD_EVIDENCE")
        self.assertEqual(self.case["event"]["classification"], "CONFIRMED_POSITIVE_FIELD_EVIDENCE")
        self.assertIn("housing", " ".join(self.case["event"]["observed_outcome"]).lower())

    def test_rainfall_context_cannot_be_threshold(self):
        self.assertEqual(self.case["rainfall_context"]["reported_peak_daily_mm_on_event_day"], 18.0)
        self.assertEqual(self.case["rainfall_context"]["status"], "CONTEXT_ONLY_NOT_THRESHOLD")
        self.assertIsNone(self.case["threshold_policy"]["decision_thresholds"])
        forbidden = " ".join(self.case["threshold_policy"]["forbidden_promotions"]).lower()
        self.assertIn("18 mm", forbidden)

    def test_candidate_geometry_is_not_promoted_to_official_watershed(self):
        g = self.case["geometry"]
        self.assertEqual(g["representation"], "COPERNICUS_DEM_GLO30_D8_CATCHMENT")
        self.assertFalse(g["official_watershed_area"])
        self.assertFalse(g["official_outlet_confirmed"])
        self.assertEqual(g["confidence"], "MEDIUM_CANDIDATE")

    def test_compound_system_remains_unresolved_and_blocked(self):
        sep = self.case["compound_system_separation"]
        self.assertTrue(sep["cashahuacra_local_component_closed_for_research"])
        self.assertFalse(sep["santa_eulalia_river_component_resolved"])
        self.assertFalse(sep["rimac_receiving_river_component_resolved"])
        self.assertFalse(sep["compound_synchronization_validated"])
        self.assertFalse(sep["system_contract_may_be_promoted"])
        self.assertEqual(self.contract["contract_status"], "DRAFT")
        self.assertEqual(self.contract["hazard_model"]["mechanism_status"], "TO_BE_RESOLVED")
        self.assertEqual(self.contract["validation"]["activation_gate"], "BLOCKED")
        self.assertIsNone(self.contract["decision_thresholds"])

    def test_pedregal_clean_room_remains_sealed(self):
        p = self.case["pedregal_clean_room_separation"]
        self.assertTrue(p["source_contains_pedregal_outcome"])
        self.assertFalse(p["pedregal_outcome_used_in_this_closeout"])
        self.assertTrue(p["pedregal_outcome_bearing_content_remains_sealed_from_clean_room"])
        self.assertFalse(p["safe_unblind_performed"])
        self.assertTrue(self.source["pedregal"]["clean_room_policy"]["sealed_from_candidate_matching_and_reranking"])

    def test_no_negative_is_fabricated(self):
        self.assertEqual(self.case["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")
        self.assertTrue(self.case["historical_context"]["event_level_verification_required_before_use_as_controls"])


if __name__ == "__main__":
    unittest.main()
