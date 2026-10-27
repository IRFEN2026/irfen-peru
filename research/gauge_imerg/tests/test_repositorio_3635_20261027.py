"""Hechos REALES de la consulta única al Repositorio Institucional SENAMHI (hdl 20.500.12542/3635) y del presupuesto."""
import json
import unittest
from pathlib import Path

import _synth

from irfen_gauge_imerg.grid import locate, neighbourhood

assert _synth.T0  # ruta del paquete y bloqueo de red

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "historical/repositorio_3635_20261027"
BUDGET = HERE / "historical/imerg_download_budget_proposal_20261027.json"


class Repositorio(unittest.TestCase):
    def test_handle_resolves_but_repository_unreachable(self):
        log = json.loads((OUT / "query_log.json").read_text(encoding="utf-8"))["requests"]
        api = json.loads((OUT / "handle_api.json").read_text(encoding="utf-8"))
        self.assertEqual(api["values"][0]["data"]["value"], "http://repositorio.senamhi.gob.pe/handle/20.500.12542/3635")
        self.assertEqual(log["handle_redirect.txt"]["http_status"], 302)
        for k in ("item_full.html", "item_rest.json", "datos_2024.csv"):
            self.assertIsNone(log[k]["http_status"])
            self.assertIn("ConnectTimeout", log[k]["error"])
        self.assertFalse((OUT / "datos_2024.csv.gz").exists())


class Budget(unittest.TestCase):
    def test_block_covers_3x3_of_the_four_stations(self):
        b = json.loads(BUDGET.read_text(encoding="utf-8"))
        self.assertEqual(b["status"], "PROPOSAL_NOT_AUTHORIZED")
        blk = b["spatial_block"]
        for s in b["stations"]:
            c, flags = locate(s["lat"], s["lon"])
            self.assertEqual([c.i, c.j], s["cell"])
            self.assertEqual(flags, [])
            for n in neighbourhood(c):
                self.assertTrue(blk["i0"] <= n.i < blk["i1"] and blk["j0"] <= n.j < blk["j1"])
        self.assertEqual((blk["i1"] - blk["i0"]) * (blk["j1"] - blk["j0"]), blk["cells"])
        for o in b["options"][:2]:
            self.assertEqual(o["granules"], o["days"] * 48)


if __name__ == "__main__":
    unittest.main()
