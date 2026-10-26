"""Malla, identidad de gránulos y extracción de celdas (datos SINTÉTICOS)."""
import unittest
from datetime import datetime, timezone

import _synth as S
from irfen_gauge_imerg.granules import GranuleNameError, half_hour_slots, parse
from irfen_gauge_imerg.grid import GridError, locate, neighbourhood, verify_axis
from irfen_gauge_imerg.imerg_cells import GranuleContentError, UnitError, extract_from_arrays, station_cells


class Grid(unittest.TestCase):
    def test_station_inside_cell(self):
        c, flags = locate(-5.18, -80.63)
        self.assertEqual((c.i, c.j), (993, 848))
        self.assertAlmostEqual(c.lon_center, -80.65)
        self.assertAlmostEqual(c.lat_center, -5.15)
        b = c.bounds
        self.assertTrue(b["lon_min"] <= -80.63 < b["lon_max"] and b["lat_min"] <= -5.18 < b["lat_max"])
        self.assertEqual(flags, [])

    def test_station_on_edge_is_flagged(self):
        c, flags = locate(-5.18, -80.6)
        self.assertIn("ON_CELL_EDGE", flags)
        self.assertEqual(c.i, 994)  # regla semiabierta: celda al este

    def test_0_360_longitude_rejected(self):
        with self.assertRaises(GridError):
            locate(-5.18, 279.37)

    def test_lat_lon_swapped_is_caught_by_range(self):
        with self.assertRaises(GridError):
            locate(-80.63, -5.18 + 200)

    def test_neighbourhood_3x3(self):
        c, _ = locate(-5.18, -80.63)
        nb = neighbourhood(c)
        self.assertEqual(len(nb), 9)
        self.assertIn(c, nb)

    def test_axis_checks(self):
        lat, lon, i0, j0 = S.axes()
        self.assertEqual(verify_axis(lon, "lon")["offset"], i0)
        with self.assertRaises(GridError):
            verify_axis(list(reversed(lat)), "lat")  # decreciente
        with self.assertRaises(GridError):
            verify_axis([-80.7, -80.45, -80.2], "lon")  # resolución 0,25°
        with self.assertRaises(GridError):
            verify_axis([-80.7, -80.6, -80.5], "lon")  # bordes, no centros


class Granules(unittest.TestCase):
    def test_parse_runs(self):
        t = datetime(2026, 10, 26, 12, 30, tzinfo=timezone.utc)
        for run, label in (("E", "EARLY"), ("L", "LATE"), ("F", "FINAL")):
            g = parse(S.name(t, run))
            self.assertEqual(g.run, label)
            self.assertEqual(g.start_utc, t)
            self.assertEqual(g.family, f"{label}:V07")

    def test_real_name_from_archive(self):
        g = parse("3B-HHR-E.MS.MRG.3IMERG.20261026-S123000-E125959.0750.V07C.HDF5")
        self.assertEqual((g.version, g.start_utc.hour, g.start_utc.minute), ("V07C", 12, 30))

    def test_bad_names(self):
        for bad in ("3B-HHR-E.MS.MRG.3IMERG.20261026-S123000-E125959.0760.V07C.HDF5",   # índice incoherente
                    "3B-HHR-E.MS.MRG.3IMERG.20261026-S123000-E132959.0750.V07C.HDF5",   # 60 minutos
                    "3B-HHR-E.MS.MRG.3IMERG.20261026-S123000-E125959.0750.V06B.HDF5",   # versión
                    "3B-DAY-E.MS.MRG.3IMERG.20261026-S000000-E235959.V07C.nc4"):        # producto diario
            with self.assertRaises(GranuleNameError):
                parse(bad)

    def test_slots_require_alignment_and_timezone(self):
        s = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        self.assertEqual(len(half_hour_slots(s, s.replace(day=25))), 48)
        with self.assertRaises(ValueError):
            half_hour_slots(s.replace(minute=15), s.replace(day=25))
        with self.assertRaises(ValueError):
            half_hour_slots(s.replace(tzinfo=None), s.replace(day=25, tzinfo=None))


