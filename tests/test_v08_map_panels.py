"""Map screen UX (16-10-2026): the map is the protagonist; «Capas» and «Meteorología» are compact panels closed by
default. Presentation only: the same eight layer switches drive the same visibility logic, the weather overlay keeps
its texts, and no data path, rule or guard changes.

Static contract checks always run. The browser check runs where Playwright/Chromium are installed and Leaflet 1.9.4
can be loaded (from unpkg, or from a local build in IRFEN_LEAFLET_DIR); otherwise it is skipped.
"""
import functools
import http.server
import os
import re
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERR = (ROOT / "site/v08-territorial.js").read_text(encoding="utf-8")
WEATHER = (ROOT / "site/v08-weather-layers.js").read_text(encoding="utf-8")
LAYERS = ["monitored", "catchment", "local_channel", "collector", "node", "faja", "works", "document"]


class StaticContract(unittest.TestCase):
    def test_layers_drawer_holds_all_switches_and_is_closed_by_default(self):
        drawer = re.search(r'<div class="ti-drawer" id="ti-layers-panel"[^>]*>(.*?)</div></div><div id="ti-map-status"', TERR, re.S)
        self.assertIsNotNone(drawer, "layers drawer missing")
        self.assertRegex(drawer.group(0), r'id="ti-layers-panel" role="dialog" aria-label="[^"]+" hidden>')
        self.assertIn('id="ti-layers-btn" aria-expanded="false" aria-controls="ti-layers-panel"', TERR)
        for kind in LAYERS:
            self.assertEqual(len(re.findall(rf'<input type="checkbox" data-ti-layer="{kind}" checked>', drawer.group(1))), 1, kind)
        self.assertIn('id="ti-legend"', drawer.group(1))
        self.assertIn("No se crean marcadores para suplir geometrías faltantes", TERR)
        # Visibility still comes from the same switches.
        self.assertIn("function categoryOn(kind) {const el=document.querySelector('[data-ti-layer=\"'+kind+'\"]');return !!el&&el.checked;}", TERR)

    def test_weather_panel_is_closed_by_default_with_visible_state(self):
        self.assertIn('class="iw-toggle" data-iw="toggle" aria-expanded="false"', WEATHER)
        self.assertIn('<div class="iw-panel" data-iw="panel" role="dialog" aria-label="Capas meteorológicas" hidden>', WEATHER)
        self.assertIn('data-iw="rain-pill">APAGADA</span>', WEATHER)
        for state in ("APAGADA", "CARGANDO", "ACTIVA", "SIN MOSAICOS"):
            self.assertIn(state, WEATHER)
        self.assertIn('<details class="iw-more"><summary>Notas metodológicas</summary>', WEATHER)

    def test_no_new_data_sources_or_semantics(self):
        self.assertEqual(re.findall(r"https?://[^'\"]+", WEATHER),
                         ["https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi", "https://gibs.earthdata.nasa.gov/wms/epsg3857/nrt/wms.cgi"])
        for token in ("fetch(", "localStorage", "risk_score", "alert_score", "threshold"):
            self.assertNotIn(token, WEATHER)
        for token in ("risk_score", "activation_score", "alert_score", "localStorage"):
            self.assertNotIn(token, TERR)

    def test_help_texts_are_collapsible_not_removed(self):
        for text in ("Aquí aparecen los candidatos definidos", "<b>RESEARCH / TEST MODE.</b>", "RESEARCH_ONLY", "TEST_ONLY"):
            self.assertIn(text, TERR)
        self.assertIn('<details class="ti-help"><summary>Qué muestra este mapa</summary>', TERR)
        self.assertIn('<details class="ti-context" id="ti-context"><summary>Resumen del inventario y avances recientes</summary>', TERR)


def _browser():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(args=["--no-proxy-server"]).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_browser(), "Playwright/Chromium not installed")
class InBrowser(unittest.TestCase):
    def test_panels_closed_by_default_switches_still_drive_the_map(self):
        from playwright.sync_api import sync_playwright

        leaf = os.environ.get("IRFEN_LEAFLET_DIR")

        class Q(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=str(ROOT / "site")))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{srv.server_port}/"

        def route(r):
            u = r.request.url
            if leaf and "unpkg.com/leaflet@1.9.4/dist/" in u:
                name = u.rsplit("/dist/", 1)[1]
                return r.fulfill(path=str(Path(leaf) / name))
            if "tile.openstreetmap.org" in u or "gibs.earthdata.nasa.gov" in u:
                return r.fulfill(status=204, body="")
            return r.continue_() if (u.startswith(origin) or "unpkg.com/leaflet@1.9.4/" in u) else r.abort()

        try:
            with sync_playwright() as p:
                b = p.chromium.launch(args=["--no-proxy-server"])
                page = b.new_page(viewport=dict(width=1280, height=900))
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", route)
                page.goto(origin + "index.html", wait_until="networkidle")
                if not page.evaluate("typeof L !== 'undefined'"):
                    self.skipTest("Leaflet 1.9.4 not reachable (set IRFEN_LEAFLET_DIR to a local build)")
                page.click('.tab[data-tab="territorial-inventory"]')
                page.wait_for_function("document.querySelectorAll('#ti-map .leaflet-overlay-pane path').length > 0", timeout=20000)
                self.assertTrue(page.evaluate("document.getElementById('ti-layers-panel').hidden"))
                self.assertTrue(page.evaluate("[...document.querySelectorAll('#territorial-inventory [data-iw=\"panel\"]')].every(p => p.hidden)"))
                paths = lambda: page.evaluate("document.querySelectorAll('#ti-map .leaflet-overlay-pane path').length")
                n_all = paths()
                page.click("#ti-layers-btn")
                page.click('[data-ti-all-layers="off"]')
                self.assertEqual((paths(), page.inner_text("#ti-layers-count")), (0, "0/8"))
                page.click('[data-ti-all-layers="on"]')
                self.assertEqual(paths(), n_all)
                page.uncheck('[data-ti-layer="catchment"]')
                self.assertLess(paths(), n_all)
                self.assertEqual(page.inner_text("#ti-layers-count"), "7/8")
                page.check('[data-ti-layer="catchment"]')
                # Opening «Meteorología» folds «Capas»: one panel at a time over the map.
                page.click('#territorial-inventory [data-iw="toggle"]')
                self.assertTrue(page.evaluate("document.getElementById('ti-layers-panel').hidden"))
                page.keyboard.press("Escape")
                self.assertTrue(page.evaluate("document.querySelector('#territorial-inventory [data-iw=\"panel\"]').hidden"))
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
