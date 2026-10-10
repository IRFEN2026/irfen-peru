"""IRFEN v0.9 dashboard bundle (site/data/v09/dashboard_v0_1.json): guards and content. Offline."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_build_dashboard_data", ROOT / "scripts/v09_build_dashboard_data.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


class Simplify(unittest.TestCase):
    def test_rings_stay_closed_and_degenerate_rings_drop(self):
        square = dict(type="Polygon", coordinates=[[[0, 0], [0.0005, 0.00001], [1, 0], [1, 1], [0, 1], [0, 0]]])
        ring = B.simplify_geometry(square, 0.002)["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(len(ring), 5)  # the near-collinear vertex is removed
        tiny = dict(type="Polygon", coordinates=[[[0, 0], [0.0001, 0], [0, 0.0001], [0, 0]]])
        self.assertIsNone(B.simplify_geometry(tiny, 0.01))


class Bundle(unittest.TestCase):
    def setUp(self):
        self.out = B.build()

    def test_guards_and_disclaimer(self):
        for key, value in B.GUARDS.items():
            self.assertEqual(self.out[key], value)
        self.assertFalse(self.out["public_alerting"])
        self.assertIn("No es un sistema de alerta", self.out["disclaimer_es"])

    def test_content_is_traceable(self):
        kinds = {f["properties"]["kind"] for f in self.out["geometries"]["features"]}
        self.assertEqual(kinds, {"BASIN", "PROVINCE"})
        for a in self.out["avisos"]:
            self.assertIn("revisions", a)
            self.assertTrue(a["documents"])
            self.assertIn(a["official_level"], (None, "ROJO", "NARANJA", "AMARILLO", "VERDE"))
        self.assertLessEqual(len(self.out["events"]), 60)
        self.assertIn("viewer_stale_after_minutes", self.out["source"])
        self.assertNotIn("request_log", self.out["source"]["last_check"] or {})

    def test_page_recomputes_status_and_staleness_in_the_browser(self):
        html = (ROOT / "site/v09/index.html").read_text(encoding="utf-8")
        self.assertIn("function statusNow", html)
        self.assertIn("viewer_stale_after_minutes", html)
        self.assertIn("No es un nivel SENAMHI", html)
        self.assertIn('meta name="robots" content="noindex"', html)
