"""Offline SYNTHETIC tests for station-to-IMERG cell sampling (no real rain asserted)."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_station_imerg_cell_replay", ROOT / "scripts/v09_station_imerg_cell_replay.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
STATION = dict(station_code="000135", station_name="EL SALTO", latitude=-3.4517083,
               longitude=-80.2802, coordinate_provenance="SYNTHETIC_TEST_REFERENCE",
               coordinate_datum_status="UNVERIFIED")
START = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
END = START + timedelta(hours=24)


def synthetic_grid(_path):
    return (np.array([-3.55, -3.45]), np.array([-80.35, -80.25, -80.15]),
            np.array([[0, 0, 0], [0, 2, 5]], dtype=float), "mm/hr")


class TestStationCell(unittest.TestCase):
    def test_cell_and_half_hour_unit_conversion(self):
        r = M.pixel_at_station(*synthetic_grid(None)[:3], STATION["latitude"], STATION["longitude"], "mm/hr")
        self.assertEqual(r["cell_id"], "r1:c1")
        self.assertEqual(r["accumulation_30min_mm"], 1)
        self.assertEqual(r["status"], "VALID_SATELLITE_ESTIMATE")

    def test_nodata_is_missing_not_zero(self):
        lats, lons, grid, _ = synthetic_grid(None)
        grid[1, 1] = np.nan
        r = M.pixel_at_station(lats, lons, grid, STATION["latitude"], STATION["longitude"], "mm/hr")
        self.assertEqual(r["status"], "MISSING_NOT_ZERO")
        self.assertIsNone(r["accumulation_30min_mm"])

    def test_reject_units_and_extrapolation(self):
        lats, lons, grid, _ = synthetic_grid(None)
        with self.assertRaises(ValueError):
            M.pixel_at_station(lats, lons, grid, -3.4517, -80.2802, "mm")
        with self.assertRaisesRegex(ValueError, "NO_EXTRAPOLATION"):
            M.pixel_at_station(lats, lons, grid, -4, -80.2802, "mm/hr")

    def test_24h_missing_slot_never_returns_sum(self):
        times = M.slots(START, END)
        rows = {t.isoformat(): dict(status="VALID_SATELLITE_ESTIMATE", accumulation_30min_mm=1)
                for t in times[:-1]}
        r = M.summarize(times, rows)
        self.assertEqual(r["valid_half_hours"], 47)
        self.assertEqual(r["missing_half_hours"], 1)
        self.assertIsNone(r["satellite_accumulated_mm"])

    def test_complete_24h_sums_correctly(self):
        times = M.slots(START, END)
        rows = {t.isoformat(): dict(status="VALID_SATELLITE_ESTIMATE", accumulation_30min_mm=1)
                for t in times}
        self.assertEqual(M.summarize(times, rows)["satellite_accumulated_mm"], 48)

    def test_build_report_does_not_infer_risk_or_gauge_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            filenames = []
            for d in (START, START + timedelta(minutes=30)):
                p = Path(tmp) / ("3B-HHR-E.MS.MRG.3IMERG." + d.strftime("%Y%m%d-S%H%M%S") + "-E000000.V07B.HDF5")
                p.write_bytes(b"SYNTHETIC_TEST_ONLY")
                filenames.append(p)
            r = M.build_report([STATION], filenames, START, END, synthetic_grid)
        st = r["stations"][0]
        self.assertEqual(len(r["granule_manifest"]), 2)
        self.assertEqual(st["valid_half_hours"], 2)
        self.assertEqual(st["missing_half_hours"], 46)
        self.assertIsNone(st["satellite_accumulated_mm"])
        self.assertIsNone(st["station_observation_mm"])
        self.assertIsNone(r["decision_thresholds"])
        self.assertEqual(r["activation_gate"], "BLOCKED")

    def test_duplicate_granule_start_fails(self):
        paths = [Path("IMERG.20261027-S120000-a.HDF5"), Path("IMERG.20261027-S120000-b.HDF5")]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            M.build_report([STATION], paths, START, END, synthetic_grid)

    def test_coordinate_requirements(self):
        with self.assertRaisesRegex(ValueError, "provenance"):
            M.verify_station(dict(STATION, coordinate_provenance=None))
        with self.assertRaises(ValueError):
            M.verify_station(dict(STATION, latitude=91))

    def test_utc_alignment_and_aware_required(self):
        with self.assertRaises(ValueError):
            M.utc("2026-10-27T12:00:00")
        with self.assertRaises(ValueError):
            M.slots(START + timedelta(minutes=1), END)


if __name__ == "__main__":
    unittest.main()
