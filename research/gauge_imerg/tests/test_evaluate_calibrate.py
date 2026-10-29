"""Métricas, compuertas de muestra, calibración y prevención de fuga temporal (datos SINTÉTICOS)."""
import random
import unittest
from datetime import date, datetime, timedelta

import _synth

assert _synth.T0  # importar _synth fija la ruta del paquete y bloquea la red
from irfen_gauge_imerg.calibrate import apply_quantile_map, calibrate, chrono_split, fit_quantile_map
from irfen_gauge_imerg.evaluate import block, bootstrap_ci, evaluate, intensity_class


def pair(day: date, station: str, gauge: float, imerg: float, hours: float = 24, start_hour: int = 12):
    t0 = datetime(day.year, day.month, day.day, start_hour)
    s, e = (x.strftime("%Y-%m-%dT%H:%M:%SZ") for x in (t0, t0 + timedelta(hours=hours)))
    return {"station_id": station, "region": "SINTETICA", "window_start_utc": s, "window_end_utc": e,
            "duration_h": hours, "gauge_mm": gauge, "imerg_cell_mm": imerg, "SYNTHETIC": True}


def synthetic_doc(n_days=60, stations=("A", "B", "C"), factor=2.0, seed=1, use="calibration"):
    rng = random.Random(seed)
    d0 = date(2026, 1, 1)
    ps = []
    for k in range(n_days):
        for s in stations:
            im = 0.0 if rng.random() < 0.3 else round(rng.uniform(0.3, 20.0), 3)
            g = max(0.0, round(factor * im + rng.uniform(-0.2, 0.2), 3)) if im else 0.0
            ps.append(pair(d0 + timedelta(days=k), s, g, im))
    return {"policy": {"use": use}, "pairs": ps}


class Metrics(unittest.TestCase):
    def test_known_values(self):
        d = date(2026, 1, 1)
        ps = [pair(d, "A", 10, 5), pair(d, "A", 0, 2), pair(d, "A", 20, 0), pair(d, "A", 0, 0)]
        b = block(ps)
        c = b["continuous"]
        self.assertAlmostEqual(c["bias_mm"], (-5 + 2 - 20 + 0) / 4)
        self.assertAlmostEqual(c["MAE_mm"], (5 + 2 + 20 + 0) / 4)
        self.assertAlmostEqual(c["RMSE_mm"], ((25 + 4 + 400) / 4) ** 0.5, places=4)
        det = b["detection"]  # umbral 1 mm para 24 h
        self.assertEqual((det["hits"], det["misses"], det["false_alarms"], det["correct_negatives"]), (1, 1, 1, 1))
        self.assertEqual((det["POD"], det["FAR"]), (0.5, 0.5))
        self.assertAlmostEqual(det["CSI"], 1 / 3, places=4)
        self.assertEqual(b["sample_status"], "DESCRIPTIVE_ONLY_SMALL_SAMPLE")
        self.assertIsNone(c["pearson_r"])

    def test_small_sample_has_no_ci(self):
        doc = synthetic_doc(n_days=5)
        self.assertEqual(bootstrap_ci(doc["pairs"], lambda ps: 0.0)["status"], "CI_NOT_DEFENSIBLE")
        ev = evaluate({"pairs": [], "policy": {"use": "metrics"}})
        self.assertEqual(ev["overall"]["sample_status"], "NO_PAIRS")

    def test_strata_and_intensity_classes(self):
        ev = evaluate(synthetic_doc(n_days=20))
        self.assertEqual(set(ev["strata"]["station"]), {"A", "B", "C"})
        self.assertEqual(intensity_class(0.0), "seco (0 mm)")
        self.assertEqual(intensity_class(0.5), "traza (0–1 mm)")
        self.assertEqual(intensity_class(30.0), "fuerte (25–50 mm)")
        self.assertEqual(intensity_class(80.0), "muy fuerte (≥50 mm)")


class Calibration(unittest.TestCase):
    def test_blocked_unless_calibration_grade(self):
        self.assertEqual(calibrate(synthetic_doc(use="metrics"))["status"], "BLOCKED")
        self.assertIn("NO_VALID_PAIRS", calibrate({"policy": {"use": "calibration"}, "pairs": []})["reasons"])

    def test_blocked_with_small_sample(self):
        r = calibrate(synthetic_doc(n_days=8))
        self.assertEqual(r["status"], "BLOCKED")
        g = r["by_duration"]["24 h"]
        self.assertTrue(any(x.startswith("TRAIN_DAYS") for x in g["reasons"]))

    def test_recovers_known_factor_without_leakage(self):
        r = calibrate(synthetic_doc())
        g = r["by_duration"]["24 h"]
        self.assertEqual(g["status"], "EXPLORATORY_RESULTS_NOT_OPERATIONAL")
        self.assertFalse(g["split"]["temporal_overlap"])
        self.assertLess(g["split"]["train_last_day"], g["split"]["test_first_day"])
        m = g["methods"]["multiplicative"]
        self.assertAlmostEqual(m["model"]["k"], 2.0, delta=0.05)
        self.assertLess(m["deltas"]["delta_MAE_mm"], 0)
        self.assertEqual(m["verdict"], "IMPROVES_ON_THIS_TEST_PERIOD")
        self.assertEqual(g["methods"]["quantile_map"]["model"]["status"], "FITTED")
        self.assertEqual(g["territorial_extrapolation"]["status"], "EVALUATED")
        self.assertEqual(g["future_generalization"], "NOT_EVALUATED_SAME_SEASON")

    def test_no_correction_when_satellite_is_unbiased(self):
        r = calibrate(synthetic_doc(factor=1.0, seed=3))
        v = r["by_duration"]["24 h"]["methods"]["multiplicative"]["verdict"]
        self.assertNotEqual(v, "IMPROVES_ON_THIS_TEST_PERIOD")

    def test_overlapping_windows_are_detected_as_leakage(self):
        doc = synthetic_doc(n_days=30)
        long = pair(date(2026, 1, 20), "A", 50.0, 25.0, hours=24 * 15)  # termina después del inicio de prueba
        with self.assertRaises(AssertionError):
            chrono_split(doc["pairs"] + [long])

    def test_durations_never_mixed(self):
        doc = synthetic_doc(n_days=30)
        doc["pairs"] += [pair(date(2026, 1, 1) + timedelta(days=k), "A", 1.0, 0.5, hours=1) for k in range(5)]
        doc["pairs"] += [pair(date(2026, 1, 1) + timedelta(days=k), "B", 4.0, 2.0, hours=12) for k in range(5)]
        r = calibrate(doc)
        self.assertEqual(set(r["by_duration"]), {"24 h", "12 h", "1 h"})

    def test_loso_blocked_with_two_stations(self):
        r = calibrate(synthetic_doc(stations=("A", "B"), n_days=60))
        self.assertEqual(r["by_duration"]["24 h"]["territorial_extrapolation"]["status"], "BLOCKED")

    def test_quantile_map_monotone_and_non_negative(self):
        m = fit_quantile_map(synthetic_doc()["pairs"])
        xs = [0, 0.5, 1, 5, 10, 19, 40]
        ys = [apply_quantile_map(m, x) for x in xs]
        self.assertTrue(all(y >= 0 for y in ys))
        self.assertTrue(all(b >= a for a, b in zip(ys, ys[1:])))


if __name__ == "__main__":
    unittest.main()
