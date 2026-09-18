import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_climate_conditioned_research_priority_v0_1.json"
BASE = ROOT / "config/phase2_map_priority_v0_1.json"


class Phase2ClimateConditionedPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(CFG.read_text(encoding="utf-8"))
        cls.base = json.loads(BASE.read_text(encoding="utf-8"))

    def test_overlay_is_fail_closed_and_non_operational(self):
        c = self.cfg
        self.assertEqual(c["status"], "RESEARCH_ONLY_SCENARIO_OVERLAY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["activation_gate"], "BLOCKED")

    def test_phase2_scope_and_candidate_count_are_unchanged(self):
        rel = self.cfg["relationship_to_phase2"]
        self.assertEqual(rel["registered_candidate_count_unchanged"], 18)
        self.assertFalse(rel["changes_candidate_count"])
        self.assertFalse(rel["changes_operational_scope"])
        self.assertFalse(rel["changes_thresholds"])
        self.assertFalse(rel["changes_hydraulic_factors"])
        self.assertFalse(rel["changes_activation_gates"])

    def test_base_queue_remains_distinct_from_scenario_overlay(self):
        self.assertEqual(
            self.base["scenario_overlay_reference"],
            "config/phase2_climate_conditioned_research_priority_v0_1.json",
        )
        self.assertFalse(self.base["production_use"])
        self.assertTrue(self.cfg["relationship_to_phase2"]["base_queue_is_not_risk_ranking"])
        self.assertTrue(self.cfg["relationship_to_phase2"]["overlay_may_resequence_research_effort"])

    def test_two_high_priority_corridors_exist(self):
        corridors = {r["corridor_id"]: r for r in self.cfg["scenario_corridors"]}
        self.assertEqual(corridors["PACIFIC_NORTH_CENTRAL_WARM_EVENT"]["research_priority"], "HIGH")
        south = corridors["SOUTH_COAST_EPISODIC_CONNECTIVITY"]
        self.assertEqual(south["research_priority"], "HIGH")
        self.assertIn("ica_palpa_changuillo", south["current_registered_focus"])
        self.assertIn("arequipa_acari_san_agustin", south["current_registered_focus"])
        names = {d["corridor"] for d in south["discovery_corridors"]}
        self.assertIn("Moquegua-Ilo coastal ravines", names)
        self.assertTrue(all(d["register_only_after_reproducible_evidence"] for d in south["discovery_corridors"]))

    def test_population_is_not_the_only_consequence_dimension(self):
        p = self.cfg["impact_balance_policy"]
        self.assertFalse(p["demographic_exposure_required"])
        self.assertTrue(p["zero_or_low_local_population_does_not_remove_candidate"])
        self.assertTrue(p["connectivity_and_isolation_can_raise_priority"])

    def test_seasonal_background_cannot_suppress_episodic_activation_by_rule(self):
        s = self.cfg["scientific_principles"]
        self.assertTrue(s["seasonal_mean_does_not_equal_zero_activation_probability"])
        self.assertTrue(s["local_extreme_episode_can_matter_despite_normal_or_dry_seasonal_background"])
        self.assertTrue(s["missing_instrumentation_is_not_low_risk"])
        self.assertTrue(s["no_numeric_probability_without_validated_model"])

    def test_historical_regime_reconstruction_is_explicit(self):
        labels = [r["label"] for r in self.cfg["historical_regime_windows_to_reconstruct"]]
        self.assertIn("1982-1983 strong El Nino", labels)
        self.assertIn("1997-1998 strong El Nino", labels)
        self.assertIn("2017 coastal El Nino", labels)
        self.assertIn("2023 coastal warm event", labels)

    def test_dynamic_reprioritization_never_activates(self):
        d = self.cfg["dynamic_reprioritization"]
        self.assertTrue(d["enabled_for_research_queue"])
        self.assertFalse(d["operational_reprioritization"])
        self.assertIn("cannot itself activate a zone", d["rule"])


if __name__ == "__main__":
    unittest.main()
