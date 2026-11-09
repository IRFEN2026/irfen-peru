"""P0 #496 · reconstruction from the original IMERG HDF5: SYNTHETIC unit tests of every rule (no NASA data here).

The real reconstruction runs in .github/workflows/research-v091-p0-496-hdf5.yml and its report is committed under
data/v09/research/p0_496/. These tests only prove that the code refuses what it must refuse."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p0_496", ROOT / "scripts/v091_p0_496_hdf5_reconstruction.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
LON = np.round(np.arange(-179.95, 180.0, 0.1), 2)
LAT = np.round(np.arange(-89.95, 90.0, 0.1), 2)


class Names(unittest.TestCase):
    def test_parse_and_refuse(self):
        m = R.parse_name("3B-HHR-E.MS.MRG.3IMERG.20261104-S213000-E215959.1290.V07C.HDF5")
        self.assertEqual((m["start"], m["run"], m["version"]), (datetime(2026, 11, 4, 21, 30, tzinfo=timezone.utc), "Early", "V07C"))
        for bad in ("3B-HHR-E.MS.MRG.3IMERG.20261104-S213000-E222959.1290.V07C.HDF5",   # one hour
                    "3B-HHR-E.MS.MRG.3IMERG.20261104-S213000-E215959.1200.V07C.HDF5",   # minute-of-day mismatch
                    "3B-DAY-E.MS.MRG.3IMERG.20261104-S000000-E235959.V07C.nc4", "x.HDF5"):
            with self.assertRaises(ValueError):
                R.parse_name(bad)

    def test_window_is_48_half_hours_07_to_07_pet(self):
        s = R.slots()
        self.assertEqual(len(s), 48)
        self.assertEqual(s[0], datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
        self.assertEqual(s[-1] + timedelta(minutes=30), datetime(2026, 11, 5, 12, tzinfo=timezone.utc))


class Grid(unittest.TestCase):
    def test_axes(self):
        R.check_axes(LON, LAT)
        with self.assertRaises(ValueError):
            R.check_axes(LON[::-1], LAT)      # reversed (would mirror the map)
        with self.assertRaises(ValueError):
            R.check_axes(LAT, LON)            # swapped
        with self.assertRaises(ValueError):
            R.check_axes(LON + 0.05, LAT)     # cell edges instead of centres

    def test_rounded_coordinate_is_ambiguous_between_four_cells(self):
        c = R.candidate_cells(LON[0], LAT[0], -80.5, -3.8, 0.1)
        self.assertEqual(len(c), 4)
        self.assertEqual(sorted({round(float(LON[i]), 2) for i, _ in c}), [-80.55, -80.45])
        self.assertEqual(sorted({round(float(LAT[j]), 2) for _, j in c}), [-3.85, -3.75])
        (i, j), = R.candidate_cells(LON[0], LAT[0], -80.505458, -3.8119, 0.0)
        self.assertEqual((round(float(LON[i]), 2), round(float(LAT[j]), 2)), (-80.55, -3.85))

    def test_accumulation_is_rate_times_half_hour_and_missing_is_unknown(self):
        a = np.array([[2.0, 1.0]])
        b = np.array([[4.0, np.nan]])
        acc, valid = R.accumulate([a, b])
        self.assertEqual(acc[0, 0], 3.0)          # (2 + 4) mm/h × 0.5 h
        self.assertTrue(np.isnan(acc[0, 1]))     # one half-hour missing: unknown, never 1.0 or 0.5 mm
        self.assertEqual(valid.tolist(), [[2, 1]])

    def test_fill_and_negative_values_are_missing(self):
        v = R.clean(np.array([-9999.9, -1.0, 0.0, 3.2]), -9999.9)
        self.assertTrue(np.isnan(v[0]) and np.isnan(v[1]))
        self.assertEqual(v[2:].tolist(), [0.0, 3.2])


class Stations(unittest.TestCase):
    def test_unlocated_station_is_not_paired_and_located_one_reports_all_candidates(self):
        clon, clat = LON[(LON > -81.0) & (LON < -80.0)], LAT[(LAT > -4.5) & (LAT < -3.0)]
        acc = np.full((clat.size, clon.size), 2.0)
        valid = np.full(acc.shape, 48)
        rows = R.station_rows([dict(name="X", reported_mm=50.0, lon=None, lat=None, pairing_block_es="sin coordenada"),
                               dict(name="Y", reported_mm=50.0, lon=-80.5, lat=-3.8, coordinate_precision_deg=0.1)], acc, valid, clon, clat)
        self.assertEqual(rows[0]["pairing"], "NO_EMPAREJABLE")
        self.assertNotIn("imerg_candidates_max_mm", rows[0])
        self.assertEqual(rows[1]["pairing"], "AMBIGUO_POR_PRECISION_DE_COORDENADA")
        self.assertEqual(len(rows[1]["candidate_cells"]), 4)
        self.assertEqual(rows[1]["reported_status"], "PRENSA_NO_VERIFICADO")
        acc[3, 3] = np.nan
        rows = R.station_rows([dict(name="Z", reported_mm=1.0, lon=float(clon[3]), lat=float(clat[3]), coordinate_precision_deg=0.0)],
                              acc, valid, clon, clat)
        self.assertIsNone(rows[0]["imerg_candidates_max_mm"])  # missing IMERG cell: unknown, no difference computed
        self.assertNotIn("difference_reported_minus_max_candidate_mm", rows[0])

    def test_station_config_keeps_press_values_unverified(self):
        cfg = json.loads(R.STATIONS.read_text(encoding="utf-8"))
        self.assertEqual(cfg["values_status"], "REPORTADO_POR_PRENSA_NO_VERIFICADO")
        self.assertEqual(len(cfg["stations"]), 8)
        for s in cfg["stations"]:
            self.assertEqual(s["lon"] is None, s["coordinate_source"] is None, s["name"])
            if s["lon"] is None:
                self.assertTrue(s["pairing_block_es"])


class Archived(unittest.TestCase):
    def test_archived_sums_never_impute(self):
        times = ["t0", "t1"]
        ca = dict(targets=[dict(id="cp:A"), dict(id="cp:B")], granules=[dict(time_utc="t0", rate_mm_hr=[1.0, None]),
                                                                      dict(time_utc="t1", rate_mm_hr=[3.0, 2.0])])
        self.assertEqual(R.archived_sums(ca, "catchments", times), {"cp:A": 2.0, "cp:B": None})
        na = dict(targets={"z": {}}, granules=[dict(time_utc="t0", targets=dict(z=dict(rate_mm_hr=2.0)))])
        self.assertEqual(R.archived_sums(na, "north", times), {"z": None})  # t1 absent: unknown


@unittest.skipUnless(importlib.util.find_spec("h5py"), "h5py (requirements.txt) not installed")
class Hdf5(unittest.TestCase):
    def write(self, d, name, order, units="mm/hr"):
        import h5py
        p = Path(d) / name
        grid = np.zeros((LAT.size, LON.size), dtype="float32")
        j, i = int(np.argmin(abs(LAT + 3.85))), int(np.argmin(abs(LON + 80.45)))
        grid[j, i] = 7.5
        grid[0, 0] = -9999.9
        data = grid.T[None] if order == "time,lon,lat" else grid[None]
        with h5py.File(p, "w") as f:
            g = f.create_group("Grid")
            ds = g.create_dataset("precipitation", data=data)
            ds.attrs["units"] = units
            ds.attrs["DimensionNames"] = order
            ds.attrs["_FillValue"] = np.float32(-9999.9)
            g.create_dataset("lon", data=LON)
            g.create_dataset("lat", data=LAT)
        return p, (j, i)

    def test_both_dimension_orders_give_the_same_map(self):
        with tempfile.TemporaryDirectory() as d:
            for order in ("time,lon,lat", "time,lat,lon"):
                p, (j, i) = self.write(d, f"{order.replace(',', '')}.HDF5", order)
                out = R.read_independent(p)
                self.assertEqual(out["precipitation"].shape, (LAT.size, LON.size))
                self.assertAlmostEqual(float(out["precipitation"][j, i]), 7.5, places=5)
                self.assertTrue(np.isnan(out["precipitation"][0, 0]))

    def test_wrong_units_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = self.write(d, "u.HDF5", "time,lon,lat", units="mm/day")
            with self.assertRaises(ValueError):
                R.read_independent(p)


class Guards(unittest.TestCase):
    def test_research_only(self):
        self.assertEqual(R.GUARDS["deployment_status"], "RESEARCH_ONLY")
        self.assertIsNone(R.GUARDS["calibration"])
        self.assertFalse(R.GUARDS["thresholds_changed"] or R.GUARDS["public_alerting"] or R.GUARDS["notifications_enabled"])


if __name__ == "__main__":
    unittest.main()
