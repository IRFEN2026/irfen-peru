"""Catálogo de estaciones (fuentes REALES): reproducible y sin correspondencias qc inventadas."""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _synth

assert _synth.T0  # ruta del paquete y bloqueo de red

HERE = Path(__file__).resolve().parents[1] / "station_catalog"


def rows(name):
    with (HERE / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class Catalog(unittest.TestCase):
    def test_only_user_confirmed_and_corroborated_qc_is_linked(self):
        linked = [r for r in rows("catalog_confirmed.csv") if r["qc_file_code"]]
        self.assertEqual([(r["catalog_id"], r["qc_file_code"], r["qc_link_status"]) for r in linked],
                         [("SENAMHI-ATLAS:106046", "qc00000332", "CONFIRMADO_USUARIO_CORROBORADO")])
        for r in rows("catalog_confirmed.csv"):
            if not r["qc_file_code"]:
                self.assertEqual(r["qc_link_status"], "NO_DOCUMENTADO")
        for r in rows("qc_codes_pending.csv"):
            self.assertNotEqual(r["status"], "CONFIRMADO_USUARIO_CORROBORADO")
            self.assertNotIn("lat", r)

    def test_rounded_atlas_coordinates_never_assignable(self):
        atlas = [r for r in rows("catalog_confirmed.csv") if r["catalog_id"].startswith("SENAMHI-ATLAS:")]
        self.assertEqual(len(atlas), 60)
        self.assertTrue(all(r["pixel_assignable_0p1deg"] == "False" for r in atlas))

    def test_candidates_are_never_merged(self):
        c = rows("catalog_candidates.csv")
        self.assertTrue(c)
        self.assertTrue(all(r["status"].startswith("CANDIDATO") for r in c))
        piura = [r for r in c if r["oscar_name"] == "PIURA"][0]
        self.assertEqual(piura["status"], "CANDIDATO_DUDOSO")  # altitud 49 m frente a 22 m

    def test_outputs_reproduce(self):
        with tempfile.TemporaryDirectory() as td:
            before = {n: (HERE / n).read_bytes() for n in ("catalog_confirmed.csv", "catalog_candidates.csv",
                                                           "qc_codes_pending.csv")}
            subprocess.run([sys.executable, "-B", str(HERE / "build_station_catalog.py")], check=True,
                           capture_output=True, cwd=td)
            for n, b in before.items():
                self.assertEqual((HERE / n).read_bytes(), b, n)


if __name__ == "__main__":
    unittest.main()
