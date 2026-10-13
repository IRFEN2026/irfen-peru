"""IRFEN v0.9 dashboard in a real browser with a simulated clock, without reloading the page.

The committed bundle is copied and its times are replaced by SYNTHETIC values anchored on T0 (they exercise the
rules; they are not observations). The browser clock is installed at T0 and moved forward with Playwright; the page
must re-evaluate on its own:

* INDECI/COEN source: AL_DIA until 180 min after the last check, DESACTUALIZADA after;
* GOES-19 (> 90 min), IMERG Early (> 12 h) tagged as old data and no longer counted for the priority;
* GEOS-CF cycle older than 48 h: no sums;
* aviso past its documented end: VENCIDO, and the internal priority follows;
* periodic re-download: a failed download keeps the data and says so, the event tray neither duplicates nor drops
  events, an older bundle is rejected.

Runs where Playwright and Chromium are installed (workflow v09-dashboard-browser-test.yml); skipped elsewhere.
"""
import copy
import functools
import http.server
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test and demo output clean
        pass
BUNDLE = ROOT / "site/data/v09/dashboard_v0_1.json"
ZONE = "tumbes_province_context:ZARUMILLA"
T0 = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as _p:
        _b = _p.chromium.launch(args=["--no-proxy-server"])
        _b.close()
    BROWSER = True
except Exception:  # noqa: BLE001 - playwright or chromium missing
    BROWSER = False


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def event(n, minutes):
    return dict(event="AVISO_NEW", observed_at_utc=iso(T0 - timedelta(minutes=minutes)), aviso_key=f"SYNTH-EVENT-{n}",
                requires_human_review=True, detail=[f"SYNTHETIC event {n}"])


def fixture() -> dict:
    """SYNTHETIC bundle: real structure, times anchored on T0."""
    d = copy.deepcopy(json.loads(BUNDLE.read_text(encoding="utf-8")))
    d["built_at_utc"] = iso(T0 - timedelta(minutes=5))
    d["source"]["health"] = dict(state="AL_DIA", last_check_utc=iso(T0 - timedelta(minutes=10)),
                                 last_successful_check_utc=iso(T0 - timedelta(minutes=10)))
    d["source"]["viewer_stale_after_minutes"] = 180
    aviso = dict(aviso_key="SYNTH-AVISO-1", product="AVISO-METEOROLOGICO", aviso_number="SINTÉTICO", phenomenon="AVISO SINTÉTICO DE PRUEBA",
                 rain_related=True, validity_start=iso(T0 - timedelta(hours=20)), validity_end=iso(T0 + timedelta(hours=2)),
                 validity_text="SINTÉTICO", official_level="AMARILLO", official_level_source="SYNTHETIC", departments=["TUMBES"],
                 provinces_by_department=None, stored_status="VIGENTE", status_history=[], revisions=[], documents=[])
    d["avisos"] = [aviso]
    d["events"] = [event(1, 300), event(2, 200), event(3, 100)]
    for z in d["rain"]["zones"]:
        if z["zone_id"] != ZONE:
            continue
        end = T0 - timedelta(hours=5)
        z["avisos"] = [dict(aviso_key="SYNTH-AVISO-1", status="VIGENTE", product="AVISO-METEOROLOGICO", official_level="AMARILLO",
                            relation_method="DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN",
                            validity_start=aviso["validity_start"], validity_end=aviso["validity_end"])]
        z["imerg"] = dict(source="SYNTHETIC", window_end_utc=iso(end), latest_granule_start_utc=iso(end - timedelta(minutes=30)),
                          series_24h_half_hourly_mm=[],
                          windows={k: dict(status="CALCULADO", accum_mm=v, end_utc=iso(end)) for k, v in
                                   (("1h", 0.2), ("3h", 0.6), ("6h", 1.2), ("24h", 2.4))})
        z["goes19"] = dict(status="CALCULADO", source="SYNTHETIC", rate_mean_mm_h=0.1, rate_max_mm_h=0.4,
                           scan_end_utc=iso(T0 - timedelta(minutes=10)), good_quality_pixels=189, window_pixels=189, recent_scans_mm_h=[])
        z["geos_cf"] = dict(status="CALCULADO", source="SYNTHETIC", dataset_time_start=iso(T0 - timedelta(hours=30)),
                            resolution_note="SINTÉTICO", hourly=[dict(valid_time_utc=iso(T0 + timedelta(minutes=30) + timedelta(hours=k)), precip_mm=0.25)
                                                                for k in range(96)])
        z["percentile"] = dict(status="NO_DISPONIBLE")
    return d


