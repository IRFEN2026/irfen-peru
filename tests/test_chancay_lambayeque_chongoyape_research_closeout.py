import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/chancay_lambayeque_chongoyape_2021_2026.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/chancay_lambayeque_chongoyape_official_context_2021_2026.json"
CONTRACT = ROOT / "site/data/validation/phase2_hydrologic_child_contracts/lambayeque_chancay_lambayeque_chongoyape.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lambayeque_chancay_lambayeque_chongoyape.geojson"


class ChancayLambayequeChongoyapeResearchCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))

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

    def test_official_geometry_is_preserved_as_whole_hydrologic_unit(self):
        identity = self.case["hydrologic_identity"]
        self.assertEqual(identity["official_hydrologic_unit_code"], "13776")
        self.assertEqual(identity["official_hydrologic_unit_name"], "Cuenca Chancay-Lambayeque")
        self.assertFalse(identity["municipal_boundary_is_unit_boundary"])
        self.assertFalse(identity["geometry_is_event_footprint"])
        self.assertFalse(identity["geometry_is_hydraulic_capacity_model"])
        self.assertEqual(self.contract["geometry"]["official_hydrologic_boundary"], True)
        self.assertTrue(self.geometry.get("type") in {"Feature", "FeatureCollection"})

    def test_multiple_positive_outcomes_are_mechanism_separated(self):
        ids = {row["control_id"] for row in self.case["positive_controls"]}
        self.assertEqual(ids, {
            "CHONGOYAPE-CHANCAY-2021-03-10",
            "CHONGOYAPE-YAIPON-2026-02-15",
            "CHONGOYAPE-JUANA-RIOS-2026-02-18",
            "CHONGOYAPE-YAIPON-2026-02-21",
        })
        sep = self.case["mechanism_separation"]
        self.assertTrue(sep["rio_chancay_resolved_as_distinct_component"])
        self.assertTrue(sep["rio_yaipon_resolved_as_distinct_component"])
        self.assertTrue(sep["local_quebradas_resolved_as_distinct_component"])
        self.assertFalse(sep["cross_component_routing_validated"])
        self.assertFalse(sep["universal_activation_rule_supported"])

    def test_no_negative_control_is_fabricated(self):
        self.assertEqual(
            self.case["negative_control_status"]["status"],
            "NO_CONFIRMED_NEGATIVE_CONTROL",
        )
        self.assertEqual(self.case["negative_control_status"]["verified_negative_controls"], [])
        self.assertEqual(
            self.evidence["negative_control_status"]["status"],
            "NO_CONFIRMED_NEGATIVE_CONTROL",
        )

    def test_peot_source_flows_never_become_irfen_thresholds_or_capacity(self):
        ctx = self.case["current_hydraulic_context"]
        self.assertFalse(ctx["reported_90_m3s_is_irfen_threshold"])
        self.assertFalse(ctx["reported_400_600_m3s_range_is_irfen_threshold"])
        self.assertFalse(ctx["reported_620_m3s_narrative_max_is_irfen_threshold"])
        self.assertFalse(ctx["source_values_validate_overflow_capacity"])
        self.assertFalse(ctx["historical_backcast_allowed"])
        for row in self.evidence["current_hydraulic_context"]:
            self.assertFalse(row["capacity_validated"])
            self.assertFalse(row["irfen_threshold"])

    def test_hydrologic_child_contract_remains_in_review_blocked(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "IN_REVIEW")
        self.assertEqual(c["review_status"], "REVIEW_ONLY")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertFalse(c["validation"]["promotion_allowed"])

    def test_current_critical_points_are_context_not_historical_outcomes(self):
        ana = self.evidence["critical_reach_context"]["ana_2025"]
        peot = self.evidence["critical_reach_context"]["peot_2026"]
        self.assertIn("NOT_EVENT_FOOTPRINT", ana["role"])
        self.assertIn("NOT_HISTORICAL_OUTCOME", peot["role"])


if __name__ == "__main__":
    unittest.main()
