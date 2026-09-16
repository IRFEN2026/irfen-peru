import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/zana_oyotun_2008_2009.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/zana_oyotun_official_outcome_context_2008_2026.json"
CHILD = ROOT / "site/data/validation/phase2_hydrologic_child_contracts/lambayeque_zana_oyotun.json"
GEOM = ROOT / "site/data/phase2/geometries/lambayeque_zana_oyotun.geojson"


class ZanaOyotunResearchCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.child = json.loads(CHILD.read_text(encoding="utf-8"))
        cls.geometry = json.loads(GEOM.read_text(encoding="utf-8"))

    def test_closeout_is_research_only_and_fail_closed(self):
        c = self.case
        self.assertEqual(c["case_status"], "CLOSED_RESEARCH_VALIDATION_CASE")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["activation_gate"], "BLOCKED")

    def test_positive_outcomes_are_independent_official_time_slices(self):
        ids = {row["case_id"] for row in self.case["positive_controls"]}
        self.assertEqual(ids, {"ZANA-OYOTUN-2008-03", "ZANA-OYOTUN-2009-01-14"})
        evidence_ids = {row["case_id"] for row in self.evidence["historical_positive_outcomes"]}
        self.assertEqual(ids, evidence_ids)
        row2009 = next(row for row in self.evidence["historical_positive_outcomes"] if row["case_id"] == "ZANA-OYOTUN-2009-01-14")
        self.assertEqual(row2009["reported_impact"], "07 familias afectadas")
        self.assertEqual(row2009["source_event_text"], "desborde del río sña")

    def test_source_typo_is_preserved_not_silently_rewritten(self):
        row2009 = next(row for row in self.evidence["historical_positive_outcomes"] if row["case_id"] == "ZANA-OYOTUN-2009-01-14")
        self.assertIn("preserves the source wording", row2009["source_text_note"])
        self.assertNotEqual(row2009["source_event_text"], "desborde del río Zaña")

    def test_official_geometry_is_whole_hydrologic_unit_not_district(self):
        g = self.case["geometry"]
        self.assertEqual(g["hydrologic_unit_code"], "137754")
        self.assertEqual(g["hydrologic_unit_name"], "Cuenca Zaña")
        self.assertTrue(g["official_hydrologic_boundary"])
        self.assertFalse(g["district_boundary_used"])
        self.assertFalse(g["municipal_boundary_is_unit_boundary"])
        self.assertEqual(self.child["identity"]["official_hydrologic_unit_code"], "137754")
        self.assertTrue(self.child["geometry"]["official_hydrologic_boundary"])
        self.assertEqual(self.geometry["type"], "FeatureCollection")

    def test_no_negative_or_threshold_is_fabricated(self):
        n = self.case["negative_control_status"]
        self.assertEqual(n["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")
        self.assertFalse(n["verified_negative_control"])
        self.assertIsNone(self.case["threshold_policy"]["decision_thresholds"])
        self.assertFalse(self.case["threshold_policy"]["historical_outcomes_are_operational_thresholds"])
        self.assertFalse(self.case["threshold_policy"]["critical_point_design_values_are_operational_thresholds"])

    def test_hydrometeorology_and_routing_remain_unresolved(self):
        h = self.case["hydrometeorological_limitations"]
        self.assertFalse(h["event_day_rainfall_2008_available"])
        self.assertFalse(h["event_day_discharge_2008_available"])
        self.assertFalse(h["event_day_rainfall_2009_available"])
        self.assertFalse(h["event_day_discharge_2009_available"])
        sep = self.case["mechanism_separation"]
        self.assertFalse(sep["event_specific_nanchoc_to_zana_routing_validated"])
        self.assertFalse(sep["individual_quebrada_activation_validated"])
        self.assertFalse(sep["current_channel_capacity_validated"])

    def test_current_critical_point_is_context_not_historical_truth(self):
        current = self.case["current_critical_reach_context"]
        self.assertFalse(current["current_state_backcast_to_2008_2009"])
        self.assertEqual(current["2026_reference_sector"], "Algarrobal Alto / Río Nanchoc")
        self.assertEqual(current["role"], "CURRENT_EXPOSURE_AND_INTERVENTION_CONTEXT_NOT_HISTORICAL_EVENT_TRUTH")

    def test_child_contract_remains_in_review_and_blocked(self):
        self.assertEqual(self.child["contract_status"], "IN_REVIEW")
        self.assertEqual(self.child["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(self.child["production_use"])
        self.assertFalse(self.child["production_ready"])
        self.assertFalse(self.child["operational_alerting_enabled"])
        self.assertIsNone(self.child["decision_thresholds"])
        self.assertEqual(self.child["validation"]["activation_gate"], "BLOCKED")
        self.assertFalse(self.child["validation"]["promotion_allowed"])
        self.assertFalse(self.case["mechanism_separation"]["hydrologic_child_contract_may_be_promoted"])


if __name__ == "__main__":
    unittest.main()