class Cells(unittest.TestCase):
    def setUp(self):
        self.cells = station_cells(S.SYN_STATION)
        self.lat, self.lon, self.i0, self.j0 = S.axes()
        self.t = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)

    def _field(self, v):
        return [[v for _ in self.lat] for _ in self.lon]

    def test_units(self):
        n = S.name(self.t)
        extract_from_arrays(n, self.lat, self.lon, self._field(1.0), b"mm/hr", -9999.9, self.cells, self.t)
        for bad in ("mm", "kg m-2 s-1", "", "in/hr"):
            with self.assertRaises(UnitError):
                extract_from_arrays(n, self.lat, self.lon, self._field(1.0), bad, -9999.9, self.cells, self.t)

    def test_fill_and_negative_are_missing_zero_is_zero(self):
        n = S.name(self.t)
        for raw, expected in ((-9999.9, None), (-1.0, None), (float("nan"), None), (0.0, 0.0), (2.5, 2.5)):
            r = extract_from_arrays(n, self.lat, self.lon, self._field(raw), "mm/hr", -9999.9, self.cells, self.t)
            self.assertEqual(r["values"]["SYN-A"]["center_mm_hr"], expected)

    def test_internal_time_mismatch(self):
        with self.assertRaises(GranuleContentError):
            extract_from_arrays(S.name(self.t), self.lat, self.lon, self._field(1.0), "mm/hr", None, self.cells,
                                self.t.replace(minute=30))

    def test_station_outside_file_subset(self):
        far = station_cells({"FAR": {"lat": -12.0, "lon": -77.0, "coordinate_verified": True}})
        with self.assertRaises(GridError):
            extract_from_arrays(S.name(self.t), self.lat, self.lon, self._field(1.0), "mm/hr", None, far, self.t)


if __name__ == "__main__":
    unittest.main()


class Block(unittest.TestCase):
    """Bloque regional SINTÉTICO → serie de celdas por estación (recuperación previa a conocer coordenadas)."""

    def _block(self, value=2.0, missing_center=False):
        from irfen_gauge_imerg.granules import iso
        b = {"i0": 990, "i1": 1001, "j0": 857, "j1": 868}
        t = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
        rates = [[0.0 for _ in range(b["j1"] - b["j0"])] for _ in range(b["i1"] - b["i0"])]
        rates[994 - 990][863 - 857] = None if missing_center else value  # celda de (−80,55; −3,65)
        return {"schema": "irfen.gauge_imerg.imerg_block", "block_global_indices": b, "SYNTHETIC": True,
                "granules": [{"granule": S.name(t), "units": "mm/hr", "fill_value": -9999.9, "sha256": "SYN",
                              "internal_start_utc": iso(t), "retrieved_at_utc": "2026-01-10T17:00:00Z",
                              "rates_mm_hr_lon_lat": rates}]}

    def test_station_cell_from_block(self):
        from irfen_gauge_imerg.imerg_cells import build_series_from_block
        st = {"SYN-T": {"lat": -3.65, "lon": -80.55, "coordinate_verified": True}}
        # −80,55 y −3,65 son centros: dentro de la celda (994, 863) sin borde
        doc = build_series_from_block(self._block(), st)
        self.assertEqual(doc["read_errors"], [])
        v = doc["granules"][0]["values"]["SYN-T"]
        self.assertEqual(v["center_mm_hr"], 2.0)
        self.assertEqual(doc["granules"][0]["retrieved_at_utc"], "2026-01-10T17:00:00Z")
        doc = build_series_from_block(self._block(missing_center=True), st)
        self.assertIsNone(doc["granules"][0]["values"]["SYN-T"]["center_mm_hr"])

    def test_station_outside_block_rejected(self):
        from irfen_gauge_imerg.imerg_cells import build_series_from_block
        with self.assertRaises(GridError):
            build_series_from_block(self._block(), {"FAR": {"lat": -5.18, "lon": -80.63}})
