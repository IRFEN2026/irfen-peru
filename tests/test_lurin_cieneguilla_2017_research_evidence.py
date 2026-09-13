import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT = ROOT / "site/data/validation/phase2_research_evidence/senamhi_lurin_antapucro_2017.json"
HYDRAULIC = ROOT / "site/data/validation/phase2_research_evidence/ana_lurin_hydraulic_context_2019.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_lurin_cieneguilla.json"


class LurinCieneguilla2017ResearchEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.event = json.loads(EVENT.read_text(encoding="utf-8"))
        cls.hydraulic = json.loads(HYDRAULIC.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_evidence_remains_research_only_and_non_operational(self):
        for e in (self.event, self.hydraulic):
            self.assertEqual(e["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(e["test_mode"], "TEST_ONLY")
            self.assertFalse(e["production_use"])
            self.assertFalse(e["production_ready"])
            self.assertFalse(e["operational_alerting_enabled"])
            self.assertIsNone(e["decision_thresholds"])

    def test_antapucro_event_day_flow_is_not_transferred_to_impact_reach(self):
        ctx = self.event["event_day_hydrologic_context"]
        self.assertEqual(ctx["date_local"], "2017-03-14")
        self.assertEqual(ctx["reported_flow_m3s"], 77.23)
        self.assertEqual(ctx["reported_anomaly_percent_above_historical_mean"], 251)
        self.assertEqual(ctx["station_scope"], "ANTAPUCRO_NOT_LOCAL_IMPACT_REACH")
        self.assertFalse(ctx["transfer_to_pachacamac_impact_reach_validated"])
        self.assertFalse(ctx["travel_time_validated"])
        self.assertFalse(ctx["receiving_channel_capacity_validated"])

    def test_forecast_values_are_not_observations_or_thresholds(self):
        forecast = self.event["model_forecast_separated_from_observation"]
        self.assertEqual(forecast["evidence_class"], "MODEL_FORECAST_NOT_OBSERVED")
        self.assertEqual(forecast["forecast_horizon_hours"], [24, 48, 72])
        self.assertFalse(self.event["historical_alert_line_policy"]["alert_line_values_ingested_as_thresholds"])
        self.assertFalse(self.event["historical_alert_line_policy"]["decision_thresholds_derived"])

    def test_cieneguilla_no_damage_candidate_is_not_verified_negative(self):
        controls = {x["case_id"]: x for x in self.event["outcome_links"]}
        candidate = controls["cieneguilla_2017_03_06"]
        self.assertEqual(candidate["role"], "UNADJUDICATED_NO_DAMAGE_CONTROL_CANDIDATE")
        self.assertFalse(candidate["verified_negative_control"])
        self.assertFalse(candidate["same_day_hydrologic_context_available_here"])

    def test_contract_progress_is_partial_only(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "DRAFT")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["hazard_model"]["mechanism_status"], "TO_BE_RESOLVED")
        self.assertEqual(c["assets"]["geometry"]["status"], "MISSING")
        self.assertEqual(c["assets"]["exposure"]["status"], "MISSING")
        self.assertEqual(c["assets"]["historical_events"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["observations"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["hydraulic_context"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["forecast"]["status"], "CANDIDATE")

    def test_ana_context_does_not_become_event_day_state(self):
        self.assertEqual(self.hydraulic["evidence_class"], "OFFICIAL_BASIN_HYDROLOGIC_AND_HYDRAULIC_CONTEXT")
        forbidden = set(self.hydraulic["forbidden_uses"])
        self.assertIn("event_day_abstraction_assumption", forbidden)
        self.assertIn("automatic_station_to_impact_reach_transfer", forbidden)
        self.assertIn("operational_threshold_derivation", forbidden)


if __name__ == "__main__":
    unittest.main()
