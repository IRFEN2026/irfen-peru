"""IRFEN v0.9 zone rain engine: windows, quality, review priority. Offline.

Synthetic series below are labelled SYNTHETIC and only exercise the rules; they are not evidence of any event.
"""
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_zone_rain_engine", ROOT / "scripts/v09_zone_rain_engine.py")
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)
T0 = datetime(2026, 10, 9, 20, 30, tzinfo=timezone.utc)
AT = T0 + timedelta(hours=1)  # evaluation instant: IMERG windows end at T0+30 min, GOES scan at T0+50 min


def synthetic_series(n, value=0.5, gaps=()):
    """SYNTHETIC half-hourly accumulations ending at T0 (not real data)."""
    out = {}
    for k in range(n):
        t = (T0 - timedelta(minutes=30 * k)).isoformat()
        out[t] = None if k in gaps else value
    return out


class Windows(unittest.TestCase):
    def test_complete_windows_sum_half_hours(self):
        w = E.windows(synthetic_series(48, 0.5))
        self.assertEqual(w["latest_granule_start_utc"], T0.isoformat())
        self.assertEqual(w["window_end_utc"], (T0 + timedelta(minutes=30)).isoformat())
        self.assertEqual({k: v["accum_mm"] for k, v in w["windows"].items()}, {"1h": 1.0, "3h": 3.0, "6h": 6.0, "24h": 24.0})

    def test_any_missing_half_hour_makes_the_window_unavailable(self):
        w = E.windows(synthetic_series(48, 0.5, gaps=(7,)))
        self.assertEqual(w["windows"]["1h"]["status"], "CALCULADO")
        self.assertEqual(w["windows"]["3h"]["status"], "CALCULADO")
        self.assertEqual(w["windows"]["6h"]["status"], "NO_DISPONIBLE")
        self.assertEqual(w["windows"]["6h"]["missing_half_hours"], 1)
        self.assertNotIn("accum_mm", w["windows"]["24h"])

    def test_short_archive_and_empty_archive(self):
        w = E.windows(synthetic_series(4, 1.0))
        self.assertEqual(w["windows"]["1h"]["accum_mm"], 2.0)
        self.assertEqual(w["windows"]["3h"]["missing_half_hours"], 2)
        empty = E.windows({})
        self.assertTrue(all(v["status"] == "NO_DISPONIBLE" for v in empty["windows"].values()))

    def test_invalid_cells_are_missing_not_zero(self):
        north = dict(granules=[dict(time_utc=T0.isoformat(), targets=dict(z=dict(accum_30min_mm=0.0, valid_cells=0)))])
        self.assertEqual(E.series_from_north(north, "z"), {T0.isoformat(): None})


class Goes(unittest.TestCase):
    PROBE = dict(source_available=True, latest_object=dict(scan_end="2026-10-10T01:39:52+00:00"), samples=[
        dict(target_id="a", weight=0.35, coverage_valid=True, good_quality_pixel_count=25, window_pixel_count=25,
             rain_rate_summary_mm_h=dict(min=0, mean=2.0, max=4.0)),
        dict(target_id="a", weight=0.65, coverage_valid=True, good_quality_pixel_count=0, window_pixel_count=25,
             rain_rate_summary_mm_h=dict(min=0, mean=9.0, max=9.0)),
        dict(target_id="b", coverage_valid=False, good_quality_pixel_count=0, window_pixel_count=25,
             rain_rate_summary_mm_h=dict(min=0, mean=0, max=0))])

    def test_only_quality_controlled_pixels(self):
        g = E.goes_for_zone("a", self.PROBE)
        self.assertEqual((g["status"], g["rate_mean_mm_h"], g["rate_max_mm_h"]), ("CALCULADO", 2.0, 4.0))
        self.assertIn("no validado", g["uncertainty_es"])
        self.assertEqual(E.goes_for_zone("b", self.PROBE)["status"], "NO_DISPONIBLE")
        self.assertEqual(E.goes_for_zone(None, self.PROBE)["status"], "NO_DISPONIBLE")
        self.assertEqual(E.goes_for_zone("a", dict(source_available=False))["status"], "NO_DISPONIBLE")


def zone_row(zone_id, avisos, imerg, goes, at=AT):
    pct = dict(status="NO_DISPONIBLE")
    return dict(zone_id=zone_id, imerg=imerg, goes19=goes, review_priority=E.review_priority(avisos, imerg, goes, pct, at))


