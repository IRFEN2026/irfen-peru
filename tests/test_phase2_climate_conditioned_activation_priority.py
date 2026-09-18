import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "config/phase2_climate_conditioned_activation_priority_v0_1.json"
INVENTORY = ROOT / "config/phase2_candidate_inventory_v0_2.json"


class ClimateConditionedActivationPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.framework = json.loads(FRAMEWORK.read_text(encoding="utf-8"))
        cls.inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_framework_is_fail_closed_and_non_operational(self):
        f = self.framework
        self.assertEqual(f["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(f["production_use"])
        self.assertFalse(f["production_ready"])
        self.assertFalse(f["operational_alerting_enabled"])
        self.assertIsNone(f["decision_thresholds"])
        self.assertEqual(f["activation_gate"], "BLOCKED")
        self.assertTrue(f["guardrails"]["all_activation_gates_remain_blocked"])

    def test_v08_scope_and_phase2_count_are_not_changed(self):
        rel = self.framework["relationship_to_v08"]
        self.assertTrue(rel["operational_scope_unchanged"])
        self.assertEqual(rel["operational_pilots"], ["san_ildefonso", "chosica_huaycoloro", "catacaos_bajo_piura"])
        self.assertTrue(rel["phase2_candidate_count_unchanged"])
        self.assertFalse(rel["counts_toward_v08_release_scorecard"])
        self.assertEqual(len(self.inventory["candidates"]), 18)

    def test_no_exhaustive_equal_intensity_national_search(self):
        p = self.framework["principles"]
        self.assertTrue(p["exhaustive_peru_first_forbidden"])
        self.assertEqual(p["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertTrue(p["regional_priority_is_dynamic_and_may_change_with_official_climate_context"])

    def test_population_is_not_the_only_impact_measure(self):
        p = self.framework["principles"]
        self.assertTrue(p["population_count_is_not_the_only_impact_measure"])
        impact = self.framework["impact_balance"]
        self.assertIn("roads", impact["rule"].lower() + " " + impact["small_population_case"].lower())
        self.assertIn("bridge", impact["small_population_case"].lower())
        self.assertIn("water", impact["small_population_case"].lower())

    def test_south_coast_episodic_lane_is_explicit(self):
        lanes = {row["lane_id"]: row for row in self.framework["dynamic_research_lanes"]}
        south = lanes["SOUTH_COAST_EPISODIC_HIGH_IMPACT"]
        self.assertIn("Ilo", south["geographic_focus"])
        self.assertIn("coastal Arequipa", south["geographic_focus"])
        self.assertIn("ica_palpa_changuillo", south["registered_candidate_examples"])
        self.assertIn("arequipa_acari_san_agustin", south["registered_candidate_examples"])
        self.assertIn("moquegua_ilo_coastal_ravines", south["discovery_only_corridors"])
        self.assertFalse(south["discovery_only_corridors_count_as_phase2_candidates"])

    def test_seasonal_mean_cannot_be_used_as_zero_activation_risk(self):
        p = self.framework["principles"]
        self.assertTrue(p["seasonal_mean_rainfall_is_not_zero_activation_risk"])
        guard = self.framework["south_coast_specific_guardrails"]
        self.assertTrue(guard["do_not_use_seasonal_below_normal_as_no_activation"])
        self.assertTrue(guard["require_event_level_evidence_for_activation_truth"])

    def test_historical_behavior_matrix_is_non_numeric_and_event_grounded(self):
        m = self.framework["historical_behavior_matrix"]
        self.assertFalse(m["numeric_probability_required"])
        self.assertTrue(m["no_negative_from_absence_of_report"])
        self.assertIn("isolated_convective_or_episodic_extreme", m["required_axes"])
        self.assertEqual(m["allowed_response_classes"], ["HIGH", "MEDIUM", "LOW", "UNKNOWN"])

    def test_priority_cannot_promote_thresholds_or_alerts(self):
        s = self.framework["research_selection_rule"]
        self.assertFalse(s["numeric_score_used"])
        self.assertTrue(s["deterministic_winner_forbidden"])
        self.assertFalse(s["selection_output_is_operational_alert"])
        g = self.framework["guardrails"]
        self.assertTrue(g["no_operational_promotion_from_priority_framework"])
        self.assertTrue(g["no_threshold_transfer"])
        self.assertTrue(g["no_hydraulic_factor_transfer"])


if __name__ == "__main__":
    unittest.main()
