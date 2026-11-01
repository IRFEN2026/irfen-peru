"""IRFEN v0.9 · vista privada unificada de vigilancia costera (site/v09/vigilancia.html + surveillance_view_v0_1.json).

Comprueba guardas, reproducibilidad del paquete, cobertura Tumbes–Tacna, ventanas de lluvia sin ceros inventados,
atribución de avisos a SENAMHI vía INDECI/COEN, separación de fenómenos, fechas y calidad por fuente, puerta de
publicación y, si hay Chromium, el recorrido en escritorio y móvil."""
import importlib.util
import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("sv", "scripts/v09_build_surveillance_view.py")
D = json.loads(B.OUT.read_text(encoding="utf-8"))
PAGE = (ROOT / "site/v09/vigilancia.html").read_text(encoding="utf-8")


class Bundle(unittest.TestCase):
    def test_rebuilds_byte_for_byte(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(B.main(["--check"]), 0)
        # Research Preview 1 freeze: every released file still matches the SHA-256 recorded in the manifest
        import hashlib
        man = json.loads((ROOT / "research/v09/RESEARCH_PREVIEW_1_MANIFEST.json").read_text(encoding="utf-8"))
        for rel, sha in man["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), sha, rel)
        self.assertFalse(man["public_alerting"] or man["predictive_engine_enabled"] or man["merged_into_main"])

    def test_guards(self):
        for k, v in B.GUARDS.items():
            self.assertEqual(D[k], v, k)
        self.assertFalse(D["predictive_engine_enabled"])
        self.assertFalse(D["notifications_enabled"])
        self.assertIn("no significa ausencia de peligro", D["disclaimer_es"])

    def test_whole_coast_tumbes_to_tacna(self):
        self.assertEqual(D["coast_departments"][0], "TUMBES")
        self.assertEqual(D["coast_departments"][-1], "TACNA")
        self.assertEqual(len(D["coast_departments"]), 11)
        self.assertEqual(set(D["departments"]), set(D["coast_departments"]))
        if D["admin"]["status"] == "OK":
            self.assertEqual({f["properties"]["id"] for f in D["admin"]["departments"]["features"]}, set(D["coast_departments"]))
            self.assertEqual(D["admin"]["source"]["legal_status"], "REFERENTIAL_CENSUS_LIMITS_NOT_LEGAL_DEMARCATION")

    def test_rain_windows_never_invent_zeros(self):
        self.assertEqual(D["rain"]["windows_h"], [1, 3, 6, 24, 72])
        c = D["rain"]["coast"]
        if c["status"] == "OK":
            for k, w in c["windows"].items():
                if w["status"] == "COMPLETA":
                    self.assertEqual(len(w["values"]), len(c["cells"]))
                    self.assertEqual(w["half_hours"][0], w["half_hours"][1])
                else:
                    self.assertIsNone(w["values"])
            for dep, st in c["department_stats"].items():
                for w in st.values():
                    if w["valid_cells"] < w["cells"]:
                        self.assertIsNone(w["mean_mm"])
        for f in D["rain"]["north_zones"]["zones"]["features"]:
            for w in f["properties"]["windows"].values():
                self.assertEqual(w["mm"] is None, w["status"] != "COMPLETA")

    def test_avisos_attributed_and_classified(self):
        self.assertTrue(D["avisos"])
        for a in D["avisos"]:
            self.assertIn("SENAMHI reproducido por INDECI/COEN", a["attribution"])
            self.assertIn(a["category"], ("LLUVIA_INTENSA", "ACTIVACION_QUEBRADAS", "METEOROLOGICO", "OTRO"))
            if a["url"]:
                self.assertTrue(a["url"].startswith("https://portal.indeci.gob.pe/"), a["url"])
            if not a["level"]:
                self.assertTrue(a["level_note"])

    def test_three_phenomena_and_gaps_are_declared(self):
        self.assertEqual({p["id"] for p in D["phenomena"]}, {"CRECIDA_RIO", "INUNDACION_PLUVIAL", "ACTIVACION_QUEBRADAS"})
        self.assertTrue(D["rivers"]["realtime_flow"].startswith("NO_DISPONIBLE"))
        self.assertTrue(D["rivers"]["hydrological_avisos"].startswith("NO_INTEGRADOS"))
        self.assertGreaterEqual(len(D["pending"]), 5)
        for s in D["sources"]:
            self.assertTrue(s["quality"])

    def test_river_history_is_measured_daily_mean_only(self):
        for h in D["rivers"]["history"]:
            self.assertIn("CAUDAL_MEDIO_DIARIO", h["statistic"])
        for t in D["rivers"]["anticipation_status"]:
            self.assertIn(t["status"], ("NO_EVALUABLE", "FUERA_DE_ALCANCE"))

    def test_settlements_are_documentary_locations(self):
        self.assertIn("no es la quebrada", D["quebradas"]["ana_source"]["note"])
        self.assertGreater(len(D["quebradas"]["ana_points"]), 500)


class Page(unittest.TestCase):
    def test_guards_disclaimers_and_safety(self):
        self.assertIn('<meta name="robots" content="noindex,nofollow">', PAGE)
        self.assertIn("La ausencia de datos no significa ausencia de peligro", PAGE)
        self.assertIn('D.activation_gate!=="BLOCKED"', PAGE)
        self.assertIn("intervalos de visualización, no umbrales", PAGE)
        self.assertIn("IRFEN no emite avisos", PAGE)
        self.assertNotRegex(PAGE, r"\binnerHTML\s*=\s*[^;]*\b(a|p|s|f)\.(description|name|phenomenon)\b(?![^;]*safe)")
        self.assertIn('rel="noopener noreferrer"', PAGE)
        self.assertNotIn("Notification", PAGE)
        self.assertNotIn("navigator.serviceWorker", PAGE)

    def test_scripts_only_pinned_leaflet_with_integrity(self):
        srcs = re.findall(r'<script src="([^"]+)"', PAGE)
        self.assertEqual(srcs, ["https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"])
        self.assertIn('integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="', PAGE)

    def test_inline_bundle_supported_for_single_file_demo(self):
        self.assertIn('document.getElementById("bundle")', PAGE)
        self.assertIn("../data/v09/surveillance_view_v0_1.json", PAGE)

    def test_internal_links_exist(self):
        for href in set(re.findall(r'href="([a-z_]+\.html)', PAGE)):
            self.assertTrue((ROOT / "site/v09" / href).is_file(), href)

    def test_publication_gate_withholds_the_view(self):
        g = _load("gate", "scripts/v09_pages_publication_gate.py")
        self.assertIn("site/v09/vigilancia.html", g.TERRITORY_PATHS)
        self.assertIn("site/data/v09/surveillance_view_v0_1.json", g.TERRITORY_PATHS)
        cfg = json.loads((ROOT / "config/v09_public_demo_v0_1.json").read_text(encoding="utf-8"))
        self.assertIsNot(cfg.get("publish_v09_territory"), True)


@unittest.skipUnless(importlib.util.find_spec("playwright"), "playwright not installed")
class Browser(unittest.TestCase):
    def test_desktop_and_mobile_journey(self):
        smoke = _load("smoke", "qa/replay_tools/v09_surveillance_view_smoke.py")
        local = os.environ.get("IRFEN_LOCAL_LEAFLET")
        out = Path(os.environ.get("IRFEN_SMOKE_OUT", "/tmp/irfen_surveillance_smoke"))
        try:
            rep = smoke.run(out, Path(local) if local else None)
        except Exception as e:  # noqa: BLE001
            if "Executable doesn't exist" in str(e):
                self.skipTest("Chromium not installed")
            raise
        for r in rep["runs"]:
            self.assertEqual(r["errors"], [], r["name"])
            self.assertEqual(r["broken_internal_links"], [], r["name"])
            self.assertFalse(r["checks"]["overflow_x"], r["name"])
            self.assertEqual(r["checks"]["summary_rows"], 11)
            self.assertTrue(r["checks"]["leaflet"], "Leaflet not loaded (network to unpkg?)")
            self.assertGreater(r["checks"]["aviso_highlight_links"], 0)
            self.assertEqual(r["checks"]["river_chart"], 1)


if __name__ == "__main__":
    unittest.main()