class NorthArchives(unittest.TestCase):
    """SYNTHETIC v0.9 archive records (shape only), not real observations."""

    def test_polygon_goes_preferred_and_qc_respected(self):
        north = dict(scans=[dict(scan_end="2026-10-12T13:40:00+00:00", targets=dict(
            z=dict(pixels=40, valid_pixels=31, valid_fraction=0.775, rate_mean_mm_h=1.2, rate_max_mm_h=4.0),
            q=dict(pixels=12, valid_pixels=0, valid_fraction=0.0, rate_mean_mm_h=None, rate_max_mm_h=None)))])
        g = E.goes_for_zone("v08target", Goes.PROBE, "z", north)
        self.assertEqual((g["status"], g["source"], g["good_quality_pixels"]), ("CALCULADO", "GOES19_RRQPE_V09_POLYGON", 31))
        q = E.goes_for_zone(None, None, "q", north)
        self.assertEqual(q["status"], "NO_DISPONIBLE")
        self.assertIn("DQF=0", q["reason"])
        self.assertEqual(E.goes_for_zone("a", Goes.PROBE, "other", north)["source"], "GOES19_RRQPE_V08_PROBE:a")

    def test_geos_north_carries_its_resolution_note(self):
        north = dict(dataset_time_start="2026-10-12T00:30", zones=dict(z=dict(cells=1, resolution_note="Zona más pequeña que una celda de 0,25°",
                                                                               hourly=[dict(valid_time="2026-10-12T14:30:00Z", precip_mm=0.2)])))
        g = E.geos_for_zone(None, None, "z", north)
        self.assertEqual((g["status"], g["cells"]), ("CALCULADO", 1))
        self.assertIn("más pequeña", g["resolution_note"])
        self.assertEqual(E.geos_for_zone(None, None, "missing", north)["status"], "NO_DISPONIBLE")


