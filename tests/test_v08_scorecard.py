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
        "archived_at": "2026-08-15T00:10:00Z",
        "production_use": False,
        "outcome_verification": {
            "status": "REVIEWED_REAL_WORLD_OUTCOME",
            "label": "NONE",
            "verified_event": None,
            "official_source": ["https://portal.indeci.gob.pe/emergencias/"],
            "reviewed_at": "2026-08-16T00:00:00Z",
            "reviewed_by": "Revisor humano identificado",
            "automatic": False,
            "comprehensive_none_coverage": True,
            "counts_toward_closeout": True,
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

    def test_late_same_day_snapshot_is_not_eligible(self):
        record = eligible_record()
        record["archived_at"] = "2026-08-15T17:30:00Z"

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["snapshot_captured_within_pre_outcome_window"])

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

    def test_accepted_label_without_named_reviewer_is_rejected(self):
        record = eligible_record()
        record["outcome_verification"]["reviewed_by"] = None

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["outcome_named_human_reviewer"])

    def test_none_requires_explicit_comprehensive_coverage(self):
        record = eligible_record()
        record["outcome_verification"]["comprehensive_none_coverage"] = False

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["outcome_label_semantics_supported"])

    def test_nonofficial_outcome_source_is_rejected(self):
        record = eligible_record()
        record["outcome_verification"]["official_source"] = ["https://example.com/report"]

        result = scorecard.shadow_record_eligibility(record, PILOTS, 30)

        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["outcome_official_sources_recorded"])


class ShadowOutcomeReviewQueueTests(unittest.TestCase):
    def queue(self, records, evidence=None):
        return scorecard.shadow_outcome_review_queue(
            records,
            evidence or {"records": []},
            PILOTS,
            30,
            {"EVENT", "NONE"},
        )

    def test_pending_day_without_official_match_waits_without_auto_none(self):
        record = eligible_record()
        record["outcome_verification"] = {
            "status": "PENDING_REAL_WORLD_OUTCOME_REVIEW",
            "label": None,
        }

        queue = self.queue([record])

        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["action"], "WAIT_FOR_OFFICIAL_EVIDENCE")
        self.assertEqual(queue[0]["official_pilot_specific_link_count"], 0)
        self.assertIn("outcome_label_accepted", queue[0]["failed_eligibility_check_ids"])
        self.assertTrue(queue[0]["automatic_outcome_classification_forbidden"])
        self.assertTrue(queue[0]["missing_evidence_is_not_none"])
        self.assertFalse(queue[0]["counts_toward_closeout"])

    def test_uncertain_review_remains_queued(self):
        record = eligible_record()
        record["outcome_verification"]["label"] = "UNCERTAIN"

        queue = self.queue([record])

        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["current_label"], "UNCERTAIN")
        self.assertEqual(queue[0]["action"], "WAIT_FOR_OFFICIAL_EVIDENCE")

    def test_exact_official_link_routes_to_human_review_only(self):
        record = eligible_record()
        record["outcome_verification"] = {
            "status": "PENDING_REAL_WORLD_OUTCOME_REVIEW",
            "label": None,
        }
        evidence = {
            "records": [{
                "snapshot_date_utc": "2026-08-15",
                "captures": [{
                    "captured_at": "2026-08-16T03:00:00Z",
                    "sources": [{
                        "summary": {
                            "pilot_report_links_for_snapshot_date": [
                                {"url": "https://portal.indeci.gob.pe/exact-pilot-report"}
                            ]
                        }
                    }],
                }],
            }],
        }

        queue = self.queue([record], evidence)

        self.assertEqual(queue[0]["official_pilot_specific_link_count"], 1)
        self.assertEqual(queue[0]["action"], "HUMAN_REVIEW_REQUIRED")
        self.assertTrue(queue[0]["automatic_outcome_classification_forbidden"])

    def test_eligible_accepted_outcome_is_removed_from_queue(self):
        self.assertEqual(self.queue([eligible_record()]), [])


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
