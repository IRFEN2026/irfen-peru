"""Resultados REALES de la recuperación única del 26-oct y del registro v2 (comprobación de lo que se afirma)."""
import json
import tempfile
import unittest
from pathlib import Path

import _synth

from irfen_gauge_imerg.granules import parse
from irfen_gauge_imerg.observations import check_ledger
from irfen_gauge_imerg.run_pipeline import run

assert _synth.T0  # ruta del paquete y bloqueo de red

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "retrieval/output_20261026"
LEDGER_V2 = HERE / "evidence/tumbes_2026-10/north_gauge_reports_2026-10-21_26_v2.json"
MANIFEST = HERE / "evidence/imerg_early_granule_manifest_2026-10-21_26_v1.json"


class OneShotRetrieval(unittest.TestCase):
    def setUp(self):
        self.log = json.loads((OUT / "retrieval_log.json").read_text(encoding="utf-8"))

    def test_cmr_confirms_all_192_manifest_granules_as_v07c(self):
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        want = sorted({g["granule"] for w in m["windows"] if w["id"] in (
            "rainday_2026-10-22_PET", "rainday_2026-10-23_PET", "rainday_2026-10-24_PET", "rainday_2026-10-25_PET")
            for g in w["granules"]})
        self.assertEqual(len(want), 192)
        self.assertEqual(sorted(self.log["cmr_items"]), want)
        self.assertEqual(self.log["cmr"]["discrepancies"], [])
        for name, it in self.log["cmr_items"].items():
            self.assertEqual(parse(name).version, "V07C")
            self.assertTrue(it["concept_id"].endswith("-GES_DISC"))
            self.assertTrue(it["get_data_urls"][0].startswith("https://data.gesdisc.earthdata.nasa.gov/"))

    def test_no_granule_retained_and_reason_recorded(self):
        im = self.log["imerg"]
        self.assertEqual((im["login"], im["search_matches"], im["retrieved"], im["expected"]), ("OK", 192, 0, 192))
        self.assertTrue(all("hora interna None" in e["error"] for e in im["errors"]))
        block = json.loads((OUT / "imerg_early_tumbes_block_2026-10-21T12_25T12.json").read_text(encoding="utf-8"))
        self.assertEqual(block["granules"], [])

    def test_senamhi_unreachable_recorded_not_bypassed(self):
        reqs = self.log["metadata"]["senamhi_public"]["requests"] + self.log["station_records"]["requests"]
        self.assertTrue(reqs)
        self.assertTrue(all(r.get("http_status") is None and "ConnectTimeout" in r.get("error", "") for r in reqs))

    def test_oscar_has_none_of_the_ten_stations(self):
        names = {c["name"] for c in self.log["metadata"]["oscar"]["candidates"]}
        for n in ("LA CRUZ", "MATAPALO", "PAPAYAL", "PUERTO PIZARRO", "RICA PLAYA", "CABO INGA"):
            self.assertNotIn(n, names)


class LedgerV2(unittest.TestCase):
    def test_candidate_coordinates_are_too_coarse_and_unconfirmed(self):
        doc = json.loads(LEDGER_V2.read_text(encoding="utf-8"))
        el = check_ledger(doc)
        self.assertEqual(sum(v["exploratory"] for v in el.values()), 0)
        coarse = [k for k, v in el.items() if "COORDINATE_PRECISION_INSUFFICIENT:0.1deg" in v["reasons"]]
        self.assertEqual(len(coarse), 13)
        for o in doc["observations"]:
            for c in o["station"]["candidate_ids"]:
                if c.get("scheme") == "SENAMHI_ATLAS_ANEXO1_CODE":
                    self.assertEqual(c["match_basis"], "NOMBRE_IGUAL_IDENTIDAD_NO_CONFIRMADA")
            self.assertIsNone(o["station"]["official_id"])

    def test_committed_v2_run_reproduces(self):
        ref = HERE / "reports/real_run_2026-10-27"
        for use in ("exploratory", "metrics", "calibration"):
            with self.subTest(use=use), tempfile.TemporaryDirectory() as td:
                m = run(LEDGER_V2, None, use, "EARLY:V07", Path(td), fixed_time="2026-10-27T00:00:00Z")
                self.assertEqual(m["summary"]["pairs"], 0)
                for n in ("eligibility.json", "pairs.json", "evaluation.json", "calibration.json"):
                    self.assertEqual(Path(td, n).read_text(encoding="utf-8"),
                                     (ref / use / n).read_text(encoding="utf-8"), f"{use}/{n}")


if __name__ == "__main__":
    unittest.main()
