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


class ExternalEvidenceQueueTests(unittest.TestCase):
    def test_pending_evidence_is_exposed_without_automatic_acceptance(self):
        contract = {
            "production_use": False,
            "pilots": [
                {
                    "zone_id": "san_ildefonso",
                    "required_evidence_ids": ["capacity", "maintenance"],
                }
            ],
        }
        ledger = {
            "production_use": False,
            "pilots": [
                {
                    "zone_id": "san_ildefonso",
                    "items": [
                        {
                            "evidence_id": "capacity",
                            "status": "PARTIAL_CANDIDATE_REVIEW",
                            "official_sources": ["https://www.gob.pe/example"],
                            "remaining_gap": "Falta memoria as-built.",
                        }
                    ],
                }
            ],
        }

        passed, evidence = scorecard.external_validation_gate(
            contract, ledger, ["san_ildefonso"]
        )

        self.assertFalse(passed)
        queue = evidence["san_ildefonso"]["review_queue"]
        self.assertEqual([row["evidence_id"] for row in queue], ["capacity", "maintenance"])
        self.assertEqual(queue[0]["official_source_count"], 1)
        self.assertEqual(queue[0]["remaining_gap"], "Falta memoria as-built.")
        self.assertEqual(queue[1]["status"], "MISSING")
        self.assertTrue(all(row["named_human_review_required"] for row in queue))
        self.assertTrue(all(row["automatic_acceptance_forbidden"] for row in queue))

    def test_fully_reviewed_evidence_is_removed_from_queue(self):
        contract = {
            "production_use": False,
            "pilots": [
                {"zone_id": "catacaos", "required_evidence_ids": ["river_state"]}
            ],
        }
        ledger = {
            "production_use": False,
            "pilots": [
                {
                    "zone_id": "catacaos",
                    "items": [
                        {
                            "evidence_id": "river_state",
                            "status": "ACCEPTED",
                            "official_sources": ["https://www.senamhi.gob.pe/example"],
                            "review": {
                                "reviewed_by": "Revisor identificado",
                                "reviewed_at": "2026-08-17T12:00:00Z",
                                "automatic": False,
                            },
                        }
                    ],
                }
            ],
        }

        passed, evidence = scorecard.external_validation_gate(
            contract, ledger, ["catacaos"]
        )

        self.assertTrue(passed)
        self.assertEqual(evidence["catacaos"]["review_queue"], [])


if __name__ == "__main__":
    unittest.main()
