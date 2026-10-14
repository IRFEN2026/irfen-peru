"""IRFEN v0.9: la comprobación de desfase detecta una fuente etiquetada con la fecha de inicio de la ventana."""
import importlib.util
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_obs_lag_check", ROOT / "scripts/v09_obs_lag_check.py")
L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(L)


def series(shift_days: int = 0, noise: float = 0.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    start = date(2026, 1, 1)
    ref, new = {}, {}
    for prov in ("2001", "2401", "1401"):
        rain = rng.gamma(0.4, 12.0, 90) * (rng.random(90) < 0.4)
        for k, value in enumerate(rain):
            day = start + timedelta(days=k)
            ref[(day.isoformat(), prov)] = float(value)
            label = day - timedelta(days=shift_days)  # la fuente nueva etiqueta con otra fecha
            new[(label.isoformat(), prov)] = float(max(0.0, value + noise * rng.normal()))
    return ref, new


class LagCheck(unittest.TestCase):
    def test_aligned_source_is_usable(self):
        ref, new = series(noise=1.0)
        out = L.verdict(L.lag_correlations(ref, new))
        self.assertEqual(out["state"], "ALIGNED")
        self.assertTrue(out["usable"])

    def test_start_date_labels_are_detected(self):
        ref, new = series(shift_days=1, noise=1.0)
        corr = L.lag_correlations(ref, new)
        out = L.verdict(corr)
        self.assertEqual(out["state"], "DATE_LABEL_SUSPECT")
        self.assertFalse(out["usable"])
        self.assertEqual(out["best_lag_days"], 1)

    def test_small_sample_is_not_trusted(self):
        ref, new = series()
        few = dict(list(new.items())[:10])
        self.assertEqual(L.verdict(L.lag_correlations(ref, few))["state"], "INSUFFICIENT_SAMPLE")


if __name__ == "__main__":
    unittest.main()