class ReviewPriority(unittest.TestCase):
    VIG = dict(aviso_key="A1", status="VIGENTE", relation_method="BASIN_INTERSECTS_LISTED_PROVINCE", official_level="NARANJA",
               validity_start="2026-10-09T00:00:00-05:00", validity_end="2026-10-10T23:59:00-05:00")
    FUT = dict(aviso_key="A2", status="FUTURO", relation_method="DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN",
               validity_start="2026-10-11T00:00:00-05:00", validity_end="2026-10-11T23:59:00-05:00")
    NEG = dict(aviso_key="A3", status="VIGENTE", relation_method="BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES",
               validity_start="2026-10-09T00:00:00-05:00", validity_end="2026-10-10T23:59:00-05:00")
    FULL_ZERO = E.windows(synthetic_series(48, 0.0))
    FULL_RAIN = E.windows(synthetic_series(48, 0.4))
    NONE = E.windows({})
    GOES_ZERO = dict(status="CALCULADO", rate_max_mm_h=0.0, scan_end_utc=(T0 + timedelta(minutes=50)).isoformat())
    GOES_RAIN = dict(status="CALCULADO", rate_max_mm_h=3.0, scan_end_utc=(T0 + timedelta(minutes=50)).isoformat())
    GOES_NA = dict(status="NO_DISPONIBLE")

    def code(self, avisos, imerg, goes, at=AT):
        return E.review_priority(avisos, imerg, goes, dict(status="NO_DISPONIBLE"), at)["code"]

    def test_tiers(self):
        self.assertEqual(self.code([self.VIG], self.FULL_RAIN, self.GOES_ZERO), "R2_VIGILANCIA_ACTIVA")  # C not evaluable
        self.assertEqual(self.code([self.FUT], self.FULL_ZERO, self.GOES_ZERO), "R3_PREPARAR_VIGILANCIA")
        self.assertEqual(self.code([], self.FULL_RAIN, self.GOES_NA), "R4_LLUVIA_OBSERVADA_SIN_AVISO")
        self.assertEqual(self.code([], self.NONE, self.GOES_NA), "R5_DATOS_INSUFICIENTES")
        self.assertEqual(self.code([], self.FULL_ZERO, self.GOES_ZERO), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")
        self.assertEqual(self.code([self.NEG], self.FULL_ZERO, self.GOES_ZERO), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")

    def test_situation_c_needs_an_interpretable_percentile(self):
        p = E.review_priority([self.VIG], self.FULL_RAIN, self.GOES_ZERO, dict(status="CALCULADO", percentile_24h=97), AT)
        self.assertEqual(p["code"], "R1_REVISION_PRIORITARIA")
        p = E.review_priority([self.VIG], self.FULL_RAIN, self.GOES_ZERO, dict(status="NO_DISPONIBLE"), AT)
        self.assertTrue(any("no evaluable" in r for r in p["reasons_es"]))
        self.assertTrue(any("percentil" in m for m in p["missing_es"]))

    def test_missing_data_never_sorts_as_low(self):
        rows = [zone_row("zero", [self.VIG], self.FULL_ZERO, self.GOES_ZERO),
                zone_row("missing", [self.VIG], self.NONE, self.GOES_NA),
                zone_row("rain", [self.VIG], self.FULL_RAIN, self.GOES_ZERO),
                zone_row("no_aviso_missing", [], self.NONE, self.GOES_NA),
                zone_row("no_aviso_zero", [], self.FULL_ZERO, self.GOES_ZERO)]
        order = [r["zone_id"] for r in sorted(rows, key=E.sort_key)]
        self.assertEqual(order, ["missing", "rain", "zero", "no_aviso_missing", "no_aviso_zero"])

    def test_stale_observations_count_as_missing_never_as_zero(self):
        """SYNTHETIC: the same evidence evaluated 13 h later (IMERG > 12 h, GOES > 90 min)."""
        late = AT + timedelta(hours=13)
        self.assertEqual(self.code([], self.FULL_ZERO, self.GOES_ZERO), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")
        self.assertEqual(self.code([], self.FULL_ZERO, self.GOES_ZERO, late), "R5_DATOS_INSUFICIENTES")
        self.assertEqual(self.code([], self.FULL_RAIN, self.GOES_NA), "R4_LLUVIA_OBSERVADA_SIN_AVISO")
        self.assertEqual(self.code([], self.FULL_RAIN, self.GOES_NA, late), "R5_DATOS_INSUFICIENTES")
        p = E.review_priority([], self.FULL_ZERO, self.GOES_ZERO, dict(status="NO_DISPONIBLE"), late)
        self.assertFalse(p["imerg_usable"] or p["goes_usable"])
        self.assertTrue(any("IMERG Early desactualizado" in m for m in p["missing_es"]))
        self.assertTrue(any("GOES-19 desactualizado" in m for m in p["missing_es"]))

    def test_goes_alone_goes_stale_after_ninety_minutes(self):
        just = T0 + timedelta(minutes=50 + 90)
        self.assertEqual(self.code([], self.FULL_ZERO, self.GOES_RAIN, just), "R4_LLUVIA_OBSERVADA_SIN_AVISO")
        self.assertEqual(self.code([], self.FULL_ZERO, self.GOES_RAIN, just + timedelta(seconds=1)), "R5_DATOS_INSUFICIENTES")

    def test_aviso_status_follows_the_evaluation_instant(self):
        before = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        during = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
        after = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
        fresh = lambda at: dict(self.GOES_ZERO, scan_end_utc=at.isoformat())
        imerg_at = lambda at: dict(self.FULL_ZERO, window_end_utc=(at - timedelta(hours=5)).isoformat())
        self.assertEqual(self.code([self.FUT], imerg_at(before), fresh(before), before), "R3_PREPARAR_VIGILANCIA")
        self.assertEqual(self.code([self.FUT], imerg_at(during), fresh(during), during), "R2_VIGILANCIA_ACTIVA")
        self.assertEqual(self.code([self.FUT], imerg_at(after), fresh(after), after), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")
        self.assertEqual(self.code([dict(self.FUT, status="CANCELADO")], imerg_at(during), fresh(during), during), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")
        self.assertEqual(self.code([dict(self.FUT, validity_end=None)], imerg_at(after), fresh(after), after), "R3_PREPARAR_VIGILANCIA")

    def test_next_change_is_the_nearest_edge(self):
        p = E.review_priority([self.VIG], self.FULL_ZERO, self.GOES_ZERO, dict(status="NO_DISPONIBLE"), AT)
        self.assertEqual(p["next_change_utc"], (T0 + timedelta(minutes=50 + 90, seconds=1)).isoformat())  # GOES goes stale first
        late = datetime(2026, 10, 11, 0, tzinfo=timezone.utc)
        p = E.review_priority([self.VIG], self.FULL_ZERO, self.GOES_NA, dict(status="NO_DISPONIBLE"), late)
        self.assertEqual(p["next_change_utc"], "2026-10-11T04:59:01+00:00")  # aviso end, 23:59 Lima

    def test_stale_observation_sorts_as_missing(self):
        fresh = zone_row("fresh_rain", [self.VIG], self.FULL_RAIN, self.GOES_ZERO)
        old = zone_row("old_rain", [self.VIG], self.FULL_RAIN, self.GOES_ZERO, AT + timedelta(hours=13))
        self.assertEqual([r["zone_id"] for r in sorted([fresh, old], key=E.sort_key)], ["old_rain", "fresh_rain"])

    def test_vocabulary_is_separate_from_senamhi_levels(self):
        codes = " ".join(p["code"] + p["label_es"] for p in E.REVIEW_PRIORITIES).upper()
        for level in ("ROJO", "NARANJA", "AMARILLO", "VERDE"):
            self.assertNotIn(level, codes)
        self.assertNotIn("PROBABILIDAD", codes)


class GeosWindows(unittest.TestCase):
    """SYNTHETIC hourly forecast (shape only), not a real GEOS-CF run."""
    START = "2026-10-12T09:30:00.000000000"

    def geos(self, hours, start=None, gaps=()):
        h0 = datetime(2026, 10, 12, 14, 30, tzinfo=timezone.utc)
        return dict(status="CALCULADO", dataset_time_start=start or self.START,
                    hourly=[dict(valid_time_utc=(h0 + timedelta(hours=k)).isoformat().replace("+00:00", "Z"), precip_mm=0.25)
                            for k in range(hours) if k not in gaps])

    def test_sums_need_consecutive_hours_from_the_evaluation_instant(self):
        at = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)
        w = E.geos_windows_at(self.geos(48), at)
        self.assertEqual((w["status"], w["windows"]["6h"]["accum_mm"], w["windows"]["24h"]["accum_mm"]), ("CALCULADO", 1.5, 6.0))
        w = E.geos_windows_at(self.geos(48, gaps=(10,)), at)
        self.assertEqual((w["windows"]["6h"]["status"], w["windows"]["24h"]["status"]), ("CALCULADO", "NO_DISPONIBLE"))
        self.assertNotIn("accum_mm", w["windows"]["24h"])
        w = E.geos_windows_at(self.geos(20), at)
        self.assertEqual(w["windows"]["24h"]["status"], "NO_DISPONIBLE")
        early = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)  # first forecast hour more than 1 h away: no sum
        self.assertEqual(E.geos_windows_at(self.geos(48), early)["windows"]["6h"]["status"], "NO_DISPONIBLE")

    def test_old_cycle_gives_no_sums(self):
        at = datetime(2026, 10, 14, 15, 31, tzinfo=timezone.utc)  # 54 h + 1 min after the cycle start
        w = E.geos_windows_at(self.geos(120), at)
        self.assertEqual(w["status"], "DESACTUALIZADO")
        self.assertNotIn("windows", w)
        self.assertEqual(E.geos_windows_at(dict(status="NO_DISPONIBLE", reason="x"), at)["status"], "NO_DISPONIBLE")
        self.assertEqual(E.geos_windows_at(dict(self.geos(48), dataset_time_start=None), at)["status"], "NO_DISPONIBLE")


class CommittedState(unittest.TestCase):
    def test_committed_state_guards_and_rules(self):
        out = json.loads(E.OUT.read_text(encoding="utf-8"))
        for key, value in E.GUARDS.items():
            self.assertEqual(out[key], value)
        self.assertFalse(out["map_publishable"])
        for z in out["zones"]:
            for w in z["imerg"]["windows"].values():
                self.assertIn(w["status"], ("CALCULADO", "NO_DISPONIBLE"))
                if w["status"] == "NO_DISPONIBLE":
                    self.assertNotIn("accum_mm", w)
            self.assertEqual(z["river_level"]["status"], "NO_DISPONIBLE")
        codes = [z["review_priority"]["code"] for z in out["zones"]]
        self.assertEqual(codes, sorted(codes, key=lambda c: E.RANK[c]))
        self.assertEqual(out["freshness"], E.FRESHNESS)
        self.assertTrue(out["evaluated_at_utc"])

    def test_committed_state_replays_from_its_inputs(self):
        out = json.loads(E.OUT.read_text(encoding="utf-8"))
        current = {k: E.sha(p) for k, p in (("zones", E.ZONES), ("links", E.LINKS), ("imerg_north", E.IMERG_NORTH),
                                            ("imerg_v08", E.IMERG_V08), ("goes19", E.GOES), ("geos_cf", E.GEOS),
                                            ("goes19_north", E.GOES_NORTH), ("geos_cf_north", E.GEOS_NORTH))}
        if out["inputs"] != current:
            self.skipTest("an input changed after the committed state; the v0.9 workflows regenerate and check it")
        self.assertEqual(E.main(["--check"]), 0)
