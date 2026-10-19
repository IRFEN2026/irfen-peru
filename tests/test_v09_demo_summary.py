"""IRFEN v0.9 private demo (15-10-2026): plain-language summary, per-source freshness (available / delayed / absent),
avisos described with their natural scope, and selva-only avisos shown apart on Pacific basins. Presentation only:
the internal priority rule (SHARED-RULES) and the bundle guards are unchanged, and the Pages gate still excludes v0.9.

The helpers run with node on the committed bundle; the page runs in Chromium on a SYNTHETIC bundle anchored on T0
(skipped where Playwright/Chromium are missing; the v09 browser workflow has them).
"""
import copy
import functools
import http.server
import importlib.util
import json
import shutil
import subprocess
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "site/v09/index.html").read_text(encoding="utf-8")
BUNDLE = json.loads((ROOT / "site/data/v09/dashboard_v0_1.json").read_text(encoding="utf-8"))
NODE = shutil.which("node")
HELPERS = HTML[HTML.index("/* DEMO-HELPERS-BEGIN"):HTML.index("/* DEMO-HELPERS-END */")]
T0 = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
BASIN = "lalibertad_chaman"

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as _p:
        _p.chromium.launch(args=["--no-proxy-server"]).close()
    BROWSER = True
except Exception:  # noqa: BLE001
    BROWSER = False


def node(js: str, payload) -> object:
    out = subprocess.run([NODE, "-e", HELPERS + "\nconst input=JSON.parse(require('fs').readFileSync(0,'utf8'));\n" + js],
                         input=json.dumps(payload), capture_output=True, text=True, check=True, timeout=60)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node not installed")
class Helpers(unittest.TestCase):
    def test_scope_from_phenomenon_or_description_sections(self):
        cases = [dict(phenomenon="LLUVIA EN LA SELVA - DÉCIMO SEGUNDO FRIAJE"), dict(phenomenon="PRECIPITACIONES EN LA SIERRA NORTE Y COSTA NORTE"),
                 dict(phenomenon="Lluvias intensas (aviso de corto plazo, 24 h)", description="SELVA: lluvias. SIERRA: precipitaciones. COSTA: lluvias aisladas."),
                 dict(phenomenon="Posible activación de quebradas (aviso de corto plazo, 24 h)", description=""),
                 dict(phenomenon="DESCENSO DE TEMPERATURA DIURNA EN LA SELVA CENTRO Y SUR"), dict(phenomenon="INCREMENTO DE VIENTO EN LA COSTA")]
        got = node("process.stdout.write(JSON.stringify(input.map(a=>avisoScope(a))))", cases)
        self.assertEqual([g["selvaOnly"] for g in got], [True, False, False, False, True, False])
        self.assertEqual(got[2]["regions"], ["COSTA", "SIERRA", "SELVA"])
        self.assertEqual(got[3]["basis"], "NOT_STATED")  # unknown scope is never treated as "not applicable"

    def test_scope_never_hides_a_coastal_rain_aviso_in_the_committed_bundle(self):
        got = node("process.stdout.write(JSON.stringify(input.map(a=>[a.aviso_key,a.phenomenon,avisoScope(a)])))", BUNDLE["avisos"])
        for key, phenomenon, sc in got:
            if sc["selvaOnly"]:
                self.assertIn("SELVA", phenomenon.upper(), key)
                self.assertNotRegex(phenomenon.upper(), r"\b(COSTA|SIERRA)\b", key)

    def test_freshness_states(self):
        got = node("process.stdout.write(JSON.stringify(input.map(([t,n,l])=>freshnessState(t,n,l).state)))",
                   [["2026-10-15T10:00:00Z", 1792065600000, 180], ["2026-10-15T00:00:00Z", 1792065600000, 180], [None, 1792065600000, 180], ["no-date", 0, 1]])
        self.assertEqual(got, ["DISPONIBLE", "RETRASADA", "AUSENTE", "AUSENTE"])


class Contract(unittest.TestCase):
    def test_labels_and_no_alert_semantics(self):
        for flag in ("RESEARCH_ONLY", "TEST_ONLY", "DEMO PRIVADA · NO PUBLICADA", "NO ES UN SISTEMA DE ALERTA"):
            self.assertIn(f'<span class="flag">{flag}</span>', HTML)
        self.assertIn('id="summary"', HTML)
        for forbidden in ("fetch(", "Date.now(", "document.", "window."):
            self.assertNotIn(forbidden, HELPERS)

    def test_rule_and_guards_unchanged(self):
        spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts/v09_pages_publication_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        cfg = json.loads((ROOT / "config/v09_public_demo_v0_1.json").read_text(encoding="utf-8"))
        self.assertIs(cfg["publish_v09_dashboard"], False)
        self.assertFalse(gate.decide(cfg, BUNDLE)[0], "the Pages gate must keep v0.9 out")
        for k, v in dict(production_use=False, operational_alerting_enabled=False, activation_gate="BLOCKED",
                         missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None).items():
            self.assertEqual(BUNDLE[k], v, k)
        shared = HTML[HTML.index("/* SHARED-RULES-BEGIN"):HTML.index("/* SHARED-RULES-END */")]
        self.assertNotIn("avisoScope", shared, "presentation helpers must not enter the shared priority rule")


