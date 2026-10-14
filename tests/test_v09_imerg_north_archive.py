"""IRFEN v0.9 IMERG Early north archive: bounded retries of the Earthdata contact, explicit missing half-hours,
catch-up budget. Offline: the Earthdata client is replaced by SYNTHETIC fakes (no network, not real data)."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_imerg_north_archive", ROOT / "scripts/v09_imerg_north_archive.py")
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


class FakeProbe:
    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    def earthdata_preflight(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("HTTPSConnectionPool(host='urs.earthdata.nasa.gov', port=443): Max retries exceeded")
        return 401


class FakeEarthaccess:
    def login(self, strategy):
        return True

    def search_data(self, **kw):
        return ["granule"]


class ContactRetries(unittest.TestCase):
    def test_transient_failure_is_retried_and_traced(self):
        waits = []
        found, attempts = A.contact_with_retries(FakeProbe(failures=2), FakeEarthaccess(), NOW, sleep=waits.append)
        self.assertEqual(found, ["granule"])
        self.assertEqual([a["ok"] for a in attempts], [False, False, True])
        self.assertIn("urs.earthdata.nasa.gov", attempts[0]["error"])
        self.assertEqual(waits, list(A.CONTACT_BACKOFF_S))

    def test_persistent_failure_raises_with_every_attempt(self):
        waits = []
        with self.assertRaises(RuntimeError) as ctx:
            A.contact_with_retries(FakeProbe(failures=99), FakeEarthaccess(), NOW, sleep=waits.append)
        self.assertEqual(len(ctx.exception.attempts), A.CONTACT_ATTEMPTS)
        self.assertFalse(any(a["ok"] for a in ctx.exception.attempts))
        self.assertEqual(len(waits), A.CONTACT_ATTEMPTS - 1)  # no wait after the last attempt


class MissingHalfHours(unittest.TestCase):
    def test_reasons_and_24h_span(self):
        newest = datetime(2026, 10, 13, 6, 30, tzinfo=timezone.utc)
        slots = [newest - timedelta(minutes=30 * k) for k in range(48)]
        not_published = slots[10]
        not_archived = slots[20]
        catalog = [t for t in slots if t != not_published]
        archived = {t for t in slots if t not in (not_published, not_archived)}
        gaps = A.missing_half_hours(catalog, archived, NOW)
        self.assertEqual({g["time_utc"]: g["reason"] for g in gaps},
                         {not_published.isoformat(): "NOT_IN_CATALOG", not_archived.isoformat(): "IN_CATALOG_NOT_ARCHIVED"})
        self.assertEqual(A.missing_half_hours([], set(), NOW), [])

    def test_budget_covers_the_whole_window(self):
        # 16 per run left the oldest granules behind when runs were more than 8 h apart (12-10 09:00 and 09:30).
        self.assertGreaterEqual(A.MAX_DOWNLOADS_PER_RUN, A.WINDOW_HOURS * 2)


class EngineCoverage(unittest.TestCase):
    def test_zone_coverage_lists_missing_half_hours(self):
        spec = importlib.util.spec_from_file_location("v09_zone_rain_engine", ROOT / "scripts/v09_zone_rain_engine.py")
        E = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(E)
        last = datetime(2026, 10, 13, 1, 30, tzinfo=timezone.utc)
        gap = last - timedelta(hours=16)
        granules = [dict(time_utc=(last - timedelta(minutes=30 * k)).isoformat(), targets=dict(z=dict(accum_30min_mm=0.0, valid_cells=4)))
                    for k in range(48) if (last - timedelta(minutes=30 * k)) != gap]
        im = E.imerg_for_zone("z", None, dict(granules=granules), None)
        self.assertEqual(im["coverage_24h"]["available_half_hours"], 47)
        self.assertEqual(im["coverage_24h"]["missing_half_hours_utc"], [gap.isoformat()])
        self.assertEqual(im["windows"]["24h"]["status"], "NO_DISPONIBLE")  # a missing half-hour is never zero rain


if __name__ == "__main__":
    unittest.main()
