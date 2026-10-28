"""Resolución qc → estación: lector .rda (SINTÉTICO), regla H-QC y resultados REALES comprometidos."""
import csv
import gzip
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _synth

assert _synth.T0  # ruta del paquete y bloqueo de red

QR = Path(__file__).resolve().parents[1] / "station_catalog/qc_resolution"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, QR / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(QR))
    spec.loader.exec_module(m)
    return m


read_rda = _load("read_rda")
resolve_qc = _load("resolve_qc")


def _xdr_frame() -> bytes:
    """.rda SINTÉTICO: lista «catalogue» = data.frame(StationID='000332', Latitude=-6.88)."""
    i = lambda v: struct.pack(">i", v)  # noqa: E731
    ch = lambda s: i(9 | (1 << 16)) + i(len(s)) + s.encode()  # noqa: E731
    sym = lambda s: i(1) + ch(s)  # noqa: E731
    names = i(16) + i(2) + ch("StationID") + ch("Latitude")
    df = (i(19 | (1 << 9)) + i(2) + i(16) + i(1) + ch("000332") + i(14) + i(1) + struct.pack(">d", -6.88)
          + i(2 | (1 << 10)) + sym("names") + names + i(254))
    body = i(2) + i(0x030500) + i(0x020300) + i(2 | (1 << 10)) + sym("catalogue") + df + i(254)
    return gzip.compress(b"RDX2\nX\n" + body)


class ReadRda(unittest.TestCase):
    def test_synthetic_frame(self):
        names, rows = read_rda.frame(read_rda.loads(_xdr_frame())["catalogue"])
        self.assertEqual(names, ["StationID", "Latitude"])
        self.assertEqual(rows, [("000332", -6.88)])

    def test_rejects_non_rda(self):
        with self.assertRaises(ValueError):
            read_rda.loads(b"not an rda file")


class Rule(unittest.TestCase):
    def test_station_id_rule(self):
        self.assertEqual(resolve_qc.station_id("qc00000332"), "000332")
        self.assertEqual(resolve_qc.station_id("qc00153102.txt"), "153102")
        self.assertEqual(resolve_qc.station_id("qc47287402"), "47287402")
        with self.assertRaises(ValueError):
            resolve_qc.station_id("qc332")


class RealResults(unittest.TestCase):
    def setUp(self):
        with (QR / "qc_resolution.csv").open(encoding="utf-8") as fh:
            self.r = {x["qc_file_code"]: x for x in csv.DictReader(fh)}

    def test_reque_user_evidence_and_independent_corroboration_kept_separate(self):
        r = self.r["qc00000332"]
        self.assertEqual(r["status"], "CONFIRMADO_USUARIO_CORROBORADO")
        self.assertEqual((r["station"], r["province"], r["district"]), ("REQUE", "CHICLAYO", "ETEN"))
        self.assertEqual(r["e1_user"], "True")
        self.assertEqual(r["e3_atlas_code"], "106046")
        self.assertEqual(r["e3_coherent"], "True")
        self.assertEqual((r["imerg_cell_i"], r["imerg_cell_j"]), ("1001", "831"))
        user = json.loads((QR / "user_evidence_qc_20261028.json").read_text(encoding="utf-8"))["records"][0]
        self.assertIsNone(user["coordinates_from_user"])  # las coordenadas NO provienen del usuario

    def test_no_other_code_promoted_without_user_evidence(self):
        for code, r in self.r.items():
            if code != "qc00000332":
                self.assertNotEqual(r["status"], "CONFIRMADO_USUARIO_CORROBORADO", code)
        self.assertEqual(self.r["qc00000791"]["status"], "CANDIDATO_FUERA_DE_REGION")
        self.assertEqual(self.r["qc00000791"]["lat"], "")  # sin coordenadas fuera del subconjunto

    def test_unstable_coordinates_never_select_a_pixel(self):
        for code in ("qc00000132", "qc00000247", "qc00000208"):
            self.assertEqual(self.r[code]["pixel_assignable"], "False", code)
            self.assertGreater(float(self.r[code]["coord_version_spread_deg"]), resolve_qc.MAX_SPREAD_DEG)

    def test_outputs_reproduce(self):
        before = {n: (QR / n).read_bytes() for n in ("qc_resolution.csv", "georeferenced_stations_for_imerg.csv")}
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([sys.executable, "-B", str(QR / "resolve_qc.py")], check=True, capture_output=True, cwd=td)
        for n, b in before.items():
            self.assertEqual((QR / n).read_bytes(), b, n)

    def test_georef_table_never_enables_metrics(self):
        with (QR / "georeferenced_stations_for_imerg.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(rows)
        self.assertFalse(any("METRIC" in r["allowed_use"] or "CALIBRATION" in r["allowed_use"] for r in rows))


if __name__ == "__main__":
    unittest.main()
