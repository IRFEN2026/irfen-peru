import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "site/data/validation/phase2_case_validations/pisco_humay_2023_2024.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/pisco_humay_official_context_2023_2025.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/ica_pisco_san_andres.json"
MAP_CATALOG = ROOT / "site/data/map_layers.json"


# Generated catalog parity is enforced by the global onboarding tests.
class PiscoHumayResearchCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(CASE.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.map_catalog = json.loads(MAP_CATALOG.read_text(encoding="utf-8"))

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

    def test_official_positive_sequence_is_retained(self):
        ids = {row["control_id"] for row in self.case["positive_controls"]}
        self.assertEqual(ids, {
            "PISCO-HUMAY-2023-02-02",
            "PISCO-HUMAY-2024-01-30",
            "PISCO-HUMAY-2024-02-28",
            "PISCO-HUMAY-2024-03-03",
        })

    def test_tambo_colorado_erosion_is_not_mislabeled_as_overflow(self):
        row = next(r for r in self.evidence["confirmed_positive_outcomes"]
                   if r["case_id"] == "PISCO-HUMAY-2024-03-03")
        self.assertEqual(row["classification"], "CONFIRMED_POSITIVE_FLUVIAL_EROSION_OUTCOME")
        self.assertIn("not relabeled as a river-overflow outcome", row["mechanism_caution"])

    def test_no_negative_control_is_fabricated(self):
        self.assertEqual(self.case["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")
        self.assertEqual(self.case["negative_control_status"]["verified_negative_controls"], [])
        self.assertEqual(self.evidence["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")

    def test_letrayoc_context_is_not_transferred_to_humay(self):
        ctx = self.case["hydrologic_monitoring_context"]
        self.assertEqual(ctx["station"], "Letrayoc")
        self.assertFalse(ctx["event_paired_numeric_series_ingested"])
        self.assertFalse(ctx["station_to_humay_transfer_validated"])
        self.assertFalse(ctx["travel_time_validated"])
        self.assertFalse(ctx["downstream_channel_capacity_validated"])
        self.assertFalse(ctx["operational_threshold_derived"])

    def test_san_andres_canal_mechanism_stays_separate(self):
        sep = self.evidence["san_andres_mechanism_separation"]
        self.assertEqual(sep["observed_mechanism"], "CANAL_DE_REGADIO_OVERFLOW")
        self.assertFalse(sep["rio_pisco_overflow_control"])
        self.assertFalse(sep["san_andres_river_component_resolved"])
        case_sep = self.case["mechanism_separation"]
        self.assertFalse(case_sep["san_andres_local_drainage_component_resolved"])
        self.assertFalse(case_sep["canal_overflow_is_rio_pisco_overflow"])

    def test_current_critical_points_are_not_historical_event_footprint(self):
        ctx = self.evidence["current_critical_point_context"]
        self.assertEqual(ctx["role"], "CURRENT_OFFICIAL_CRITICAL_POINT_AND_PREVENTION_CONTEXT_NOT_EVENT_FOOTPRINT")
        self.assertFalse(ctx["historical_backcast_allowed"])
        self.assertFalse(ctx["channel_capacity_validated"])

    def test_contract_remains_draft_blocked_and_incomplete(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "DRAFT")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["hazard_model"]["mechanism_status"], "TO_BE_RESOLVED")
        self.assertEqual(c["assets"]["geometry"]["status"], "MISSING")
        self.assertEqual(c["assets"]["historical_events"]["status"], "READY")
        self.assertEqual(c["assets"]["observations"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["exposure"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["hydraulic_context"]["status"], "PARTIAL")


    def test_missing_pisco_geometry_remains_withheld_from_map(self):
        row = next(
            z for z in self.map_catalog["research_zones"]
            if z["candidate_id"] == "ica_pisco_san_andres"
        )
        self.assertEqual(row["geometry"]["status"], "MISSING")
        self.assertFalse(row["geometry"]["map_eligible"])
        self.assertEqual(row["geometry"]["representation"], "NOT_MAPPED_NO_REPRODUCIBLE_FILE")

    def test_no_threshold_or_hydraulic_promotion(self):
        self.assertIsNone(self.evidence["decision_thresholds"])
        forbidden = set(self.evidence["forbidden_uses"])
        self.assertIn("operational threshold derivation", forbidden)
        self.assertIn("station-to-impact-reach hydraulic transfer", forbidden)


if __name__ == "__main__":
    unittest.main()

# Catalog regeneration marker: Phase2 and map catalogs regenerated from current contract.
