import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_v08_scorecard", ROOT / "scripts/build_v08_scorecard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scorecard = load_script()
PILOTS = ["san_ildefonso", "chosica", "catacaos"]


def eligible_record():
    return {
        "snapshot_date_utc": "2026-08-15",
        "production_use": False,
        "outcome_verification": {
            "status": "REVIEWED_REAL_WORLD_OUTCOME",
            "label": "NONE",
            "reviewed_at": "2026-08-16T00:00:00Z",
        },
        "zones": [
            {
                "zone_id": zone_id,
                "recommendation": {
                    "code": "TEST_MONITOR",
                    "mode": "TEST_ONLY",
                    "operational_alert": False,
                },
            }
            for zone_id in PILOTS
        ],
        "source_health": {
            "forecast_available": True,
            "forecast_verification_pairs_by_zone": {zone_id: 30 for zone_id in PILOTS},
            "imerg_early_status": "EARLY_HALFHOURLY_SOURCE_AVAILABLE",
            "imerg_early_latency_hours": 5.5,
            "regression_status": "PASS",
        },
    }


class ShadowEligibilityTests(unittest.TestCase):
    def test_complete_pre_outcome_snapshot_is_eligible(self):
        result = scorecard.shadow_record_eligibility(eligible_record(), PILOTS, 30)
        self.assertTrue(result["eligible"])
        self.assertTrue(all(result["checks"].values()))

    def test_aggregate_pair_total_cannot_replace_per_pilot_maturity(self):
        record = eligible_record()
        record["source_health"]["forecast_verification_pairs"] = 120
        del record["source_health"]["forecast_verification_pairs_by_zone"]

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["forecast_pairs_mature_at_snapshot"])

    def test_missing_data_is_not_an_eligible_dry_day(self):
        record = eligible_record()
        record["source_health"]["imerg_early_status"] = "SOURCE_TEMPORARILY_UNREACHABLE"
        record["source_health"]["imerg_early_latency_hours"] = None

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["imerg_early_available"])
        self.assertFalse(result["checks"]["imerg_latency_recorded"])

    def test_review_before_day_close_is_not_eligible(self):
        record = eligible_record()
        record["outcome_verification"]["reviewed_at"] = "2026-08-15T23:59:59Z"

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["outcome_review_after_utc_day_close"])

    def test_operational_recommendation_is_rejected(self):
        record = eligible_record()
        record["zones"][0]["recommendation"]["operational_alert"] = True

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["all_recommendations_test_only"])


if __name__ == "__main__":
    unittest.main()
