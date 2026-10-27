"""Inventario REAL de estaciones GBON/RBON del norte (OSCAR) y estado del conjunto abierto de SENAMHI."""
import json
import unittest
from pathlib import Path

import _synth

from irfen_gauge_imerg.grid import locate

assert _synth.T0  # ruta del paquete y bloqueo de red

HERE = Path(__file__).resolve().parents[1]
INV = HERE / "historical/inventory_north_gbon_rbon_20261027.json"
DL = HERE / "historical/open_data_20261027/download_log.json"


class Inventory(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(INV.read_text(encoding="utf-8"))
        self.st = {s["name"]: s for s in self.doc["stations_north"]}

    def test_identity_and_precision_from_oscar(self):
        for name, wigos in (("CHULUCANAS", "0-604-1-08602104"), ("LANCONES", "0-604-1-07610101"),
                            ("TONGORRAPE", "0-604-1-09582002"), ("TINAJONES", "0-604-1-10575101")):
            s = self.st[name]
            self.assertEqual(s["wigos_primary"], wigos)
            self.assertLessEqual(s["coordinate_precision_deg"], 0.0001)
            self.assertTrue(s["pixel_assignable"])
            cell, flags = locate(s["lat"], s["lon"])
            self.assertEqual((cell.i, cell.j), (s["imerg_cell"]["i_lon"], s["imerg_cell"]["j_lat"]))

    def test_rounded_coordinates_never_select_a_pixel(self):
        self.assertFalse(self.st["PIURA"]["pixel_assignable"])  # −5,2 / −80,6: esquina de celdas
        for s in self.doc["stations_north"]:
            if s["coordinate_precision_deg"] >= 0.1:
                self.assertFalse(s["pixel_assignable"], s["name"])

    def test_open_dataset_blocked_and_no_overlap(self):
        dl = json.loads(DL.read_text(encoding="utf-8"))
        self.assertTrue(all(v["http_status"] == 418 for v in dl["files"].values()))
        self.assertEqual(self.doc["open_dataset"]["status"], "BLOCKED_BY_PROVIDER")
        self.assertEqual(self.doc["overlap"]["real_overlap_pairs"], 0)
        self.assertEqual(self.doc["overlap"]["archived_pixel_imerg_days"],
                         ["2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13"])


if __name__ == "__main__":
    unittest.main()
