from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import json
import unittest

from scripts.build_shadow_review_queue import (
    ACCEPTED_STORED_LABELS,
    FLOW_STATES,
    artifact_refresh_required,
    build_queue,
    file_sha256,
    material_evaluation_time,
    parse_utc,
)
from scripts.build_v08_scorecard import shadow_record_eligibility

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/v08_closeout_contract.json"
SCHEMA_PATH = ROOT / "config/shadow_review_queue.schema.v1.json"
ARCHIVE_PATH = ROOT / "site/data/validation/shadow_runs.json"
QUEUE_PATH = ROOT / "site/data/validation/shadow_review_queue.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def recommendations(available_future_hours: int = 85):
    return [
        {
            "zone_id": pilot,
            "forecast_mm": {"available_future_hours": available_future_hours},
            "recommendation": {
                "code": "TEST_NO_TRIGGER",
                "mode": "TEST_ONLY",
                "operational_alert": False,
            },
        }
        for pilot in ("san_ildefonso", "chosica", "catacaos")
    ]


def complete_record(snapshot_date="2026-08-20", *, op_status="updated"):
    target = date.fromisoformat(snapshot_date)
    captured = datetime.combine(
        target - timedelta(days=1), time(hour=14), tzinfo=timezone.utc
    )
    start = datetime.combine(
        target - timedelta(days=1), time(hour=12), tzinfo=timezone.utc
    )
    end = datetime.combine(target, time(hour=2), tzinfo=timezone.utc)
    return {
        "snapshot_date_utc": snapshot_date,
        "archived_at": captured.isoformat(),
        "pre_outcome_capture_window": {
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "captured_within_window": True,
        },
        "zones": recommendations(),
        "operational_dataset_status": op_status,
        "source_health": {
            "forecast_available": True,
            "forecast_covers_target_day": True,
            "forecast_verification_pairs_by_zone": {
                "san_ildefonso": 30,
                "chosica": 30,
                "catacaos": 30,
            },
            "imerg_early_status": "EARLY_HALFHOURLY_SOURCE_AVAILABLE",
            "imerg_early_latency_hours": 5.5,
            "regression_status": "PASS",
        },
        "outcome_verification": {
            "status": "PENDING_REAL_WORLD_OUTCOME_REVIEW",
            "label": None,
            "verified_event": None,
            "official_source": None,
        },
        "production_use": False,
    }


def archive_for(*records, declared=None, updated_at="2026-08-21T12:00:00+00:00"):
    return {
        "version": "0.8-experimental",
        "production_use": False,
        "production_ready": False,
        "updated_at": updated_at,
        "record_count": len(records) if declared is None else declared,
        "records": list(records),
    }


def reviewed_event(record=None, *, source="https://portal.indeci.gob.pe/emergencias/"):
    record = deepcopy(record or complete_record())
    snapshot = date.fromisoformat(record["snapshot_date_utc"])
    reviewed_at = datetime.combine(
        snapshot + timedelta(days=1), time(hour=3), tzinfo=timezone.utc
    )
    record["outcome_verification"] = {
        "status": "REVIEWED_REAL_WORLD_OUTCOME",
        "label": "EVENT",
        "verified_event": "Evento oficial pertinente al piloto.",
        "official_source": [source],
        "reviewed_at": reviewed_at.isoformat(),
        "reviewed_by": "human-reviewer",
        "automatic": False,
        "review_window_closed_utc": datetime.combine(
            snapshot + timedelta(days=1), time.min, tzinfo=timezone.utc
        ).isoformat(),
        "comprehensive_none_coverage": False,
        "counts_toward_closeout": True,
    }
    return record


class ShadowReviewQueueUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load(CONTRACT_PATH)
        cls.as_of = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)

    def build(self, archive, *, as_of=None):
        return build_queue(
            archive,
            self.contract,
            evaluation_as_of=as_of or self.as_of,
            schema_sha256=file_sha256(SCHEMA_PATH),
        )

    def test_stale_is_annotation_not_new_gate(self):
        artifact = self.build(archive_for(complete_record(op_status="stale")))
        day = artifact["days"][0]
        self.assertEqual(day["flow_state"], "READY_FOR_HUMAN_REVIEW")
        self.assertTrue(day["technical_eligibility"])
        self.assertEqual(day["operational_dataset_status"]["role"], "ANNOTATION_ONLY")
        self.assertFalse(day["operational_dataset_status"]["is_eligibility_gate"])
        self.assertNotIn("OPERATIONAL_DATASET_STATUS", day["failed_gates"])
        self.assertFalse(artifact["guards"]["stale_is_gate"])

    def test_pending_record_never_receives_automatic_event_or_none(self):
        artifact = self.build(archive_for(complete_record()))
        review = artifact["days"][0]["human_review"]
        self.assertIsNone(review["stored_label"])
        self.assertEqual(review["evidence_state"], "UNKNOWN")
        self.assertNotIn(review["stored_label"], {"EVENT", "NONE"})
        self.assertFalse(artifact["guards"]["automatic_event_none_classification_enabled"])

    def test_absent_archived_at_fails_closed_as_unknown(self):
        record = complete_record()
        record.pop("pre_outcome_capture_window")
        record["archived_at"] = None
        record["source_health"]["imerg_early_status"] = None
        record["source_health"]["imerg_early_latency_hours"] = None
        artifact = self.build(archive_for(record))
        day = artifact["days"][0]
        self.assertEqual(day["flow_state"], "TECHNICALLY_INELIGIBLE")
        self.assertEqual(day["capture_window"]["evidence_state"], "UNKNOWN")
        self.assertEqual(day["human_review"]["evidence_state"], "UNKNOWN")
        self.assertFalse(day["closeout_eligible"])
        self.assertIn("CAPTURED_WITHIN_WINDOW", day["failed_gates"])
        self.assertIn("IMERG_EARLY_AVAILABLE", day["failed_gates"])

    def test_missing_stored_window_uses_reproducible_archived_at_calculation(self):
        record = complete_record()
        record.pop("pre_outcome_capture_window")
        artifact = self.build(archive_for(record))
        day = artifact["days"][0]
        self.assertEqual(day["capture_window"]["evidence_state"], "CALCULATED")
        self.assertTrue(day["capture_window"]["computed_captured_within_window"])
        self.assertTrue(day["technical_eligibility"])

    def test_day_not_closed_precedes_review_readiness(self):
        record = complete_record("2026-08-25")
        artifact = self.build(
            archive_for(record),
            as_of=datetime(2026, 8, 24, 19, tzinfo=timezone.utc),
        )
        day = artifact["days"][0]
        self.assertEqual(day["flow_state"], "DAY_NOT_CLOSED")
        self.assertFalse(day["day_closed_utc"])
        self.assertIn("DAY_CLOSED_UTC", day["failed_gates"])

    def test_reviewed_uncertain_preserves_human_label_without_counting(self):
        record = complete_record()
        record["outcome_verification"] = {
            "status": "REVIEWED_REAL_WORLD_OUTCOME",
            "label": "UNCERTAIN",
            "verified_event": None,
            "official_source": ["https://www.senamhi.gob.pe/"],
            "reviewed_at": "2026-08-21T03:00:00+00:00",
            "reviewed_by": "human-reviewer",
            "automatic": False,
            "review_window_closed_utc": "2026-08-21T00:00:00+00:00",
            "comprehensive_none_coverage": False,
            "counts_toward_closeout": False,
        }
        artifact = self.build(archive_for(record))
        day = artifact["days"][0]
        self.assertEqual(day["flow_state"], "REVIEWED_UNCERTAIN")
        self.assertEqual(day["human_review"]["stored_label"], "UNCERTAIN")
        self.assertFalse(day["closeout_eligible"])
        self.assertEqual(artifact["summary"]["label_counts"]["UNCERTAIN"], 1)

    def test_event_requires_complete_human_contract_and_exact_scorecard_parity(self):
        event = reviewed_event()
        artifact = self.build(archive_for(event))
        day = artifact["days"][0]
        self.assertEqual(day["flow_state"], "ELIGIBLE_EVENT")
        self.assertTrue(day["closeout_eligible"])
        self.assertEqual(day["closeout_eligible"], day["scorecard_eligibility"]["eligible"])

        broken = deepcopy(event)
        broken["outcome_verification"]["reviewed_by"] = None
        artifact = self.build(archive_for(broken))
        day = artifact["days"][0]
        self.assertEqual(day["flow_state"], "TECHNICALLY_INELIGIBLE")
        self.assertFalse(day["closeout_eligible"])
        self.assertIn("HUMAN_REVIEWER_IDENTIFIED", day["failed_gates"])

    def test_review_before_utc_day_close_never_eligible(self):
        event = reviewed_event()
        event["outcome_verification"]["reviewed_at"] = "2026-08-20T23:59:59+00:00"
        artifact = self.build(archive_for(event))
        day = artifact["days"][0]
        self.assertFalse(day["closeout_eligible"])
        self.assertFalse(day["human_review"]["review_after_utc_day_close"])
        self.assertIn("REVIEW_AFTER_UTC_DAY_CLOSE", day["failed_gates"])
        codes = {row["code"] for row in artifact["inconsistencies"]}
        self.assertIn("REVIEW_BEFORE_UTC_DAY_CLOSE", codes)

    def test_non_official_url_does_not_satisfy_source_gate(self):
        event = reviewed_event(source="https://example.com/unverified")
        artifact = self.build(archive_for(event))
        day = artifact["days"][0]
        self.assertFalse(day["closeout_eligible"])
        self.assertFalse(day["human_review"]["official_sources_valid"])
        self.assertIn("OFFICIAL_SOURCES_VALID", day["failed_gates"])
        codes = {row["code"] for row in artifact["inconsistencies"]}
        self.assertIn("REVIEWED_WITH_NON_OFFICIAL_SOURCE", codes)

    def test_stored_capture_window_mismatch_is_exposed(self):
        record = complete_record()
        record["pre_outcome_capture_window"]["captured_within_window"] = False
        artifact = self.build(archive_for(record))
        day = artifact["days"][0]
        self.assertTrue(day["capture_window"]["computed_captured_within_window"])
        self.assertFalse(day["capture_window"]["stored_captured_within_window"])
        codes = {row["code"] for row in artifact["inconsistencies"]}
        self.assertIn("CAPTURE_WINDOW_STORED_COMPUTED_MISMATCH", codes)

    def test_stored_forecast_coverage_mismatch_is_exposed(self):
        record = complete_record()
        record["source_health"]["forecast_covers_target_day"] = False
        artifact = self.build(archive_for(record))
        day = artifact["days"][0]
        self.assertTrue(day["forecast"]["computed_covers_target_day"])
        self.assertFalse(day["forecast"]["stored_covers_target_day"])
        codes = {row["code"] for row in artifact["inconsistencies"]}
        self.assertIn("FORECAST_COVERAGE_STORED_COMPUTED_MISMATCH", codes)

    def test_day_transition_occurs_without_source_change(self):
        record = complete_record("2026-08-25")
        archive = archive_for(record, updated_at="2026-08-24T14:00:00+00:00")
        before = self.build(
            archive, as_of=datetime(2026, 8, 25, 23, 59, tzinfo=timezone.utc)
        )
        after = self.build(
            archive, as_of=datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(before["days"][0]["flow_state"], "DAY_NOT_CLOSED")
        self.assertEqual(after["days"][0]["flow_state"], "READY_FOR_HUMAN_REVIEW")
        stale, reasons = artifact_refresh_required(
            before, datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)
        )
        self.assertTrue(stale)
        self.assertIn("NEXT_TRANSITION_REACHED", reasons)

    def test_material_evaluation_time_does_not_churn_by_seconds(self):
        record = complete_record("2026-08-25")
        archive = archive_for(record, updated_at="2026-08-24T14:00:00+00:00")
        a = material_evaluation_time(
            archive, datetime(2026, 8, 25, 17, 1, 2, tzinfo=timezone.utc)
        )
        b = material_evaluation_time(
            archive, datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc)
        )
        self.assertEqual(a, b)
        self.assertEqual(a, datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc))
        c = material_evaluation_time(
            archive, datetime(2026, 8, 26, 0, 0, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(c, datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc))

    def test_detects_record_count_status_label_and_eligibility_conflicts(self):
        record = complete_record()
        record["outcome_verification"] = {
            "status": "PENDING_REAL_WORLD_OUTCOME_REVIEW",
            "label": "NONE",
            "reviewed_by": None,
            "official_source": None,
            "automatic": True,
            "comprehensive_none_coverage": False,
            "counts_toward_closeout": True,
        }
        artifact = self.build(archive_for(record, declared=7))
        codes = {row["code"] for row in artifact["inconsistencies"]}
        self.assertIn("RECORD_COUNT_MISMATCH", codes)
        self.assertIn("PENDING_STATUS_WITH_STORED_LABEL", codes)
        self.assertIn("COUNTS_TRUE_BUT_NOT_ELIGIBLE", codes)
        self.assertEqual(artifact["status"], "INCONSISTENCIES_DETECTED")

    def test_only_allowed_flow_states_and_stored_labels_are_emitted(self):
        artifact = self.build(archive_for(complete_record()))
        for day in artifact["days"]:
            self.assertIn(day["flow_state"], FLOW_STATES)
            label = day["human_review"]["stored_label"]
            self.assertTrue(label is None or label in ACCEPTED_STORED_LABELS)


class ShadowReviewQueueRepositoryRegressionTests(unittest.TestCase):
    def test_repository_artifact_is_reproducible_at_its_recorded_as_of(self):
        archive = load(ARCHIVE_PATH)
        contract = load(CONTRACT_PATH)
        current = load(QUEUE_PATH)
        as_of = parse_utc(current.get("evaluation_as_of_utc"))
        self.assertIsNotNone(as_of)
        rebuilt = build_queue(
            archive,
            contract,
            evaluation_as_of=as_of,
            schema_sha256=file_sha256(SCHEMA_PATH),
        )
        self.assertEqual(current, rebuilt)

    def test_queue_and_scorecard_eligibility_are_identical_for_all_current_days(self):
        archive = load(ARCHIVE_PATH)
        contract = load(CONTRACT_PATH)
        queue = load(QUEUE_PATH)
        pilots = list(contract.get("pilot_zone_ids") or [])
        minimum = int(
            (contract.get("forecast_verification") or {}).get(
                "minimum_mature_pairs_per_pilot", 30
            )
        )
        shadow = contract.get("shadow_validation") or {}
        accepted = set(shadow.get("accepted_outcome_labels") or [])
        capture = shadow.get("snapshot_capture") or {}
        lead = int(capture.get("earliest_eligible_capture_lead_minutes", 720))
        delay = int(capture.get("latest_eligible_capture_delay_minutes", 120))
        by_date = {row["snapshot_date_utc"]: row for row in queue["days"]}
        for record in archive.get("records") or []:
            expected = shadow_record_eligibility(
                record, pilots, minimum, accepted, lead, delay
            )
            actual = by_date[record["snapshot_date_utc"]]
            self.assertEqual(actual["scorecard_eligibility"], expected)
            self.assertEqual(actual["closeout_eligible"], expected["eligible"])

    def test_known_cut_without_permanent_queue_constants(self):
        archive = load(ARCHIVE_PATH)
        artifact = load(QUEUE_PATH)
        summary = artifact["summary"]
        records = archive.get("records") or []
        expected_uncertain = sum(
            1
            for row in records
            if (row.get("outcome_verification") or {}).get("label") == "UNCERTAIN"
        )
        expected_pending = sum(
            1
            for row in records
            if (row.get("outcome_verification") or {}).get("status")
            == "PENDING_REAL_WORLD_OUTCOME_REVIEW"
            and (row.get("outcome_verification") or {}).get("label") is None
        )
        self.assertEqual(summary["record_count_actual"], len(records))
        self.assertEqual(summary["label_counts"]["UNCERTAIN"], expected_uncertain)
        self.assertEqual(summary["label_counts"]["PENDING"], expected_pending)
        self.assertEqual(
            summary["closeout_eligible_total"],
            sum(1 for day in artifact["days"] if day["closeout_eligible"]),
        )
        if archive.get("updated_at") == "2026-08-24T14:27:20.242799+00:00":
            self.assertEqual(summary["record_count_actual"], 11)
            self.assertEqual(summary["label_counts"]["UNCERTAIN"], 5)
            self.assertEqual(summary["label_counts"]["PENDING"], 6)
            self.assertEqual(summary["closeout_eligible_total"], 0)

    def test_eight_historical_findings_remain_visible_without_repair(self):
        artifact = load(QUEUE_PATH)
        codes = [row["code"] for row in artifact["inconsistencies"]]
        self.assertEqual(codes.count("REVIEWED_WITHOUT_IDENTIFIED_REVIEWER"), 5)
        self.assertEqual(
            codes.count("REVIEWED_WITHOUT_EXPLICIT_AUTOMATIC_FALSE"), 3
        )
        self.assertEqual(artifact["summary"]["inconsistency_count"], 8)

    def test_schema_and_safety_guards_are_versioned(self):
        schema = load(SCHEMA_PATH)
        artifact = load(QUEUE_PATH)
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0.0")
        self.assertEqual(artifact["schema_version"], "1.0.0")
        self.assertEqual(
            artifact["source"]["methodology"],
            "CANONICAL_ARCHIVE_PLUS_VERSIONED_CLOSEOUT_CONTRACT_AND_SCORECARD_PARITY",
        )
        self.assertFalse(artifact["guards"]["production_use"])
        self.assertFalse(artifact["guards"]["production_ready"])
        self.assertFalse(artifact["guards"]["operational_alerting_enabled"])
        self.assertFalse(
            artifact["guards"]["automatic_event_none_classification_enabled"]
        )
        self.assertFalse(artifact["guards"]["operational_dataset_status_is_gate"])
        self.assertFalse(artifact["guards"]["stale_is_gate"])
        self.assertEqual(
            artifact["freshness"]["basis"], "SOURCE_UPDATE_OR_UTC_DAY_CLOSE"
        )

    def test_current_artifact_is_not_stale_at_its_material_evaluation(self):
        artifact = load(QUEUE_PATH)
        as_of = parse_utc(artifact["evaluation_as_of_utc"])
        stale, reasons = artifact_refresh_required(artifact, as_of)
        self.assertFalse(stale, reasons)


class ShadowReviewQueueIntegrationTests(unittest.TestCase):
    def test_workflows_rebuild_and_persist_atomic_package_with_pr133_guards(self):
        shadow = (ROOT / ".github/workflows/shadow-validation.yml").read_text(
            encoding="utf-8"
        )
        review = (ROOT / ".github/workflows/review-shadow-outcome.yml").read_text(
            encoding="utf-8"
        )
        for workflow in (shadow, review):
            self.assertIn("python scripts/build_shadow_review_queue.py", workflow)
            self.assertIn("python scripts/build_shadow_review_queue.py --check", workflow)
            self.assertIn("site/data/validation/shadow_runs.json", workflow)
            self.assertIn("site/data/validation/shadow_review_queue.json", workflow)
            self.assertIn("for attempt in 1 2 3 4", workflow)
            self.assertIn("git worktree add --detach", workflow)
            self.assertIn("candidate_sha", workflow)
            self.assertIn("persisted_sha", workflow)
            self.assertIn("cambió concurrentemente", workflow)
            self.assertNotIn("git pull --rebase", workflow)
            self.assertNotIn("git push --force", workflow)
        self.assertIn(
            "from scripts.archive_shadow_validation import validate_shadow_integrity",
            review,
        )

    def test_readiness_panel_shows_live_freshness_and_fail_closed_fields(self):
        script = (ROOT / "site/v08-readiness.js").read_text(encoding="utf-8")
        self.assertIn("data/validation/shadow_review_queue.json", script)
        self.assertIn("STALE/REFRESH_REQUIRED", script)
        self.assertIn("next_transition_at_utc", script)
        self.assertIn("computed_captured_within_window", script)
        self.assertIn("computed_covers_target_day", script)
        self.assertIn("paridad scorecard", script)
        self.assertIn("Puertas fallidas exactas", script)
        self.assertIn("counts_toward_closeout", script)
        self.assertIn("solo anotación; no gate", script)
        self.assertIn("UNKNOWN/UNCERTAIN", script)
        self.assertNotIn("stored_label='EVENT'", script)
        self.assertNotIn("stored_label='NONE'", script)


if __name__ == "__main__":
    unittest.main()
