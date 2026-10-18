"""Map screen UX: the map is the protagonist; «Capas» and «Meteorología» are compact panels closed by default.
Presentation only: the same eight layer switches drive the same visibility logic, the weather overlay keeps its
sources, and no data path, rule or guard changes.

Weather states must not overstate what the page knows: ACTIVA only when every tile arrived, PARCIAL / SIN MOSAICOS
otherwise (Leaflet fires 'load' even after tile errors), and an empty tile is never read as "no rain". The IMERG
layer is a 30-min rate, so it is requested for an explicit UTC interval in the full YYYY-MM-DDTHH:MI:SSZ form that
NASA GIBS documents for subdaily layers, never for a bare date.

Static and node checks always run. The browser checks run where Playwright/Chromium are installed and Leaflet 1.9.4
can be loaded (from unpkg, or from a local build in IRFEN_LEAFLET_DIR); otherwise they are skipped.
"""
import base64
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import threading
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
TERR = (ROOT / "site/v08-territorial.js").read_text(encoding="utf-8")
WEATHER = (ROOT / "site/v08-weather-layers.js").read_text(encoding="utf-8")
LAYERS = ["monitored", "catchment", "local_channel", "collector", "node", "faja", "works", "document"]
NODE = shutil.which("node")
# 1x1 transparent PNG served in place of NASA GIBS tiles (no network in tests).
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


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
        self.assertIn("RAIN_STATE={off:['APAGADA',''],loading:['CARGANDO','wait'],on:['ACTIVA','on'],partial:['PARCIAL','wait'],error:['SIN MOSAICOS','err']}", WEATHER)
        self.assertIn('<details class="iw-more"><summary>Notas metodológicas</summary>', WEATHER)
        # Recorded node ID (pytest collection manifest): the related checks run here as sub-tests.
        for check in (self.check_activa_only_when_no_tile_failed, self.check_absence_is_never_presented_as_no_rain,
                      self.check_imerg_is_requested_for_an_interval_not_a_bare_date, self.check_time_helpers):
            with self.subTest(check=check.__name__):
                check()

    def check_activa_only_when_no_tile_failed(self):
        load = WEATHER[WEATHER.index("rain.on('load'"):WEATHER.index("rain.addTo(targetMap);")]
        self.assertIn("if(!bad){\n                setRainState('on');", load)
        self.assertIn("setRainState('partial')", load)
        self.assertIn("setRainState('error')", load)
        # No state handler may declare the layer active on its own (the bug fixed here).
        self.assertEqual(WEATHER.count("setRainState('on')"), 1)
        self.assertNotIn("rain.on('tileerror',function(){\n              setRainState", WEATHER)

    def check_absence_is_never_presented_as_no_rain(self):
        # Every user-facing sentence that could read an empty or missing tile as "no rain" is banned.
        lower = WEATHER.lower()
        for claim in ("no hay precipitación", "no hay lluvia", "sin lluvia", "no llovió", "sin precipitación representada",
                      "precipitación nula", "lluvia: 0", "0 mm"):
            self.assertNotIn(claim, lower, claim)
        # Availability is never asserted, least of all from the interval's age.
        for claim in ("disponible", "ya está publicado", "ya publicado", "datos confirmados", "intervalo publicado:"):
            self.assertNotIn(claim, lower, claim)
        self.assertIn("La antigüedad de un intervalo no garantiza que esté publicado", WEATHER)
        self.assertIn("Recibir mosaicos no confirma que haya datos de ese intervalo", WEATHER)
        load = WEATHER[WEATHER.index("rain.on('load'"):WEATHER.index("rain.addTo(targetMap);")]
        # Each verdict carries its own "absence is not no-rain" sentence; none depends on s.recent.
        self.assertEqual(load.count("ausencia de lluvia"), 3)
        self.assertNotIn("recent", load.replace("caveat", ""))
        for stale in ("Si no aparece color, no hay precipitación", "Sin color = sin precipitación"):
            self.assertNotIn(stale, WEATHER)
        legend = re.search(r'data-iw="rain-legend" hidden>(.*?)</div></div>', WEATHER, re.S).group(1)
        self.assertIn("no equivale a riesgo bajo", legend)
        self.assertIn("no equivale a ausencia de lluvia", WEATHER)
        self.assertIn("no significa ausencia de lluvia", WEATHER)

    def check_imerg_is_requested_for_an_interval_not_a_bare_date(self):
        self.assertIn("makeWms(NASA_WMS_NRT,'IMERG_Precipitation_Rate_30min_v7_NRT',s.time,opacity)", WEATHER)
        self.assertIn("makeWms(NASA_WMS_BEST,'VIIRS_SNPP_CorrectedReflectance_TrueColor',isoDayAt(dayOffset,nowMs)", WEATHER)
        self.assertNotIn("isoDay(-1)", WEATHER)
        self.assertIn('data-iw="slot"', WEATHER)
        self.assertIn("no se consulta a NASA GIBS qué intervalo está publicado", WEATHER)

    def test_no_new_data_sources_or_semantics(self):
        self.assertEqual(re.findall(r"https?://[^'\"]+", WEATHER),
                         ["https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi", "https://gibs.earthdata.nasa.gov/wms/epsg3857/nrt/wms.cgi"])
        for token in ("fetch(", "localStorage", "risk_score", "alert_score", "threshold", "GetCapabilities"):
            self.assertNotIn(token, WEATHER)
        for token in ("risk_score", "activation_score", "alert_score", "localStorage"):
            self.assertNotIn(token, TERR)

    def test_help_texts_are_collapsible_not_removed(self):
        for text in ("Aquí aparecen los candidatos definidos", "<b>RESEARCH / TEST MODE.</b>", "RESEARCH_ONLY", "TEST_ONLY"):
            self.assertIn(text, TERR)
        self.assertIn('<details class="ti-help"><summary>Qué muestra este mapa</summary>', TERR)
        self.assertIn('<details class="ti-context" id="ti-context"><summary>Resumen del inventario</summary>', TERR)
        with self.subTest(check="recent_strip"):
            self.check_recent_strip_is_compact_and_outside_the_folded_summary()

    def check_recent_strip_is_compact_and_outside_the_folded_summary(self):
        # Layout only: the strip sits below the folded summary and is always visible. Card content (renderRecent)
        # is not changed here; the plain-language cards belong to the demo PR (#386).
        self.assertRegex(TERR, r'<div id="ti-summary"[^>]*>[^<]*</div></details>\s*<details class="ti-recent-box" id="ti-recent-box" open><summary>Avances integrados recientemente</summary>\s*<div id="ti-recent" class="ti-recent"')
        # Open by default (desktop, and without JS); folded at start only on narrow screens.
        self.assertIn("const narrow=window.matchMedia?window.matchMedia('(max-width:1000px)'):null;", TERR)
        self.assertIn("if(narrow&&narrow.matches)recentBox.open=false;", TERR)
        self.assertNotIn("document.getElementById('ti-context').open=true", TERR)
        detail = TERR[TERR.index("function selectRecord(key,focus)"):TERR.index("function applyVisibility()")]
        self.assertIn("esc(advance.note)", detail)

    def check_time_helpers(self):
        """Pure helpers between TIME-HELPERS-BEGIN/END, run with node and a fixed clock (skipped without node)."""
        if not NODE:
            self.skipTest("node not installed")
        self.check_slots_default_and_peru_time()
        self.check_full_datetime_format_for_every_slot()

    def run_js(self, body):
        block = WEATHER[WEATHER.index("/* TIME-HELPERS-BEGIN"):WEATHER.index("/* TIME-HELPERS-END */")]
        out = subprocess.run([NODE, "-e", block + body], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def check_slots_default_and_peru_time(self):
        r = self.run_js(r"""
        const now=Date.parse('2026-10-18T18:47:00Z'), y=slotsFor(-1,now), t=slotsFor(0,now), e=Date.parse('2026-10-18T03:10:00Z');
        process.stdout.write(JSON.stringify({n:y.length, yDef:defaultSlot(y), y2330:y[47], tDef:defaultSlot(t),
          tFuture:t.filter(s=>s.future).map(s=>s.utc)[0], tRecent:t.filter(s=>s.recent).map(s=>s.utc),
          eToday:defaultSlot(slotsFor(0,e)), eTodayRecent:slotsFor(0,e).find(s=>s.minute===defaultSlot(slotsFor(0,e))).recent,
          eYest:defaultSlot(slotsFor(-1,e)), day:isoDayAt(-2,now)}));
        """)
        self.assertEqual(r["n"], 48)
        self.assertEqual(r["yDef"], 23 * 60 + 30)
        self.assertEqual(r["y2330"], {"minute": 1410, "time": "2026-10-17T23:30:00Z", "utc": "23:30", "peru": "18:30",
                                      "future": False, "recent": False})
        self.assertEqual(r["tDef"], 12 * 60 + 30)  # 12:30 is the last interval at least 6 h old at 18:47
        self.assertEqual(r["tFuture"], "19:00")
        self.assertEqual(r["tRecent"][0], "13:00")
        # Early in the UTC day: today has only recent intervals, flagged as such; never a future one.
        self.assertEqual(r["eToday"], 3 * 60)
        self.assertTrue(r["eTodayRecent"])
        self.assertEqual(r["eYest"], 21 * 60)
        self.assertEqual(r["day"], "2026-10-16")

    def check_full_datetime_format_for_every_slot(self):
        r = self.run_js("process.stdout.write(JSON.stringify(slotsFor(-1,Date.parse('2026-01-01T00:10:00Z')).map(s=>s.time)));")
        self.assertTrue(all(re.fullmatch(r"2025-12-31T\d\d:[03]0:00Z", t) for t in r), r[:3])


def _browser():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(args=["--no-proxy-server"]).close()
        return True
    except Exception:  # noqa: BLE001
        return False


VIEWPORTS = {"desktop": dict(width=1280, height=900), "mobile": dict(width=390, height=844)}


@unittest.skipUnless(_browser(), "Playwright/Chromium not installed")
class InBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Q(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=str(ROOT / "site")))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.origin = f"http://127.0.0.1:{cls.srv.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def open(self, p, viewport, gibs="ok"):
        """gibs: 'ok' serves every tile, 'fail' aborts every tile, 'partial' aborts every other IMERG tile."""
        leaf = os.environ.get("IRFEN_LEAFLET_DIR")
        seen = {"imerg": [], "viirs": [], "n": 0}

        def route(r, *_):
            u = r.request.url
            if leaf and "unpkg.com/leaflet@1.9.4/dist/" in u:
                return r.fulfill(path=str(Path(leaf) / u.rsplit("/dist/", 1)[1]))
            if "gibs.earthdata.nasa.gov" in u:
                q = parse_qs(urlparse(u).query)
                layer = (q.get("layers") or q.get("LAYERS") or [""])[0]
                time = (q.get("time") or q.get("TIME") or [""])[0]
                if "IMERG" in layer:
                    seen["imerg"].append(time)
                    seen["n"] += 1
                    if gibs == "fail" or (gibs == "partial" and seen["n"] % 2 == 0):
                        return r.abort()
                else:
                    seen["viirs"].append(time)
                return r.fulfill(status=200, content_type="image/png", body=PNG)
            if "tile.openstreetmap.org" in u:
                return r.fulfill(status=200, content_type="image/png", body=PNG)
            return r.continue_() if (u.startswith(self.origin) or "unpkg.com/leaflet@1.9.4/" in u) else r.abort()

        b = p.chromium.launch(args=["--no-proxy-server"])
        page = b.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", route)
        page.goto(self.origin + "index.html", wait_until="networkidle")
        if not page.evaluate("typeof L !== 'undefined'"):
            b.close()
            self.skipTest("Leaflet 1.9.4 not reachable (set IRFEN_LEAFLET_DIR to a local build)")
        # DOM click: on narrow screens the tab bar can still be settling, and the tab is already the default one.
        page.evaluate("document.querySelector('.tab[data-tab=\"territorial-inventory\"]').click()")
        page.wait_for_function("document.querySelectorAll('#ti-map .leaflet-overlay-pane path').length > 0", timeout=20000)
        return b, page, errors, seen

    W = '#territorial-inventory [data-iw="{}"]'

    @staticmethod
    def tap(page, selector):
        """DOM click on the real element (same handlers as a user click). Avoids Playwright's frame-stability
        heuristic, which intermittently timed out in a loaded container although positions were stable."""
        page.evaluate("s => { const e = document.querySelector(s); e.scrollIntoView({block: 'center'}); e.click(); }", selector)

    @staticmethod
    def set_checked(page, selector, on):
        page.evaluate("([s, on]) => { const e = document.querySelector(s); if (e.checked !== on) e.click(); }", [selector, on])

    @staticmethod
    def until(page, cond, timeout_ms=15000):
        """Poll a Python-side condition (e.g. on intercepted requests) instead of sleeping a fixed time."""
        for _ in range(timeout_ms // 100):
            if cond():
                return True
            page.wait_for_timeout(100)
        return cond()

    def rain_on(self, page):
        self.tap(page, self.W.format("toggle"))
        self.set_checked(page, self.W.format("rain"), True)
        page.wait_for_function(f"!['CARGANDO','APAGADA'].includes(document.querySelector('{self.W.format('rain-pill')}').textContent)", timeout=15000)
        return page.inner_text(self.W.format("rain-pill")), page.inner_text(self.W.format("status"))

    def test_panels_closed_by_default_switches_still_drive_the_map(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            for tag, vp in VIEWPORTS.items():
                with self.subTest(viewport=tag):
                    b, page, errors, _ = self.open(p, vp)
                    self.assertTrue(page.evaluate("document.getElementById('ti-layers-panel').hidden"))
                    self.assertTrue(page.evaluate("[...document.querySelectorAll('#territorial-inventory [data-iw=\"panel\"]')].every(p => p.hidden)"))
                    self.assertFalse(page.evaluate("document.getElementById('ti-context').open"))
                    # No horizontal page scroll; the map is the widest block of the section.
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), vp["width"])
                    paths = lambda: page.evaluate("document.querySelectorAll('#ti-map .leaflet-overlay-pane path').length")
                    n_all = paths()
                    self.tap(page, "#ti-layers-btn")
                    box = page.query_selector("#ti-layers-panel").bounding_box()
                    self.assertLessEqual(box["x"] + box["width"], vp["width"])
                    self.tap(page, '[data-ti-all-layers="off"]')
                    self.assertEqual((paths(), page.inner_text("#ti-layers-count")), (0, "0/8"))
                    self.tap(page, '[data-ti-all-layers="on"]')
                    self.assertEqual(paths(), n_all)
                    self.set_checked(page, '[data-ti-layer="catchment"]', False)
                    self.assertLess(paths(), n_all)
                    self.assertEqual(page.inner_text("#ti-layers-count"), "7/8")
                    self.set_checked(page, '[data-ti-layer="catchment"]', True)
                    # Opening «Meteorología» folds «Capas»: one panel at a time over the map.
                    self.tap(page, self.W.format("toggle"))
                    self.assertTrue(page.evaluate("document.getElementById('ti-layers-panel').hidden"))
                    box = page.query_selector(self.W.format("panel")).bounding_box()
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertLessEqual(box["x"] + box["width"], vp["width"])
                    page.keyboard.press("Escape")
                    self.assertTrue(page.evaluate(f"document.querySelector('{self.W.format('panel')}').hidden"))
                    self.assertEqual(errors, [])
                    b.close()
        # Recorded node ID (pytest collection manifest): the related browser checks run here as sub-tests.
        for check in (self.check_weather_states_follow_the_tiles_and_the_requested_interval,
                      self.check_time_selector_changes_the_request_and_viirs_stays_daily,
                      self.check_recent_strip_is_compact_and_selects_the_record):
            with self.subTest(check=check.__name__):
                check()

    def check_weather_states_follow_the_tiles_and_the_requested_interval(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            for tag, vp in VIEWPORTS.items():
                for gibs, pill in (("ok", "ACTIVA"), ("partial", "PARCIAL"), ("fail", "SIN MOSAICOS")):
                    with self.subTest(viewport=tag, gibs=gibs):
                        b, page, errors, seen = self.open(p, vp, gibs)
                        got, status = self.rain_on(page)
                        page.wait_for_timeout(300)  # a late 'load' must not overwrite the verdict
                        self.assertEqual(page.inner_text(self.W.format("rain-pill")), pill, status)
                        self.assertTrue(seen["imerg"])
                        self.assertTrue(all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:[03]0:00Z", t) for t in seen["imerg"]), seen["imerg"][:3])
                        status = page.inner_text(self.W.format("status"))
                        low = status.lower()
                        # Absence of tiles (or an empty tile) is never presented as absence of rain.
                        self.assertRegex(low, r"no (equivale|significa) a?\s?ausencia de lluvia")
                        for claim in ("no hay precipitación", "sin lluvia", "no hay lluvia", "disponible"):
                            self.assertNotIn(claim, low)
                        if gibs == "ok":
                            self.assertIn("Recibir mosaicos no confirma que haya datos de ese intervalo", status)
                        else:
                            self.assertNotIn("mosaicos recibidos", status)
                        # The closed button names the requested interval (desktop; on mobile it is in the panel only).
                        tag_text = page.text_content(self.W.format("time-tag"))
                        self.assertRegex(tag_text, r"^\d\d:[03]0 UTC$")
                        self.assertEqual(seen["imerg"][-1][11:16] + " UTC", tag_text)
                        self.assertEqual(page.is_visible(self.W.format("time-tag")), tag == "desktop")
                        # The two map buttons never overlap, whatever the state text.
                        a = page.query_selector("#ti-layers-btn").bounding_box()
                        w = page.query_selector(self.W.format("toggle")).bounding_box()
                        self.assertLessEqual(a["x"] + a["width"], w["x"], (a, w))
                        self.assertEqual(errors, [])
                        b.close()

    def check_time_selector_changes_the_request_and_viirs_stays_daily(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b, page, errors, seen = self.open(p, VIEWPORTS["desktop"])
            self.rain_on(page)
            first = seen["imerg"][-1]
            page.select_option(self.W.format("slot"), "720")
            page.wait_for_function(f"document.querySelector('{self.W.format('time-tag')}').textContent==='12:00 UTC'")
            self.assertTrue(self.until(page, lambda: seen["imerg"][-1].endswith("T12:00:00Z")), seen["imerg"][-1])
            self.assertEqual(seen["imerg"][-1][:10], first[:10])
            page.select_option(self.W.format("day"), "-2")
            self.assertTrue(self.until(page, lambda: seen["imerg"][-1][:10] < first[:10]), seen["imerg"][-1])
            self.set_checked(page, self.W.format("clouds"), True)
            self.until(page, lambda: bool(seen["viirs"]))
            self.assertTrue(seen["viirs"] and all(re.fullmatch(r"\d{4}-\d\d-\d\d", t) for t in seen["viirs"]), seen["viirs"][:3])
            # A recent interval (< 6 h) is flagged and never presented as published, whatever the tiles do.
            page.select_option(self.W.format("day"), "0")
            recent = page.evaluate(f"[...document.querySelector('{self.W.format('slot')}').options].filter(o=>!o.disabled&&o.textContent.includes('<6 h')).map(o=>o.value)")
            if recent:
                page.select_option(self.W.format("slot"), recent[-1])
                page.wait_for_function(f"document.querySelector('{self.W.format('rain-pill')}').textContent==='ACTIVA'")
                self.assertIn("puede no estar publicado todavía", page.inner_text(self.W.format("status")))
            # The labels are UTC and PET (Peru, UTC-5), never a claim of availability.
            labels = page.evaluate(f"[...document.querySelector('{self.W.format('slot')}').options].map(o=>o.textContent)")
            self.assertTrue(all(re.fullmatch(r"\d\d:[03]0 UTC · \d\d:[03]0 PET( · futuro| · <6 h)?", x) for x in labels), labels[:4])
            # Future intervals of today cannot be chosen.
            page.select_option(self.W.format("day"), "0")
            disabled = page.evaluate(f"[...document.querySelector('{self.W.format('slot')}').options].filter(o=>o.disabled).map(o=>o.value)")
            selected = page.evaluate(f"document.querySelector('{self.W.format('slot')}').value")
            self.assertNotIn(selected, disabled)
            self.assertEqual(errors, [])
            b.close()

    def check_recent_strip_is_compact_and_selects_the_record(self):
        from playwright.sync_api import sync_playwright

        is_open = "document.getElementById('ti-recent-box').open"
        with sync_playwright() as p:
            for tag, vp in VIEWPORTS.items():
                with self.subTest(viewport=tag):
                    b, page, errors, _ = self.open(p, vp)
                    page.wait_for_selector("#ti-recent .ti-recent-card", state="attached")
                    self.assertEqual(page.evaluate("document.querySelectorAll('#ti-recent .ti-recent-card').length"), 3)
                    summary_visible = page.is_visible("#ti-recent-box > summary")
                    map_top = page.evaluate("document.getElementById('ti-map').getBoundingClientRect().top - "
                                            "document.getElementById('territorial-inventory').getBoundingClientRect().top")
                    if tag == "mobile":
                        # Folded at first on narrow screens: one summary line, the map starts higher.
                        self.assertFalse(page.evaluate(is_open))
                        self.assertTrue(summary_visible)
                        self.assertFalse(page.is_visible("#ti-recent .ti-recent-card"))
                        self.assertLess(map_top, 430, map_top)  # 516 px with the strip open (sprint 18-10)
                        self.tap(page, "#ti-recent-box > summary")
                        self.assertTrue(page.evaluate(is_open))
                    else:
                        # Desktop: compact strip, always open, no extra summary line.
                        self.assertTrue(page.evaluate(is_open))
                        self.assertFalse(summary_visible)
                    self.assertTrue(page.is_visible("#ti-recent .ti-recent-card"))
                    h = page.evaluate("document.getElementById('ti-recent').getBoundingClientRect().height")
                    # Before: «Ver avances recientes» unfolded the whole summary (≈330 px desktop, ≈815 px mobile).
                    self.assertLess(h, 190, f"recent strip too tall on {tag}: {h}")
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), vp["width"])
                    self.tap(page, "#ti-recent .ti-recent-card")
                    detail = page.inner_text("#ti-detail")
                    self.assertIn("Avance integrado", detail)
                    self.assertIn("No representa riesgo, inundación ni alerta.", detail)
                    self.assertTrue(any(note in detail for note in (
                        "Quitasol/Paracas siguen sin geometría local ni outlet", "San Agustín sigue como componente local",
                        "Palpa/Changuillo conserva tramos locales")), detail)
                    # The full inventory summary stays reachable (folded, one click away).
                    self.assertFalse(page.evaluate("document.getElementById('ti-context').open"))
                    self.tap(page, "#ti-context > summary")
                    self.assertTrue(page.evaluate("document.getElementById('ti-context').open"))
                    self.assertGreater(len(page.inner_text("#ti-summary")), 40)
                    # «Ver avances recientes» filters the list and unfolds the strip (mobile too).
                    if tag == "mobile":
                        self.tap(page, "#ti-recent-box > summary")
                        self.assertFalse(page.evaluate(is_open))
                    self.tap(page, "#ti-recent-btn")
                    self.assertEqual(page.evaluate("document.getElementById('ti-filter').value"), "recent")
                    self.assertTrue(page.evaluate(is_open))
                    self.assertEqual(errors, [])
                    b.close()

if __name__ == "__main__":
    unittest.main()
