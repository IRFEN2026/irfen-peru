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


def zone_row(zone_id, avisos, imerg, goes):
    pct = dict(status="NO_DISPONIBLE")
    return dict(zone_id=zone_id, imerg=imerg, goes19=goes, review_priority=E.review_priority(avisos, imerg, goes, pct))


class ReviewPriority(unittest.TestCase):
    VIG = dict(aviso_key="A1", status="VIGENTE", relation_method="BASIN_INTERSECTS_LISTED_PROVINCE", official_level="NARANJA")
    FUT = dict(aviso_key="A2", status="FUTURO", relation_method="DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN")
    NEG = dict(aviso_key="A3", status="VIGENTE", relation_method="BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES")
    FULL_ZERO = E.windows(synthetic_series(48, 0.0))
    FULL_RAIN = E.windows(synthetic_series(48, 0.4))
    NONE = E.windows({})
    GOES_ZERO = dict(status="CALCULADO", rate_max_mm_h=0.0)
    GOES_NA = dict(status="NO_DISPONIBLE")

    def code(self, avisos, imerg, goes):
        return E.review_priority(avisos, imerg, goes, dict(status="NO_DISPONIBLE"))["code"]

    def test_tiers(self):
        self.assertEqual(self.code([self.VIG], self.FULL_RAIN, self.GOES_ZERO), "R2_VIGILANCIA_ACTIVA")  # C not evaluable
        self.assertEqual(self.code([self.FUT], self.FULL_ZERO, self.GOES_ZERO), "R3_PREPARAR_VIGILANCIA")
        self.assertEqual(self.code([], self.FULL_RAIN, self.GOES_NA), "R4_LLUVIA_OBSERVADA_SIN_AVISO")
        self.assertEqual(self.code([], self.NONE, self.GOES_NA), "R5_DATOS_INSUFICIENTES")
        self.assertEqual(self.code([], self.FULL_ZERO, self.GOES_ZERO), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")
        self.assertEqual(self.code([self.NEG], self.FULL_ZERO, self.GOES_ZERO), "R6_SIN_SENAL_EN_DATOS_DISPONIBLES")

    def test_situation_c_needs_an_interpretable_percentile(self):
        p = E.review_priority([self.VIG], self.FULL_RAIN, self.GOES_ZERO, dict(status="CALCULADO", percentile_24h=97))
        self.assertEqual(p["code"], "R1_REVISION_PRIORITARIA")
        p = E.review_priority([self.VIG], self.FULL_RAIN, self.GOES_ZERO, dict(status="NO_DISPONIBLE"))
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

    def test_vocabulary_is_separate_from_senamhi_levels(self):
        codes = " ".join(p["code"] + p["label_es"] for p in E.REVIEW_PRIORITIES).upper()
        for level in ("ROJO", "NARANJA", "AMARILLO", "VERDE"):
            self.assertNotIn(level, codes)
        self.assertNotIn("PROBABILIDAD", codes)


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

    def test_committed_state_replays_from_its_inputs(self):
        out = json.loads(E.OUT.read_text(encoding="utf-8"))
        current = {k: E.sha(p) for k, p in (("zones", E.ZONES), ("links", E.LINKS), ("imerg_north", E.IMERG_NORTH),
                                            ("imerg_v08", E.IMERG_V08), ("goes19", E.GOES), ("geos_cf", E.GEOS))}
        if out["inputs"] != current:
            self.skipTest("an input changed after the committed state; the v0.9 workflows regenerate and check it")
        self.assertEqual(E.main(["--check"]), 0)
