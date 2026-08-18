import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "archive_shadow_validation", ROOT / "scripts" / "archive_shadow_validation.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ImmutableDailyShadowArchiveTests(unittest.TestCase):
    def test_pre_outcome_window_accepts_early_capture_and_rejects_late_run(self):
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
            {"snapshot_date_utc": f"2025-01-{day:02d}", "production_use": False}
            for day in range(1, 32)
        ]
        records.extend(
            {"snapshot_date_utc": f"2025-{month:02d}-01", "production_use": False}
            for month in range(2, 13)
        )
        while len(records) < 400:
            index = len(records)
            records.append({"snapshot_date_utc": f"2026-{index // 28 + 1:02d}-{index % 28 + 1:02d}"})
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


if __name__ == "__main__":
    unittest.main()
