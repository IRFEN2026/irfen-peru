"""IRFEN v0.9 · cuencas de aportación experimentales (HydroSHEDS, no oficial) y robustez lluvia–caudal del río Piura.
Sin red. Comprueba documentación de estaciones, topología, áreas, no sustitución de la geometría vigente, régimen de
regulación, controles de autocorrelación y de selección de desfase, y que no se ajustan umbrales."""
import gzip
import hashlib
import importlib.util
import io
import json
import re
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("pc", "scripts/v09_piura_catchments.py")
R = _load("pr", "scripts/v09_piura_robustness.py")
X = _load("px", "scripts/v09_pechp_extract.py")
CA = json.loads(C.OUT.read_text(encoding="utf-8"))
RO = json.loads(R.OUT.read_text(encoding="utf-8"))
ST = json.loads(C.STATIONS.read_text(encoding="utf-8"))
PX = json.loads(X.OUT.read_text(encoding="utf-8"))


class Stations(unittest.TestCase):
    def test_only_documented_coordinates_are_used(self):
        doc = (ROOT / "data/v09/sources/historical_floods/docs/pnud_ctar_piura_2000_apendice_d.pdftotext_layout.txt").read_text(encoding="utf-8")
        self.assertIn("5º11´55” latitud sur, 80º37´20” longitud oeste", doc)
        self.assertIn("7,790 km2", doc)
        self.assertIn("7742 Km2", doc)
        for s in ST["stations"]:
            if s["lat"] is None:
                c = next(x for x in CA["catchments"] if x["station"] == s["id"])
                self.assertEqual(c["status"], "SIN_COORDENADA_DOCUMENTADA")
                self.assertNotIn("imerg_cells", c)
        sc = next(s for s in ST["stations"] if s["id"] == "PUENTE_SANCHEZ_CERRO")
        self.assertAlmostEqual(sc["lat"], -(5 + 11 / 60 + 55 / 3600), places=5)
        self.assertAlmostEqual(sc["lon"], -(80 + 37 / 60 + 20 / 3600), places=5)
        self.assertEqual(sum(v for k, v in ST["subbasins_documented"]["km2"].items() if k in
                             ("Bigote-Huarmaca", "Chulucanas", "Tambogrande", "Medio Piura")), 7789.38)


class Catchments(unittest.TestCase):
    def test_rebuilds_and_inputs_match_their_hashes(self):
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(["--check"]), 0)
        for name in ("dir15", "acc15"):
            raw = gzip.decompress((C.HS / f"{name}.npy.gz").read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), CA["provenance"][f"{name[:3]}_npy_sha256"])

    def test_topology_area_and_status(self):
        self.assertEqual(CA["topology"]["d8_cycles_in_crop"], 0)
        c = next(x for x in CA["catchments"] if x["station"] == "PUENTE_SANCHEZ_CERRO")
        self.assertEqual(c["status"], "VALIDADA_EXPERIMENTAL")
        self.assertFalse(c["touches_crop_edge"])
        self.assertLess(abs(c["area_ratio_to_documented"] - 1), C.TOL_AREA)
        self.assertLess(abs(c["hydrorivers"]["upland_skm"] / c["area_km2_pixels"] - 1), C.TOL_HYBAS)
        self.assertGreater(c["overlap"]["share_of_catchment_inside_uh_1378"], 0.95)
        areas = [s["area_km2"] for s in c["snap_sensitivity"] if s["snap_cells"] >= 1]
        self.assertLess((max(areas) - min(areas)) / min(areas), 0.01)  # outlet choice stable beyond the raw pixel

    def test_d8_tracing_on_a_toy_grid(self):
        d = np.array([[1, 1, 4], [1, 1, 4], [16, 16, 4]], np.uint8)  # (2,0) and (2,1) drain west, out of the grid
        m = C.upstream(d, 2, 2)
        self.assertEqual(int(m.sum()), 7)
        self.assertEqual(C.has_cycles(np.array([[1, 16]], np.uint8)), 1)

    def test_imerg_fractions_are_fractions(self):
        c = next(x for x in CA["catchments"] if x["station"] == "PUENTE_SANCHEZ_CERRO")
        self.assertTrue(all(0 < x["fraction_inside"] <= 1 for x in c["imerg_cells"]))
        total = sum(x["fraction_inside"] * 11.13 * 11.08 for x in c["imerg_cells"])  # ≈ km² at 5° S
        self.assertLess(abs(total / c["area_km2_pixels"] - 1), 0.05)

    def test_current_geometry_is_not_replaced(self):
        self.assertFalse(CA["replaces_current_geometry"])
        self.assertFalse(CA["official_geometry"])
        u = json.loads((ROOT / "data/v09/research/uh_units_v0_1.json").read_text(encoding="utf-8"))
        self.assertIn("1378", [x["code"] for x in u["units"]])


