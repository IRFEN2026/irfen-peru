import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/la_leche_pacora_pitipo_1998_2025.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/la_leche_pacora_pitipo_official_context_1998_2025.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lambayeque_motupe_la_leche_pitipo.json"


class LaLechePacoraPitipoResearchCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
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

    def test_multiple_official_positive_outcomes_are_retained(self):
        ids = {row["control_id"] for row in self.case["positive_controls"]}
        self.assertEqual(ids, {
            "LA-LECHE-PACORA-1998-01-25",
            "LA-LECHE-PACORA-2015-03-23",
            "LA-LECHE-PACORA-2015-03-31",
            "LA-LECHE-PITIPO-2025-02-11",
        })
        self.assertGreaterEqual(len(self.evidence["historical_positive_outcomes"]), 4)

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

    def test_hydrologic_identity_is_context_not_event_footprint(self):
        identity = self.case["hydrologic_identity"]
        self.assertEqual(identity["ana_hydrologic_unit_code"], "137772")
        self.assertEqual(identity["la_leche_watercourse_code"], "1377722")
        self.assertFalse(identity["whole_unit_geometry_is_event_footprint"])
        self.assertFalse(identity["machine_readable_geometry_normalized_in_irfen"])

    def test_bounded_component_does_not_close_compound_system(self):
        sep = self.case["component_separation"]
        self.assertTrue(sep["la_leche_river_component_closed_for_research"])
        self.assertFalse(sep["motupe_river_component_resolved"])
        self.assertFalse(sep["local_ravine_contributions_resolved"])
        self.assertFalse(sep["event_specific_hydraulic_routing_validated"])
        self.assertFalse(sep["current_channel_capacity_validated"])
        self.assertFalse(sep["full_phase2_contract_approved"])

    def test_current_protection_project_is_not_backcast(self):
        context = self.evidence["current_exposure_and_mitigation_context"]
        self.assertEqual(context["role"], "CURRENT_EXPOSURE_AND_MITIGATION_CONTEXT_ONLY")
        self.assertTrue(context["forbidden_backcast"])
        case_context = self.case["current_mitigation_context"]
        self.assertFalse(case_context["historical_backcast_allowed"])
        self.assertFalse(case_context["hydraulic_capacity_inference_allowed"])

    def test_contract_remains_draft_blocked_and_unpromoted(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "DRAFT")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["hazard_model"]["mechanism_status"], "TO_BE_RESOLVED")
        self.assertEqual(c["assets"]["geometry"]["status"], "MISSING")
        self.assertEqual(c["assets"]["observations"]["status"], "MISSING")
        self.assertEqual(c["assets"]["historical_events"]["status"], "MISSING")
        self.assertEqual(c["assets"]["exposure"]["status"], "MISSING")
        self.assertEqual(c["assets"]["hydraulic_context"]["status"], "MISSING")
        self.assertEqual(c["official_source_ids"], [
            "CENEPRED-EVAR-PITIPO-SECTOR-1",
            "ANA-CENEPRED-CRITICAL-POINTS-2025",
        ])

    def test_no_threshold_or_numeric_hydraulic_promotion(self):
        self.assertIsNone(self.evidence["decision_thresholds"])
        forbidden = set(self.evidence["forbidden_uses"])
        self.assertIn("operational threshold derivation", forbidden)
        self.assertIn("event-day discharge inference", forbidden)
        self.assertIsNone(self.contract["hydraulic_factors"])


if __name__ == "__main__":
    unittest.main()
