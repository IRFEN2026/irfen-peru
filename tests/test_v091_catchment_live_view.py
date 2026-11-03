"""Offline, fail-closed checks for experimental 30-minute catchment rain aggregation."""
import unittest
from datetime import datetime, timedelta, timezone
from scripts import v091_catchment_live_view as A

END = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def archive(n=60, coverage=100., value=2., missing=None):
    missing = missing or set()
    start = END - timedelta(minutes=30 * n)
    granules = []
    for i in range(n):
        t = start + timedelta(minutes=30 * i)
        if i in missing:
            continue
        granules.append(dict(time_utc=t.isoformat(), rate_mm_hr=[value],
                             covered_pct=[coverage]))
    return dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, public_alerting=False, activation_gate="BLOCKED",
                targets=[dict(checkpoint_id="PIU-R-PIURA-BAJO")], granules=granules)


class RainWindows(unittest.TestCase):
    def test_correct_consecutive_windows_and_no_72h(self):
        d = A.summarize(archive(), "PIU-R-PIURA-BAJO", END.isoformat())
        self.assertEqual(d["status"], "RECIENTE")
        for h in (1,3,6,24):
            self.assertEqual(d["windows"][f"{h}h"]["mm"], float(h))
        self.assertIsNone(d["windows"]["72h"]["mm"])
        self.assertEqual(d["observation_end_utc"], END.isoformat())

    def test_missing_half_hour_makes_window_null_not_zero(self):
        d = A.summarize(archive(missing={58}), "PIU-R-PIURA-BAJO", END.isoformat())
        self.assertIsNone(d["windows"]["1h"]["mm"])
        self.assertIsNone(d["windows"]["24h"]["mm"])

    def test_low_spatial_coverage_is_not_complete(self):
        d = A.summarize(archive(coverage=79.9), "PIU-R-PIURA-BAJO", END.isoformat())
        self.assertIsNone(d["windows"]["24h"]["mm"])
        self.assertEqual(d["status"], "DATOS_INCOMPLETOS")

    def test_zero_rain_is_valid_only_if_all_intervals_exist(self):
        d = A.summarize(archive(value=0.), "PIU-R-PIURA-BAJO", END.isoformat())
        self.assertEqual(d["windows"]["24h"]["mm"], 0.0)

    def test_stale_and_future_are_identified(self):
        self.assertEqual(A.summarize(archive(), "PIU-R-PIURA-BAJO",
                         (END + timedelta(hours=13)).isoformat())["status"], "CADUCADA")
        self.assertEqual(A.summarize(archive(), "PIU-R-PIURA-BAJO",
                         (END - timedelta(hours=1)).isoformat())["status"], "FECHA_INCONSISTENTE")

    def test_absent_point_and_untrusted_archive_do_not_generate_values(self):
        self.assertEqual(A.summarize(archive(), "NOT_A_CHECKPOINT", END.isoformat())["status"], "NO_DISPONIBLE")
        obj = archive()
        obj["public_alerting"] = True
        self.assertEqual(A.summarize(obj, "PIU-R-PIURA-BAJO", END.isoformat())["status"], "NO_DISPONIBLE")

    def test_duplicate_timestamp_is_not_used(self):
        obj = archive()
        obj["granules"].append(dict(obj["granules"][-1]))
        d = A.summarize(obj, "PIU-R-PIURA-BAJO", END.isoformat())
        self.assertIsNone(d["windows"]["1h"]["mm"])

    def test_schema_never_promotes_hazard(self):
        d = A.build(archive(), ["PIU-R-PIURA-BAJO"], END.isoformat())
        self.assertFalse(d["hazard_colors_enabled"])
        self.assertEqual(d["activation_gate"], "BLOCKED")
        self.assertFalse(d["notifications_enabled"])


if __name__ == "__main__":
    unittest.main()
