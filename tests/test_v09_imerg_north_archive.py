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
        # an empty catalog is not "no gaps": the last 24 h that should already be published are all missing
        empty = A.missing_half_hours([], set(), NOW)
        self.assertEqual(len(empty), 48)
        self.assertEqual({g["reason"] for g in empty}, {"NOT_IN_CATALOG_PAST_NORMAL_LATENCY"})

    def test_budget_covers_the_whole_window(self):
        # 16 per run left the oldest granules behind when runs were more than 8 h apart (12-10 09:00 and 09:30).
        self.assertGreaterEqual(A.MAX_DOWNLOADS_PER_RUN, A.WINDOW_HOURS * 2)


def half_hours(last, n):
    return [last - timedelta(minutes=30 * k) for k in range(n)]


class SourceDelay(unittest.TestCase):
    """Replay of 28-30 Oct 2026 (GES DISC ingest migration): NASA's catalog published nothing after the granule of
    2026-10-28T15:30Z until 2026-10-29T20:23Z. Times only; no rain values are involved."""
    LAST_PUBLISHED = datetime(2026, 10, 28, 15, 30, tzinfo=timezone.utc)
    RUN = datetime(2026, 10, 29, 19, 55, tzinfo=timezone.utc)  # the last scheduled run before NASA resumed

    def test_stalled_catalog_is_a_delay_at_the_source_with_its_missing_half_hours(self):
        catalog = half_hours(self.LAST_PUBLISHED, 5)  # what the run of 29-10 19:55Z really saw (5 granules)
        archived = set(half_hours(self.LAST_PUBLISHED, 96))
        f = A.catalog_freshness(catalog, self.RUN)
        self.assertEqual(f["state"], "DELAYED_AT_SOURCE")
        self.assertEqual(f["newest_catalog_granule_start_utc"], self.LAST_PUBLISHED.isoformat())
        self.assertAlmostEqual(f["lag_hours"], 27.9, places=1)
        self.assertEqual(A.run_state(self.LAST_PUBLISHED.isoformat(), f), "CATALOG_DELAYED")  # was AVAILABLE
        gaps = A.missing_half_hours(catalog, archived, self.RUN)  # was [] (gaps measured up to the newest granule)
        self.assertEqual(len(gaps), 43)  # 24 h span 28-10 13:30 .. 29-10 13:00; the 5 archived half-hours are not gaps
        self.assertEqual({g["reason"] for g in gaps}, {"NOT_IN_CATALOG_PAST_NORMAL_LATENCY"})
        self.assertEqual(gaps[0]["time_utc"], "2026-10-28T16:00:00+00:00")
        self.assertEqual(gaps[-1]["time_utc"], "2026-10-29T13:00:00+00:00")  # ended >= 6 h before the run
        self.assertNotIn(self.LAST_PUBLISHED.isoformat(), {g["time_utc"] for g in gaps})

    def test_normal_latency_is_not_a_delay(self):
        newest = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)  # 4.5 h before NOW: normal IMERG Early latency
        catalog = half_hours(newest, 60)
        f = A.catalog_freshness(catalog, NOW)
        self.assertEqual(f["state"], "WITHIN_NORMAL_LATENCY")
        self.assertEqual(A.run_state(newest.isoformat(), f), "AVAILABLE")
        self.assertEqual(A.missing_half_hours(catalog, set(catalog), NOW), [])
        self.assertEqual(A.catalog_freshness([], NOW)["state"], "EMPTY_IN_SEARCH_SPAN")
        self.assertEqual(A.run_state(None, A.catalog_freshness([], NOW)), "CATALOG_DELAYED")

    def test_late_published_backlog_is_recovered_from_the_same_product(self):
        # NASA publishes the backlog after the migration (ends 2026-10-30T13:00Z). With the old 30 h search the
        # half-hours 28-10 16:00 .. 29-10 ~08:30 would have been outside every later search: lost for good.
        archived = {t.isoformat() for t in half_hours(self.LAST_PUBLISHED, 96)}
        first_missing = self.LAST_PUBLISHED + timedelta(minutes=30)
        backlog_end = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
        published = [first_missing + timedelta(minutes=30 * k) for k in range(int((backlog_end - first_missing) / timedelta(minutes=30)) + 1)]
        run = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
        self.assertLess(first_missing, run - timedelta(hours=A.WINDOW_HOURS))  # the defect of the 30 h search
        for _ in range(4):  # successive runs, a few hours apart
            visible = [(t, t.isoformat(), None) for t in published if t >= run - timedelta(hours=A.BACKFILL_HOURS)]
            chosen = A.select_downloads(visible, archived)
            self.assertLessEqual(len(chosen), A.MAX_DOWNLOADS_PER_RUN)
            if chosen:
                self.assertEqual(chosen[0][0], max(t for t, n, _ in visible if n not in archived))  # newest first
            archived |= {n for _, n, _ in chosen}
            run += timedelta(hours=5)
        self.assertTrue(all(t.isoformat() in archived for t in published))  # every late granule recovered
        self.assertLess(first_missing, run - timedelta(hours=A.WINDOW_HOURS))

    def test_search_span_and_retention(self):
        calls = []

        class Recording(FakeEarthaccess):
            def search_data(self, **kw):
                calls.append(kw)
                return []

        A.contact_with_retries(FakeProbe(failures=0), Recording(), NOW, sleep=lambda s: None)
        start, end = calls[0]["temporal"]
        self.assertEqual(datetime.fromisoformat(start), NOW - timedelta(hours=A.BACKFILL_HOURS))
        self.assertEqual(datetime.fromisoformat(end), NOW)
        self.assertGreaterEqual(calls[0]["count"], 2 * A.BACKFILL_HOURS)  # every half-hour of the span fits in one page
        self.assertLess(A.BACKFILL_HOURS, A.RETAIN_HOURS)  # nothing downloaded is pruned on arrival
        self.assertGreaterEqual(A.BACKFILL_HOURS, 72)  # covers a multi-day ingest interruption (28-30 Oct: 46 h)
        self.assertLessEqual(A.NORMAL_LATENCY_H, A.CATALOG_DELAY_H)


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

    def test_tumbes_piura_after_the_outage_keep_unknown_not_zero(self):
        """Zones of Tumbes (Bocapán basin, provinces) and Piura (provinces) after the 28-29 Oct gap, when NASA resumes
        with sparse granules (29-10 15:00 and 16:30, as published at 20:23Z/21:23Z): every window with a missing
        half-hour is NO_DISPONIBLE, coverage lists what is missing and nothing reads as 0 mm. SYNTHETIC values."""
        spec = importlib.util.spec_from_file_location("v09_zone_rain_engine", ROOT / "scripts/v09_zone_rain_engine.py")
        E = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(E)
        zones = ["tumbes_bocapan", "tumbes_province_context:ZARUMILLA", "piura_province_context:PIURA"]
        before = half_hours(SourceDelay.LAST_PUBLISHED, 96)
        resumed = [datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc), datetime(2026, 10, 29, 16, 30, tzinfo=timezone.utc)]
        granules = [dict(time_utc=t.isoformat(), targets={z: dict(accum_30min_mm=0.2, valid_cells=10) for z in zones})
                    for t in sorted(before + resumed)]
        evaluated = datetime(2026, 10, 29, 23, 30, tzinfo=timezone.utc)
        for z in zones:
            im = E.imerg_for_zone(z, None, dict(granules=granules), None)
            self.assertEqual(im["latest_granule_start_utc"], resumed[-1].isoformat(), z)
            self.assertEqual({w["status"] for w in im["windows"].values()}, {"NO_DISPONIBLE"}, z)
            self.assertFalse(any("accum_mm" in w for w in im["windows"].values()), z)
            self.assertEqual(im["coverage_24h"]["available_half_hours"], 2, z)
            self.assertEqual(len(im["coverage_24h"]["missing_half_hours_utc"]), 46, z)
            self.assertEqual(im["status"], "NO_DISPONIBLE", z)
            self.assertTrue(E.imerg_usable_at(im, evaluated), z)  # recent, but no complete window: nothing is computed
            # before NASA resumed: the last complete windows end 28-10 16:00 and are stale at the evaluation
            old = E.imerg_for_zone(z, None, dict(granules=[g for g in granules if g["time_utc"] <= SourceDelay.LAST_PUBLISHED.isoformat()]), None)
            self.assertEqual(old["window_end_utc"], "2026-10-28T16:00:00+00:00")
            self.assertFalse(E.imerg_usable_at(old, SourceDelay.RUN), z)


