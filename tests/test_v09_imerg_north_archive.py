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
                    mock.patch.object(A, "load_catchment_targets", lambda: []), \
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

class CatchmentTargets(unittest.TestCase):
    """v0.9.1 research: rain over the contributing areas of the river checkpoints, from the same granules."""

    def test_weighted_mean_is_unknown_without_valid_cells_never_zero(self):
        import numpy as np
        w = dict(rows=np.array([0, 0, 1]), cols=np.array([0, 1, 1]), areas=np.array([0.01, 0.005, 0.0025]), geom_area=0.0175)
        v = np.array([[2.0, np.nan], [9.0, 4.0]])
        mean, cov = A.weighted_mean(w, v)
        self.assertAlmostEqual(mean, (2.0 * 0.01 + 4.0 * 0.0025) / 0.0125)
        self.assertAlmostEqual(cov, round(100 * 0.0125 / 0.0175, 1))
        self.assertEqual(A.weighted_mean(w, np.full((2, 2), np.nan)), (None, 0.0))
        self.assertEqual(A.weighted_mean(dict(rows=np.array([], int), cols=np.array([], int), areas=np.array([]), geom_area=1.0), v), (None, 0.0))

    @unittest.skipUnless(importlib.util.find_spec("shapely"), "shapely (requirements.txt) not installed")
    def test_weights_match_polygon_mean_and_config_is_hash_locked(self):
        import json
        import numpy as np
        from shapely.geometry import Polygon, box
        lat = np.arange(-5.95, -4.95, 0.1)
        lon = np.arange(-80.95, -79.95, 0.1)
        geom = Polygon([(-80.73, -5.62), (-80.21, -5.71), (-80.12, -5.18), (-80.66, -5.08)])
        rng = np.random.default_rng(7)
        vals = rng.gamma(0.6, 2.0, (lat.size, lon.size))
        vals[3, 4] = np.nan
        # brute force (the semantics of probe_imerg_early_live.polygon_mean): area of every cell intersection
        sw = sv = 0.0
        for r in range(lat.size):
            for c in range(lon.size):
                a = geom.intersection(box(lon[c] - 0.05, lat[r] - 0.05, lon[c] + 0.05, lat[r] + 0.05)).area
                if a > 0 and np.isfinite(vals[r, c]):
                    sw, sv = sw + a, sv + a * vals[r, c]
        mean, cov = A.weighted_mean(A.cell_weights(geom, lat, lon), vals)
        self.assertAlmostEqual(mean, sv / sw, places=9)
        self.assertLess(cov, 100.0)
        cfg = json.loads(A.CATCHMENT_TARGETS.read_text(encoding="utf-8"))
        targets = A.load_catchment_targets()
        self.assertEqual([t["checkpoint_id"] for t in targets], cfg["targets"])
        self.assertGreater(len(targets), 100)
        self.assertTrue(all(t["id"].startswith("cp:") and t["geometry"].is_valid and t["geometry"].area > 0 for t in targets))
        from unittest import mock
        with mock.patch.object(A, "CATCHMENT_TARGETS", A.CATCHMENT_TARGETS.with_name("missing.json")):
            self.assertEqual(A.load_catchment_targets(), [])
        bad = dict(cfg, geometry_sha256="0" * 64)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cfg.json"
            f.write_text(json.dumps(bad), encoding="utf-8")
            with mock.patch.object(A, "CATCHMENT_TARGETS", f):
                self.assertEqual(A.load_catchment_targets(), [])  # a different geometry is never sampled silently

    def test_config_is_research_only(self):
        import json
        cfg = json.loads(A.CATCHMENT_TARGETS.read_text(encoding="utf-8"))
        for k, v in dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, public_alerting=False,
                         notifications_enabled=False, activation_gate="BLOCKED", map_publishable=False).items():
            self.assertEqual(cfg[k], v)
        self.assertEqual(len(cfg["targets"]), len(set(cfg["targets"])))

    def test_main_samples_the_same_granules_into_a_separate_archive(self):
        import json
        import sys
        import tempfile
        import types
        import numpy as np
        from unittest import mock

        now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
        catalog = half_hours(datetime(2026, 11, 3, 5, 30, tzinfo=timezone.utc), 4)
        grid = np.array([[1.0, np.nan], [3.0, 5.0]])
        downloaded = []
        fake_ea = types.SimpleNamespace(login=lambda strategy: True, search_data=lambda **kw: [name(t) for t in catalog],
                                        download=lambda names, local_path, threads, show_progress: (downloaded.extend(names) or names))
        fake_probe = types.SimpleNamespace(
            earthdata_preflight=lambda: 401,
            index_granules=lambda found: sorted((datetime.strptime(n.split(".")[4][:16], "%Y%m%d-S%H%M%S").replace(tzinfo=timezone.utc), n, n)
                                                for n in found),
            read_grid=lambda path: (np.array([-5.05, -4.95]), np.array([-80.05, -79.95]), grid, "mm/hr"),
            polygon_mean=lambda geom, lat, lon, values: (0.4, dict(valid_cells=3, cells_intersected=3, covered_geometry_pct=100.0)))
        ct = [dict(id="cp:A", checkpoint_id="A", area_km2=10.0, geometry="gA", geometry_sha256="h"),
              dict(id="cp:B", checkpoint_id="B", area_km2=5.0, geometry="gB", geometry_sha256="h")]
        weights = {"gA": dict(rows=np.array([0, 1]), cols=np.array([0, 1]), areas=np.array([1.0, 3.0]), geom_area=4.0),
                   "gB": dict(rows=np.array([0]), cols=np.array([1]), areas=np.array([1.0]), geom_area=1.0)}  # only the NaN cell
        north = A.empty_archive()
        north["granules"] = [dict(granule=name(t), time_utc=t.isoformat(), retrieved_at_utc=now.isoformat(), units="mm/hr",
                                  targets=dict(z=dict(rate_mm_hr=0.1))) for t in catalog]  # north complete, catchments missing
        with tempfile.TemporaryDirectory() as d:
            out, cout = Path(d) / "north.json", Path(d) / "catch.json"
            out.write_text(json.dumps(north), encoding="utf-8")
            clock = mock.Mock(wraps=datetime)
            clock.now = lambda tz=None: now
            with mock.patch.dict(sys.modules, {"earthaccess": fake_ea, "probe_imerg_early_live": fake_probe}), \
                    mock.patch.object(A, "OUT", out), mock.patch.object(A, "CATCHMENT_OUT", cout), mock.patch.object(A, "datetime", clock), \
                    mock.patch.object(A, "load_targets", lambda: [dict(id="z", name="Z", kind="BASIN_POLYGON", geometry=None, geometry_sha256="x")]), \
                    mock.patch.object(A, "load_catchment_targets", lambda: ct), \
                    mock.patch.object(A, "cell_weights", lambda geom, lat, lon: weights[geom]), \
                    mock.patch.dict("os.environ", {"EARTHDATA_TOKEN": "fake-token-for-offline-test"}):
                self.assertEqual(A.main(), 0)
            got = json.loads(cout.read_text(encoding="utf-8"))
        self.assertEqual(sorted(downloaded), sorted(name(t) for t in catalog))  # backfilled from the same granules
        self.assertEqual([t["id"] for t in got["targets"]], ["cp:A", "cp:B"])
        self.assertEqual(len(got["granules"]), len(catalog))
        g = got["granules"][-1]
        self.assertEqual(g["rate_mm_hr"], [round((1.0 * 1 + 5.0 * 3) / 4, 4), None])  # B: no valid cell -> unknown, not 0
        self.assertEqual(g["covered_pct"], [100.0, 0.0])
        for k, v in A.GUARDS.items():
            self.assertEqual(got[k], v)
        self.assertFalse(got["map_publishable"] or got["public_alerting"] or got["notifications_enabled"])


