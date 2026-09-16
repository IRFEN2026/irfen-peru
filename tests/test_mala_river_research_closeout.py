import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/mala_river_2017_2025.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/mala_official_outcome_hydrologic_context_2017_2026.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_mala.json"


class MalaRiverResearchCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_closeout_is_bounded_research_only(self):
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

    def test_multiple_official_positive_outcomes_are_retained(self):
        ids = {row["case_id"] for row in self.case["positive_controls"]}
        self.assertEqual(ids, {
            "MALA-2017-03-08",
            "MALA-2021-01-05",
            "MALA-2024-01-03",
            "MALA-2025-02-23",
        })
        evidence_ids = {row["case_id"] for row in self.evidence["historical_positive_outcomes"]}
        self.assertTrue(ids.issubset(evidence_ids))
        self.assertIn("MALA-2023-02-17", evidence_ids)

    def test_compound_2023_event_is_not_generalized(self):
        event = self.case["compound_event_context"]
        self.assertEqual(event["classification"], "CONFIRMED_COMPOUND_HUAICO_RIVER_OVERFLOW_OUTCOME")
        self.assertEqual(event["role"], "POSITIVE_CONTEXT_NOT_GENERALIZED_MECHANISM")
        sep = self.case["mechanism_separation"]
        self.assertFalse(sep["tributary_debris_flow_system_resolved"])
        self.assertTrue(sep["compound_huaico_to_river_pathway_supported_for_2023_only"])
        self.assertFalse(sep["universal_hydraulic_routing_validated"])

    def test_station_observations_are_not_transferred_to_impact_reaches(self):
        h = self.case["hydrologic_monitoring_context"]
        self.assertFalse(h["event_specific_transfer_validated"])
        obs = {row["date"]: row for row in h["observations"]}
        self.assertEqual(obs["2022-03-15"]["discharge_m3s"], 85.42)
        self.assertEqual(obs["2024-03-26"]["discharge_m3s"], 80.87)
        self.assertEqual(obs["2026-02-26"]["discharge_m3s"], 106.51)
        self.assertTrue(all(not row["event_day_link_to_historical_outcomes_validated"]
                            for row in self.evidence["station_hydrologic_context"]))

    def test_provider_alert_bands_are_not_irfen_thresholds(self):
        policy = self.case["threshold_policy"]
        self.assertIsNone(policy["decision_thresholds"])
        self.assertFalse(policy["provider_alert_bands_are_irfen_thresholds"])
        self.assertFalse(policy["historical_provider_bands_temporally_invariant"])
        obs = {row["date_local"]: row for row in self.evidence["station_hydrologic_context"]}
        self.assertEqual(obs["2024-03-26"]["provider_red_band_m3s"], 110)
        self.assertEqual(obs["2026-02-26"]["provider_red_band_m3s"], 130)
        self.assertNotEqual(
            obs["2024-03-26"]["provider_red_band_m3s"],
            obs["2026-02-26"]["provider_red_band_m3s"],
        )

    def test_no_negative_control_is_fabricated(self):
        n = self.case["negative_control_status"]
        self.assertEqual(n["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")
        self.assertFalse(n["verified_negative_control"])
        limits = " ".join(self.evidence["scientific_limits"]).lower()
        self.assertIn("no confirmed hydrologic negative control", limits)

    def test_official_spatial_context_is_not_event_footprint(self):
        s = self.case["spatial_context"]
        self.assertEqual(s["status"], "PARTIAL_OFFICIAL_CONTEXT_NOT_NORMALIZED_BASIN_GEOMETRY")
        self.assertFalse(s["observed_event_footprint_available"])
        self.assertFalse(s["complete_machine_readable_basin_geometry_available"])
        self.assertFalse(self.evidence["geometry_and_exposure_context"]["river_margin"]["machine_readable_geometry_normalized_in_irfen"])

    def test_phase2_zone_contract_remains_draft_and_blocked(self):
        self.assertEqual(self.contract["contract_status"], "DRAFT")
        self.assertEqual(self.contract["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(self.contract["production_use"])
        self.assertFalse(self.contract["alerting_enabled"])
        self.assertIsNone(self.contract["decision_thresholds"])
        self.assertEqual(self.contract["validation"]["activation_gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