def name(t):
    return f"3B-HHR-E.MS.MRG.3IMERG.{t:%Y%m%d}-S{t:%H%M%S}-E{(t + timedelta(minutes=29, seconds=59)):%H%M%S}.0000.V07C.HDF5"


class MainRunOffline(unittest.TestCase):
    """main() end to end with SYNTHETIC fakes for earthaccess and the probe, writing to a temporary archive (never the
    real one): a stalled catalog is reported as CATALOG_DELAYED with its missing half-hours and nothing is added;
    when the source resumes, only published granules are added, newest first."""

    def run_main(self, archive, catalog_times, now, downloaded=None):
        import json
        import sys
        import tempfile
        import types
        from unittest import mock

        fake_ea = types.SimpleNamespace(login=lambda strategy: True, search_data=lambda **kw: [name(t) for t in catalog_times],
                                        download=lambda names, local_path, threads, show_progress: (downloaded.extend(names) or names))
        fake_probe = types.SimpleNamespace(
            earthdata_preflight=lambda: 401,
            index_granules=lambda found: sorted((datetime.strptime(n.split(".")[4][:16], "%Y%m%d-S%H%M%S").replace(tzinfo=timezone.utc), n, n)
                                                for n in found),
            read_grid=lambda path: (None, None, None, "mm/hr"),
            polygon_mean=lambda geom, lat, lon, values: (0.4, dict(valid_cells=3, cells_intersected=3, covered_geometry_pct=100.0)))
        downloaded = [] if downloaded is None else downloaded
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "imerg.json"
            out.write_text(json.dumps(archive), encoding="utf-8")
            clock = mock.Mock(wraps=datetime)
            clock.now = lambda tz=None: now
            with mock.patch.dict(sys.modules, {"earthaccess": fake_ea, "probe_imerg_early_live": fake_probe}), \
                    mock.patch.object(A, "OUT", out), mock.patch.object(A, "datetime", clock), \
                    mock.patch.object(A, "load_targets", lambda: [dict(id="tumbes_bocapan", name="Bocapán", kind="BASIN_POLYGON",
                                                                       geometry=None, geometry_sha256="x")]), \
                    mock.patch.dict("os.environ", {"EARTHDATA_TOKEN": "fake-token-for-offline-test"}):
                self.assertEqual(A.main(), 0)
            return json.loads(out.read_text(encoding="utf-8")), downloaded, name

    def archive_until(self, last, n):
        a = A.empty_archive()
        a["granules"] = [dict(granule=name(t), time_utc=t.isoformat(), retrieved_at_utc=last.isoformat(), units="mm/hr",
                              targets=dict(tumbes_bocapan=dict(rate_mm_hr=0.2, accum_30min_mm=0.1, valid_cells=3)))
                         for t in sorted(half_hours(last, n))]
        return a

    def test_stalled_catalog_run(self):
        last = SourceDelay.LAST_PUBLISHED
        archive = self.archive_until(last, 60)
        catalog = [t for t in half_hours(last, 60)]
        got, downloaded, _ = self.run_main(archive, catalog, SourceDelay.RUN)
        self.assertEqual(downloaded, [])  # nothing new is published: nothing is fetched, nothing is invented
        self.assertEqual(got["granules"], archive["granules"])
        self.assertEqual(got["status"]["state"], "CATALOG_DELAYED")
        self.assertEqual(got["status"]["catalog_freshness"]["state"], "DELAYED_AT_SOURCE")
        self.assertEqual(got["status"]["latest_granule_start_utc"], last.isoformat())
        self.assertTrue(got["status"]["missing_half_hours_24h"])
        self.assertTrue(all(g["time_utc"] <= last.isoformat() for g in got["granules"]))
        self.assertEqual(got["policy"]["backfill_hours"], A.BACKFILL_HOURS)
        for k, v in A.GUARDS.items():
            self.assertEqual(got[k], v)

    def test_resumed_source_adds_only_published_granules_newest_first(self):
        last = SourceDelay.LAST_PUBLISHED
        resumed = [datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc), datetime(2026, 10, 29, 16, 30, tzinfo=timezone.utc)]
        catalog = half_hours(last, 60) + resumed
        downloaded = []
        got, downloaded, _ = self.run_main(A.empty_archive(), catalog, datetime(2026, 10, 29, 23, 30, tzinfo=timezone.utc), downloaded)
        times = [g["time_utc"] for g in got["granules"]]
        self.assertIn(resumed[1].isoformat(), times)
        self.assertNotIn("2026-10-29T16:00:00+00:00", times)  # not published: absent, never filled
        self.assertEqual(downloaded[0], name(resumed[1]))  # newest first
        self.assertEqual(got["status"]["state"], "AVAILABLE")  # 6.5 h behind: within normal latency
        reasons = {g["time_utc"]: g["reason"] for g in got["status"]["missing_half_hours_24h"]}
        self.assertEqual(reasons["2026-10-29T16:00:00+00:00"], "NOT_IN_CATALOG")

if __name__ == "__main__":
    unittest.main()
