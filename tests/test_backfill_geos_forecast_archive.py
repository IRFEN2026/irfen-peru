import importlib.util
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_geos_forecast_archive",
    ROOT / "scripts" / "backfill_geos_forecast_archive.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GeosHistoryBackfillTests(unittest.TestCase):
    def test_dataset_name_preserves_issue_cycle(self):
        self.assertEqual(
            MODULE.dataset_name(MODULE.date(2026, 8, 1)),
            "met_tavg_1hr_glo_L1440x721_slv.20260801_09z",
        )

    def test_parse_ascii_tprec(self):
        payload = """tprec, [2][2][2]
[0][0], 1.0E-6, 2.0E-6
[0][1], 3.0E-6, 4.0E-6

[1][0], 5.0E-6, 6.0E-6
[1][1], 7.0E-6, 8.0E-6

time, [2]
739830.0, 739830.0416667
lat, [2]
-10.0, -9.75
lon, [2]
-80.0, -79.75
"""
        cube = MODULE.parse_ascii_tprec(payload, (2, 2, 2))
        self.assertEqual(cube.shape, (2, 2, 2))
        self.assertTrue(np.allclose(cube[1, 1], [7e-6, 8e-6]))

    def test_parse_rejects_dods_error(self):
        with self.assertRaises(RuntimeError):
            MODULE.parse_ascii_tprec('Error { message = "missing"; };', (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
