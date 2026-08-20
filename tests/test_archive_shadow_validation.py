import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "archive_shadow_validation", ROOT / "scripts" / "archive_shadow_validation.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ImmutableDailyShadowArchiveTests(unittest.TestCase):
    def test_cendehua_raw_false_is_not_converted_to_none(self):
        captured_at = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
        probe = {
            "generated_at": "2026-08-18T00:55:00+00:00",
            "status": "AVAILABLE_TEST_ONLY",
            "huaycoloro_ground_signal": {
                "observations": [{
                    "station_id": "HUA-01",
                    "last_alert_update": "2026-08-18T00:30:00+00:00",
                    "last_image_update": "2026-08-18T00:31:00+00:00",
                    "provider_activity_flag_raw": False,
                }],
            },
        }

        signal = MODULE.compact_cendehua_signal(probe, captured_at)

        self.assertEqual(signal["station_count"], 1)
        self.assertEqual(signal["recent_station_count_at_shadow_capture"], 1)
        self.assertIs(signal["observations"][0]["provider_activity_flag_raw"], False)
        self.assertIsNone(signal["observations"][0]["irfen_outcome_label"])
        self.assertIsNone(signal["automatic_outcome_label"])
        self.assertIs(signal["can_support_none_classification_by_itself"], False)
        self.assertIs(signal["human_review_required"], True)

    def test_cendehua_recency_is_recalculated_at_shadow_capture(self):
        captured_at = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
        probe = {
            "huaycoloro_ground_signal": {
                "observations": [
                    {
                        "station_id": "RECENT",
                        "last_alert_update": "2026-08-17T23:31:00+00:00",
                    },
                    {
                        "station_id": "STALE",
                        "last_alert_update": "2026-08-17T23:29:59+00:00",
                    },
                ],
            },
        }

        signal = MODULE.compact_cendehua_signal(probe, captured_at)

        self.assertIs(signal["observations"][0]["recent_at_shadow_capture"], True)
        self.assertIs(signal["observations"][1]["recent_at_shadow_capture"], False)
        self.assertEqual(signal["recent_station_count_at_shadow_capture"], 1)

    def test_missing_cendehua_probe_stays_uncertain(self):
        signal = MODULE.compact_cendehua_signal(
            {}, datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(signal["station_count"], 0)
        self.assertEqual(signal["recent_station_count_at_shadow_capture"], 0)
        self.assertIsNone(signal["automatic_outcome_label"])
        self.assertIs(signal["can_support_none_classification_by_itself"], False)
        self.assertIs(signal["human_review_required"], True)
        self.assertIn("UNCERTAIN", signal["missing_or_stale_data_rule"])

    def test_pre_outcome_window_accepts_early_capture_and_rejects_late_run(self):
        self.assertTrue(MODULE.capture_is_within_pre_outcome_window(
            datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
            "2026-08-18",
        ))
        self.assertFalse(MODULE.capture_is_within_pre_outcome_window(
            datetime(2026, 8, 17, 11, 59, 59, tzinfo=timezone.utc),
            "2026-08-18",
        ))
        self.assertTrue(MODULE.capture_is_within_pre_outcome_window(
            datetime(2026, 8, 18, 0, 10, tzinfo=timezone.utc),
            "2026-08-18",
        ))
        self.assertTrue(MODULE.capture_is_within_pre_outcome_window(
            datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc),
            "2026-08-18",
        ))
        self.assertFalse(MODULE.capture_is_within_pre_outcome_window(
            datetime(2026, 8, 18, 2, 0, 1, tzinfo=timezone.utc),
            "2026-08-18",
        ))

    def test_capture_resolves_today_or_tomorrow_without_backdating(self):
        self.assertEqual(
            MODULE.resolve_snapshot_date(datetime(2026, 8, 18, 1, 30, tzinfo=timezone.utc)),
            "2026-08-18",
        )
        self.assertIsNone(
            MODULE.resolve_snapshot_date(datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc))
        )
        self.assertEqual(
            MODULE.resolve_snapshot_date(datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)),
            "2026-08-19",
        )

    def test_forecast_must_cover_complete_target_day(self):
        captured_at = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
        required = MODULE.required_forecast_hours_to_target_day_end(
            captured_at, "2026-08-19"
        )
        self.assertEqual(required, 36.0)
        complete = [
            {"zone_id": zone_id, "forecast_mm": {"available_future_hours": 36}}
            for zone_id in ("san_ildefonso", "chosica", "catacaos")
        ]
        self.assertTrue(MODULE.zones_cover_target_day(complete, required))
        complete[0]["forecast_mm"]["available_future_hours"] = 35.5
        self.assertFalse(MODULE.zones_cover_target_day(complete, required))

    def test_first_snapshot_is_preserved_on_same_day_rerun(self):
        original = {
            "snapshot_date_utc": "2026-08-17",
            "archived_at": "2026-08-17T17:30:00+00:00",
            "zones": [{"zone_id": "catacaos", "observed_mm": {"rain24": 4.0}}],
            "outcome_verification": {"status": "PENDING_REAL_WORLD_OUTCOME_REVIEW"},
            "production_use": False,
        }
        archive = {
            "status": "SHADOW_VALIDATION_ARCHIVE",
            "production_use": False,
            "production_ready": False,
            "record_count": 1,
            "updated_at": "2026-08-17T17:30:00+00:00",
            "records": [original],
        }
        rerun = {
            **original,
            "archived_at": "2026-08-17T22:00:00+00:00",
            "zones": [{"zone_id": "catacaos", "observed_mm": {"rain24": 40.0}}],
        }

        created = MODULE.append_immutable_daily_snapshot(
            archive, rerun, datetime(2026, 8, 17, 22, tzinfo=timezone.utc)
        )

        self.assertFalse(created)
        self.assertEqual(archive["records"], [original])
        self.assertEqual(archive["updated_at"], "2026-08-17T17:30:00+00:00")
        self.assertEqual(archive["record_count"], 1)

    def test_new_day_is_appended_and_archive_is_bounded(self):
        records = [
            {
                "snapshot_date_utc": (
                    datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
                ).date().isoformat(),
                "production_use": False,
            }
            for index in range(400)
        ]
        archive = {"status": "SHADOW_VALIDATION_ARCHIVE", "records": records}
        entry = {"snapshot_date_utc": "2099-12-31", "production_use": False}
        now = datetime(2099, 12, 31, 17, 30, tzinfo=timezone.utc)

        created = MODULE.append_immutable_daily_snapshot(archive, entry, now)

        self.assertTrue(created)
        self.assertEqual(len(archive["records"]), 400)
        self.assertEqual(archive["record_count"], 400)
        self.assertIn(entry, archive["records"])
        self.assertEqual(archive["updated_at"], now.isoformat())
        self.assertIs(archive["production_use"], False)
        self.assertIs(archive["production_ready"], False)

    def test_effective_day_snapshot_is_sealed_and_chained(self):
        archive = {"status": "SHADOW_VALIDATION_ARCHIVE", "records": []}
        first = {
            "snapshot_date_utc": "2026-08-21",
            "archived_at": "2026-08-21T00:10:00+00:00",
            "zones": [{"zone_id": "catacaos", "observed_mm": {"rain24": 4.0}}],
            "outcome_verification": {"status": "PENDING_REAL_WORLD_OUTCOME_REVIEW"},
            "production_use": False,
        }
        second = {
            **first,
            "snapshot_date_utc": "2026-08-22",
            "archived_at": "2026-08-22T00:10:00+00:00",
        }

        MODULE.append_immutable_daily_snapshot(
            archive, first, datetime(2026, 8, 21, 0, 10, tzinfo=timezone.utc)
        )
        MODULE.append_immutable_daily_snapshot(
            archive, second, datetime(2026, 8, 22, 0, 10, tzinfo=timezone.utc)
        )

        validation = MODULE.validate_shadow_integrity(archive["records"])
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["sealed_record_count"], 2)
        self.assertIsNone(first["integrity"]["previous_chain_sha256"])
        self.assertEqual(
            second["integrity"]["previous_chain_sha256"],
            first["integrity"]["chain_sha256"],
        )

    def test_review_annotation_is_mutable_but_snapshot_payload_is_not(self):
        record = {
            "snapshot_date_utc": "2026-08-21",
            "archived_at": "2026-08-21T00:10:00+00:00",
            "zones": [{"zone_id": "catacaos", "observed_mm": {"rain24": 4.0}}],
            "outcome_verification": {"status": "PENDING_REAL_WORLD_OUTCOME_REVIEW"},
            "production_use": False,
        }
        MODULE.seal_snapshot_integrity(record, None)

        record["outcome_verification"] = {
            "status": "REVIEWED_REAL_WORLD_OUTCOME",
            "label": "UNCERTAIN",
        }
        self.assertTrue(MODULE.validate_shadow_integrity([record])["valid"])

        record["zones"][0]["observed_mm"]["rain24"] = 40.0
        validation = MODULE.validate_shadow_integrity([record])
        self.assertFalse(validation["valid"])
        self.assertIn("2026-08-21:payload_hash_mismatch", validation["errors"])


if __name__ == "__main__":
    unittest.main()