class PechpExtension(unittest.TestCase):
    def test_every_extracted_river_table_passes_its_printed_column_sums(self):
        n = 0
        for m in PX["months"]:
            r = m["tables"].get("rivers", {})
            if r.get("status") == "OK":
                self.assertTrue(r["column_checksums"], m["month"])
                for col, v in r["column_checksums"].items():
                    self.assertTrue(v["matches"], (m["month"], col, v))
                self.assertTrue(all(d["readers"] == "DOS_LECTORES" for d in r["days"].values()), m["month"])
                n += 1
        self.assertGreaterEqual(n, 20)

    def test_chart_only_months_are_not_digitised(self):
        for key in ("2016-01", "2016-02", "2016-03", "2016-04", "2017-01", "2017-02", "2019-02", "2019-03", "2019-04"):
            m = next(x for x in PX["months"] if x["month"] == key)
            self.assertNotEqual(m["tables"]["rivers"].get("status"), "OK", key)


class Robustness(unittest.TestCase):
    def test_rebuilds_byte_for_byte(self):
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(["--check"]), 0)

    def test_only_validated_catchments_are_recomputed(self):
        for st, a in RO["analyses"].items():
            c = next(x for x in CA["catchments"] if x["station"] == st)
            self.assertEqual(a["status"] == "RECALCULADO", c["status"] == "VALIDADA_EXPERIMENTAL", st)

    def test_regime_rule_is_applied_as_declared(self):
        for m, v in RO["regime"]["months"].items():
            q, r = v["median_q_sanchez_cerro"], v["median_regulation_share"]
            if q is None:
                continue
            expected = ("DOMINADO_POR_REGULACION" if (r is not None and r > 0.5) or q < 5 else
                        "APORTACION_NATURAL_DOMINANTE" if r is not None and r < 0.1 else "MIXTO")
            self.assertEqual(v["regime"], expected, m)

    def test_lag_selection_null_and_three_questions_present(self):
        a = RO["analyses"]["PUENTE_SANCHEZ_CERRO"]["seasons"]
        for y, s in a.items():
            for t, r in s["targets"].items():
                if "levels" not in r:
                    continue
                self.assertEqual([c["lag_days"] for c in r["levels"]], R.LAGS)
                p = r["lag_selection_null_levels"]["p_value"]
                self.assertTrue(p is None or 0 < p <= 1)
                self.assertEqual(set(r["day_convention_sensitivity"]), {"dia_utc", "dia_utc_menos_1", "dia_utc_mas_1", "aprox_12_12_utc"})
                q = r["three_questions"]["A3"]
                self.assertIn("partial_spearman_Q_d_with_A_d_given_Q_dminus1", q["retrospective_explanation"])
                self.assertEqual([x["lead_days"] for x in q["anticipation"]], [1, 2, 3])

    def test_partial_correlation_removes_a_shared_driver(self):
        rng = np.random.default_rng(0)
        z = rng.normal(size=200)
        x, y = z + 0.1 * rng.normal(size=200), z + 0.1 * rng.normal(size=200)
        self.assertGreater(R.spear(x, y), 0.9)
        self.assertLess(abs(R.partial_spear(x, y, z)), 0.3)

    def test_no_thresholds_and_guards(self):
        self.assertFalse(RO["rules"]["thresholds_fitted_to_2017"])
        for k, v in R.GUARDS.items():
            self.assertEqual(RO[k], v, k)
        self.assertNotRegex(R.OUT.read_text(encoding="utf-8"), r'"(threshold|umbral)[a-z_]*":\s*[0-9]')


class View(unittest.TestCase):
    def test_view_is_reproducible_self_contained_and_outside_site(self):
        Vw = _load("vw", "scripts/v09_render_piura_catchments_view.py")
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(Vw.main(["--check"]), 0)
        html = Vw.OUT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(src|href)=\"https?://", html))
        self.assertIn("no oficial", html)
        self.assertFalse(str(Vw.OUT.relative_to(ROOT)).startswith("site/"))


if __name__ == "__main__":
    unittest.main()