@unittest.skipUnless(BROWSER, "Playwright/Chromium not installed; runs in workflow v09-dashboard-browser-test.yml")
class LiveDashboard(unittest.TestCase):
    def test_states_age_with_the_clock_and_refresh_keeps_history(self):
        base = fixture()
        served = dict(mode="ok", bundle=base, hits=0)
        handler = functools.partial(QuietHandler, directory=str(ROOT / "site"))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{srv.server_port}/"

        def route(r):
            url = r.request.url
            if not url.startswith(origin):
                return r.abort()
            if url.endswith("/data/v09/dashboard_v0_1.json"):
                served["hits"] += 1
                if served["mode"] == "fail":
                    return r.fulfill(status=500, body="error")
                return r.fulfill(status=200, content_type="application/json", body=json.dumps(served["bundle"]))
            return r.continue_()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(args=["--no-proxy-server"])
                page = browser.new_page(viewport=dict(width=1280, height=1400))
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", route)
                page.clock.install(time=T0)
                page.goto(origin + "v09/index.html")
                page.wait_for_selector("#zone-detail h2")
                page.evaluate("window.__noReload = 'same-page'")
                page.evaluate("id => selectZone(id, true)", ZONE)

                def at(minutes):
                    """Move the browser clock to T0 + minutes; due timers (60 s re-evaluation, 5 min refresh) fire."""
                    target = T0 + timedelta(minutes=minutes)
                    now_ms = page.evaluate("Date.now()")
                    page.clock.fast_forward(int(target.timestamp() * 1000) - now_ms)
                    page.evaluate("renderAll()")  # identical to what the 60 s timer does; makes the assertion point explicit

                chip = lambda: page.get_attribute("#source-chip", "data-state")
                prio = lambda: page.inner_text("#zone-detail .prio")
                detail = lambda: page.inner_text("#zone-detail")
                block = lambda title: page.locator("#zone-detail .block").filter(has=page.locator("h3", has_text=title)).inner_text()
                aviso_status = lambda: page.evaluate("""() => [...document.querySelectorAll('#avisos-table tr')]
                    .filter(tr => tr.textContent.includes('SINTÉTICO')).map(tr => tr.querySelector('.status').textContent)[0]""")
                page.evaluate("() => { document.getElementById('aviso-filter').value = 'all'; drawAvisos(); }")

                # T0: everything fresh
                self.assertEqual(chip(), "AL_DIA")
                self.assertEqual(prio(), "Vigilancia activa")
                self.assertNotIn("Dato antiguo", block("IMERG"))
                self.assertNotIn("Dato antiguo", block("GOES-19"))
                self.assertIn("1.5 mm", block("GEOS-CF"))  # 6 consecutive hours x 0.25 mm
                self.assertEqual(aviso_status(), "VIGENTE")

                # +100 min: GOES-19 scan is 110 min old (> 90): old data, not counted
                at(100)
                self.assertIn("Dato antiguo", block("GOES-19"))
                self.assertNotIn("Dato antiguo", block("IMERG"))
                self.assertEqual(chip(), "AL_DIA")

                # +2 h 45: 175 min since the last capture -> still AL_DIA; aviso ended at +2 h -> VENCIDO
                at(165)
                self.assertEqual(chip(), "AL_DIA")
                self.assertEqual(aviso_status(), "VENCIDO")
                self.assertEqual(prio(), "Seguimiento por lluvia observada")  # aviso expired; fresh IMERG rain

                # +2 h 55: 185 min without a capture -> DESACTUALIZADA, with no reload
                at(175)
                self.assertEqual(chip(), "DESACTUALIZADA")
                self.assertIn("puede haber avisos no capturados", page.inner_text("#chips"))

                # +7 h 05: IMERG window ended 12 h 05 ago -> old data; nothing usable -> Datos insuficientes
                at(425)
                self.assertIn("Dato antiguo", block("IMERG"))
                self.assertEqual(prio(), "Datos insuficientes")

                # +18 h 05: GEOS-CF cycle started 48 h 05 ago -> no sums
                at(1085)
                self.assertIn("desactualizado", block("GEOS-CF"))
                self.assertNotIn("Próximas 6 h", block("GEOS-CF"))

                # failed re-download: data kept, failure shown, events not lost or duplicated
                rows = lambda: page.evaluate("document.querySelectorAll('#events-table tr').length") - 1
                self.assertEqual(rows(), 3)
                served["mode"] = "fail"
                page.evaluate("refresh()")
                page.wait_for_function("document.getElementById('refresh-chip').dataset.ok === 'false'", polling=100)
                self.assertIn("Se mantienen los datos", page.inner_text("#chips"))
                self.assertIn("Tumbes · Zarumilla", detail())
                self.assertEqual(rows(), 3)

                # new bundle carrying only its last events (E1, E2 dropped, E3 repeated, E4 new): 4 rows, no duplicate
                newer = copy.deepcopy(base)
                newer["built_at_utc"] = iso(T0 + timedelta(hours=18))
                newer["events"] = [event(3, 100), event(4, -1000)]
                served.update(mode="ok", bundle=newer)
                page.evaluate("refresh()")
                page.wait_for_function("document.getElementById('refresh-chip').dataset.ok === 'true'", polling=100)
                self.assertEqual(rows(), 4)
                texts = page.text_content("#events-table")
                for n in (1, 2, 3, 4):
                    self.assertEqual(texts.count(f"SYNTH-EVENT-{n}"), 1)

                # an older bundle is rejected; the newer data stays
                older = copy.deepcopy(base)
                older["built_at_utc"] = iso(T0 - timedelta(hours=1))
                served.update(bundle=older)
                page.evaluate("refresh()")
                page.wait_for_function("document.getElementById('refresh-chip').dataset.ok === 'false'", polling=100)
                self.assertIn("más antiguo", page.inner_text("#chips"))
                self.assertEqual(rows(), 4)

                # a bundle with an altered guard is rejected
                bad = copy.deepcopy(newer)
                bad["built_at_utc"] = iso(T0 + timedelta(hours=19))
                bad["operational_alerting_enabled"] = True
                served.update(bundle=bad)
                page.evaluate("refresh()")
                page.wait_for_function("document.getElementById('refresh-chip').innerText.includes('guarda')", polling=100)

                # periodic refresh really runs on its own timer
                hits = served["hits"]
                served.update(bundle=newer)
                page.clock.fast_forward(5 * 60 * 1000 + 1000)
                page.wait_for_function("document.getElementById('refresh-chip').dataset.ok === 'true'", polling=100)
                self.assertGreater(served["hits"], hits)

                self.assertEqual(page.evaluate("window.__noReload"), "same-page")
                self.assertEqual(errors, [])
                browser.close()
        finally:
            srv.shutdown()


class StaticChecks(unittest.TestCase):
    def test_refresh_contract_in_page(self):
        html = (ROOT / "site/v09/index.html").read_text(encoding="utf-8")
        self.assertIn("REFRESH_MS = 5 * 60 * 1000, TICK_MS = 60 * 1000", html)
        self.assertIn("setInterval(refresh, REFRESH_MS)", html)
        self.assertIn("setInterval(renderAll, TICK_MS)", html)
        self.assertIn("eventHistory", html)
        self.assertEqual(html.count("addEventListener(\"change\""), 1)  # listeners bound once, not per render
        self.assertNotIn("location.reload", html)

    def test_browser_workflow_runs_this_test(self):
        wf = (ROOT / ".github/workflows/v09-dashboard-browser-test.yml").read_text(encoding="utf-8")
        self.assertIn("tests/test_v09_dashboard_browser.py", wf)
        self.assertIn("playwright install", wf)
        self.assertIn("contents: read", wf)
        self.assertNotIn("contents: write", wf)


if __name__ == "__main__":
    unittest.main()