if __name__ == "__main__":
    unittest.main()


class FakeDownloader:
    """SYNTHETIC: bulk download raises (as earthaccess DownloadFailure did on 02-11-2026); `bad` granules fail alone."""
    def __init__(self, bad):
        self.bad, self.calls = set(bad), []

    def download(self, granules, local_path, threads, show_progress):
        self.calls.append(list(granules))
        if any(g in self.bad for g in granules):
            raise RuntimeError("DownloadFailure: Download failed ... Status code: 400")
        return [f"{local_path}/{g}.HDF5" for g in granules]


class DownloadFailures(unittest.TestCase):
    ROWS = [(NOW - timedelta(minutes=30 * i), f"G{i}", f"G{i}") for i in range(3)]

    def test_one_bad_granule_does_not_lose_the_others(self):
        paths, failures = A.download_granules(FakeDownloader(bad={"G1"}), self.ROWS, "/tmp/x")
        self.assertEqual([p.rsplit("/", 1)[1] for p in paths], ["G0.HDF5", "G2.HDF5"])
        self.assertEqual([f["granule"] for f in failures], ["G1"])
        self.assertIn("400", failures[0]["error"])

    def test_all_bad_is_reported_not_raised(self):
        paths, failures = A.download_granules(FakeDownloader(bad={"G0", "G1", "G2"}), self.ROWS, "/tmp/x")
        self.assertEqual((paths, len(failures)), ([], 3))

    def test_nothing_selected_downloads_nothing(self):
        d = FakeDownloader(bad=set())
        self.assertEqual(A.download_granules(d, [], "/tmp/x"), ([], []))
        self.assertEqual(d.calls, [])