def fixture() -> dict:
    """SYNTHETIC bundle: real structure, times on T0; one coastal rain aviso and one selva-only aviso on a basin."""
    d = copy.deepcopy(BUNDLE)
    iso = lambda t: t.isoformat().replace("+00:00", "Z")
    d["built_at_utc"] = iso(T0 - timedelta(minutes=5))
    d["source"]["health"] = dict(state="AL_DIA", last_check_utc=iso(T0 - timedelta(minutes=10)), last_successful_check_utc=iso(T0 - timedelta(minutes=10)))
    d["source"]["viewer_stale_after_minutes"] = 180
    base = dict(product="AVISO-METEOROLOGICO", rain_related=True, validity_start=iso(T0 - timedelta(hours=3)), validity_end=iso(T0 + timedelta(hours=20)),
                validity_text="SINTÉTICO", official_level=None, departments=["LA LIBERTAD"], provinces_by_department=None, stored_status="VIGENTE",
                status_history=[], revisions=[], documents=[])
    coast = dict(base, aviso_key="SYNTH-COSTA", aviso_number="SINT-1", phenomenon="PRECIPITACIONES EN LA SIERRA NORTE Y COSTA NORTE")
    selva = dict(base, aviso_key="SYNTH-SELVA", aviso_number="SINT-2", phenomenon="LLUVIA EN LA SELVA - FRIAJE SINTÉTICO")
    d["avisos"] = [coast, selva]
    d["events"] = []
    for z in d["rain"]["zones"]:
        z["avisos"] = []
        z["imerg"] = dict(source="SYNTHETIC", windows={}, series_24h_half_hourly_mm=[], window_end_utc=None)
        z["goes19"] = dict(status="NO_DISPONIBLE", reason="SINTÉTICO")
        z["geos_cf"] = dict(status="NO_DISPONIBLE", reason="SINTÉTICO")
        if z["zone_id"] == BASIN:
            z["avisos"] = [dict(aviso_key=a["aviso_key"], status="VIGENTE", product=a["product"], official_level=None,
                                relation_method="BASIN_INTERSECTS_LISTED_DEPARTMENT", validity_start=a["validity_start"], validity_end=a["validity_end"])
                           for a in (coast, selva)]
            end = T0 - timedelta(hours=2)
            z["imerg"] = dict(source="SYNTHETIC", window_end_utc=iso(end), series_24h_half_hourly_mm=[],
                              windows={k: dict(status="CALCULADO", accum_mm=0.0, end_utc=iso(end)) for k in ("1h", "3h", "6h", "24h")})
    return d


@unittest.skipUnless(BROWSER, "Playwright/Chromium not installed; runs in workflow v09-dashboard-browser-test.yml")
class DemoInBrowser(unittest.TestCase):
    def test_summary_freshness_and_scope_grouping(self):
        bundle = fixture()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "site")))
        srv.RequestHandlerClass.log_message = lambda *a: None
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{srv.server_port}/"

        def route(r):
            if not r.request.url.startswith(origin):
                return r.abort()
            if r.request.url.endswith("/data/v09/dashboard_v0_1.json"):
                return r.fulfill(status=200, content_type="application/json", body=json.dumps(bundle))
            return r.continue_()

        try:
            with sync_playwright() as p:
                b = p.chromium.launch(args=["--no-proxy-server"])
                page = b.new_page(viewport=dict(width=1280, height=1400))
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", route)
                page.clock.install(time=T0)
                page.goto(origin + "v09/index.html")
                page.wait_for_selector("#summary li")
                summary = page.inner_text("#summary")
                self.assertIn("Resumen en lenguaje sencillo", summary)
                self.assertIn("1 vigente(s) o próximo(s) relacionados con las zonas del norte (n.º SINT-1 · precipitaciones en la sierra norte y costa norte)", summary)
                self.assertIn("1 aviso(s) para la selva (n.º SINT-2 · lluvia en la selva - friaje sintético)", summary)
                self.assertIn("calculable ahora en 1 de", summary)
                states = page.eval_on_selector_all("[data-fresh]", "els => els.map(e => e.dataset.fresh)")
                self.assertEqual(states, ["DISPONIBLE", "DISPONIBLE", "AUSENTE", "AUSENTE"])
                page.evaluate("id => selectZone(id, true)", BASIN)
                detail = page.inner_text("#zone-detail")
                main_block = detail.split("Otros avisos relacionados")[0]
                self.assertIn("SINT-1", main_block)
                self.assertNotIn("SINT-2", main_block, "a selva-only aviso is not presented as specific to a Pacific basin")
                self.assertIn("Otros avisos relacionados, con ámbito distinto (1)", detail)
                self.assertIn("Las quebradas del inventario documental", page.inner_text("#legend"))
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
