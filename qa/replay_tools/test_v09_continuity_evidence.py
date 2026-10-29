"""Regression checks for the private v0.9 map: IMERG 24 h coverage is verified, never trusted, and no lack of evidence
is ever shown as a satisfactory (green) state. RESEARCH_ONLY / TEST_ONLY.

No network, no publication, no workflow activation. The coverage logic is executed with node exactly as written in
site/v09/index.html; the backend agreement test feeds it real output of scripts/v09_zone_rain_engine.py; the browser test
(Playwright) loads the page with synthetic bundles and reads what is rendered.
Kept outside tests/ on purpose so the ratcheted pytest collection manifest is not touched (see the PR description).
"""
import copy
import http.server
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "site/v09/index.html"
BUNDLE = ROOT / "site/data/v09/dashboard_v0_1.json"
END = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
GUARDS = {"deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
          "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
          "decision_thresholds": None, "hydraulic_factors": None}


def slots(n, end=END, minutes=30):
    return [(end - timedelta(minutes=minutes * (n - k))).isoformat() for k in range(n)]


def imerg(series, available=None, required=48, end=END, source="IMERG_EARLY_V09_NORTH_CONTINUOUS", missing=None, window_slots=48):
    """A zone's IMERG block shaped like the engine output. By default the declared coverage is coherent with the series,
    as the engine writes it: available = valid values, missing = every window slot without a valid value (empty when the
    series is empty). `available`, `required` and `missing` can be overridden to build contradictions."""
    good = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0  # noqa: E731
    valid_at = {datetime.fromisoformat(t.replace("Z", "+00:00")) for t, v in series
                if isinstance(t, str) and _parses(t) and good(v)}
    derived = [] if not series else [t for t in slots(window_slots, end) if datetime.fromisoformat(t) not in valid_at]
    return {"source": source, "window_end_utc": end.isoformat(), "series_24h_half_hourly_mm": series,
            "coverage_24h": {"required_half_hours": required,
                             "available_half_hours": sum(1 for _, v in series if good(v)) if available is None else available,
                             "missing_half_hours_utc": derived if missing is None else missing}}


def _parses(t):
    try:
        datetime.fromisoformat(t.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def coverage_js():
    src = MAP.read_text(encoding="utf-8")
    start = src.index("const IMERG_SLOT_MIN")
    end = src.index("const COVERAGE_UI")
    return src[start:end]


def run_js(cases_js):
    """cases_js assigns `out` (any JSON-serialisable value) using the page's own functions."""
    script = coverage_js() + "\n" + cases_js + "\nprocess.stdout.write(JSON.stringify(out));"
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    if res.returncode != 0:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


def states(blocks, window_min=24 * 60):
    return run_js(f"const out = {json.dumps(blocks)}.map(b => imergCoverageState(b, {window_min}, 30));")


class Presentation(unittest.TestCase):
    def test_presentation_is_research_only_and_explains_provenance(self):
        src = MAP.read_text(encoding="utf-8")
        for token in ("DEMO PRIVADA · NO PUBLICADA", "RESEARCH_ONLY", "TEST_ONLY", 'id="continuity-chips"', "renderContinuityEvidence();",
                      "coverageLine(z.imerg)", "NO mide la puntualidad de GitHub Actions", "nunca lluvia cero ni riesgo bajo"):
            self.assertIn(token, src)

    def test_no_hard_coded_48_in_the_coverage_logic(self):
        self.assertNotRegex(coverage_js(), r"\b48\b", "expected slots must be derived from the window, not hard-coded")


class CoverageCases(unittest.TestCase):
    """The ten mandatory cases of the audit (case 10, UI vs backend, is in BackendAgreement and InBrowser)."""

    def test_01_zero_zones_is_no_data_never_green(self):
        out = run_js("const out = [imergCoverageSummary([]), imergCoverageSummary(undefined), imergCoverageSummary(null)];")
        for s in out:
            self.assertEqual((s["zones"], s["overall"]), (0, "NO_DATA"))

    def test_02_one_of_one_is_incomplete(self):
        # A self-reported 1/1 contradicts the 24 h window: UNKNOWN. With coherent metadata, 1 of 48 is PARTIAL.
        st = states([imerg([[slots(1)[0], 0.1]], available=1, required=1)])[0]
        self.assertEqual((st["state"], st["valid"], st["expected"]), ("UNKNOWN", 1, 48))
        self.assertFalse(st["declared_matches"])
        self.assertEqual(states([imerg([[slots(1)[0], 0.1]])])[0]["state"], "PARTIAL")

    def test_03_twenty_four_of_twenty_four_is_incomplete(self):
        st = states([imerg([[t, 0.2] for t in slots(24)], available=24, required=24)])[0]
        self.assertEqual((st["state"], st["valid"]), ("UNKNOWN", 24))
        self.assertEqual(states([imerg([[t, 0.2] for t in slots(24)])])[0]["state"], "PARTIAL")

    def test_04_twenty_eight_of_forty_eight_is_incomplete(self):
        series = [[t, (0.1 if k % 12 < 7 else None)] for k, t in enumerate(slots(48))]
        st = states([imerg(series)])[0]
        self.assertEqual((st["state"], st["valid"], st["registered_without_value"]), ("PARTIAL", 28, 20))
        self.assertTrue(st["declared_matches"])

    def test_05_forty_seven_of_forty_eight_is_incomplete(self):
        series = [[t, None if k == 30 else 0.0] for k, t in enumerate(slots(48))]
        self.assertEqual(states([imerg(series)])[0]["state"], "PARTIAL")
        st = states([imerg([[t, 0.0] for t in slots(48)[1:]])])[0]  # one slot simply not listed
        self.assertEqual((st["state"], st["not_listed"]), ("PARTIAL", 1))

    def test_06_forty_eight_valid_unique_slots_are_complete(self):
        st = states([imerg([[t, 0.0] for t in slots(48)])])[0]
        self.assertEqual((st["state"], st["valid"], st["expected"]), ("COMPLETE", 48, 48))
        s = run_js(f"const out = imergCoverageSummary([{{imerg: {json.dumps(imerg([[t, 0.3] for t in slots(48)]))}}}]);")
        self.assertEqual(s["overall"], "COMPLETE")

    def test_07_forty_eight_records_with_duplicates_are_not_complete(self):
        ts = slots(48)
        dup = [[t, 0.1] for t in ts[:47]] + [[ts[0], 0.1]]  # 48 records, 47 distinct slots
        st = states([imerg(dup, available=48)])[0]
        self.assertEqual((st["state"], st["valid"], st["duplicates"]), ("UNKNOWN", 47, 1))
        extra = [[t, 0.1] for t in ts] + [[ts[5], 0.1]]  # 48 distinct + 1 duplicate: contradictory, never complete
        self.assertEqual(states([imerg(extra, available=48)])[0]["state"], "UNKNOWN")
        # Same instant written differently is still the same slot.
        alias = [[t, 0.1] for t in ts[:47]] + [[ts[0].replace("+00:00", "Z"), 0.1]]
        self.assertEqual(states([imerg(alias, available=48)])[0]["duplicates"], 1)

    def test_08_slots_outside_the_window_are_not_complete(self):
        ts = slots(48)
        shifted = [[t, 0.1] for t in ts[1:]] + [[END.isoformat(), 0.1]]  # last one starts at the window end
        st = states([imerg(shifted, available=48)])[0]
        self.assertEqual((st["state"], st["outside_window"]), ("UNKNOWN", 1))
        extra = [[t, 0.1] for t in ts] + [[(END - timedelta(hours=30)).isoformat(), 0.1]]
        self.assertEqual(states([imerg(extra, available=48)])[0]["state"], "UNKNOWN")
        misaligned = [[t, 0.1] for t in ts[:47]] + [[(END - timedelta(minutes=10)).isoformat(), 0.1]]
        self.assertEqual(states([imerg(misaligned, available=48)])[0]["state"], "UNKNOWN")

    def test_09_missing_or_invalid_data_is_unknown_or_no_data(self):
        good = imerg([[t, 0.1] for t in slots(48)])
        cases = {
            "no imerg block": None,
            "malformed block (string)": "x",
            "malformed block (array)": [1, 2],
            "zone without archive": {"source": None, "status": "NO_DISPONIBLE"},
            "no coverage block": {k: v for k, v in good.items() if k != "coverage_24h"},
            "no series": {k: v for k, v in good.items() if k != "series_24h_half_hourly_mm"},
            "no window end": {**good, "window_end_utc": None},
            "negative value": imerg([[t, -1.0] for t in slots(48)]),
            "text value": imerg([[t, "0.1"] for t in slots(48)]),
            "NaN-like": imerg([[slots(48)[0], "NaN"]] + [[t, None] for t in slots(47)]),
            "bad timestamp": imerg([["ayer", 0.1]] + [[t, 0.1] for t in slots(47)]),
            "declared 48/48, series 47": imerg([[t, 0.1] for t in slots(47)], available=48),
            "series 48, declared 47": imerg([[t, 0.1] for t in slots(48)], available=47),
            "all gaps": imerg([[t, None] for t in slots(48)]),
            "empty series": imerg([]),
        }
        got = dict(zip(cases, (s["state"] for s in states(list(cases.values())))))
        for name, st in got.items():
            self.assertIn(st, ("UNKNOWN", "NO_DATA", "PARTIAL"), name)
            self.assertNotEqual(st, "COMPLETE", name)
        for name in ("no imerg block", "zone without archive", "all gaps", "empty series"):
            self.assertEqual(got[name], "NO_DATA", name)
        for name in ("malformed block (string)", "malformed block (array)", "no coverage block", "no series", "no window end", "negative value", "text value", "NaN-like", "bad timestamp",
                     "series 48, declared 47"):
            self.assertEqual(got[name], "UNKNOWN", name)
        mixed = run_js(f"const out = imergCoverageSummary([{{imerg: null}}, {{imerg: {json.dumps(good)}}}]);")
        self.assertEqual(mixed["overall"], "PARTIAL", "one complete zone never makes the whole set complete")
        only_unknown = run_js("const out = imergCoverageSummary([{imerg: {source: 'x'}}]);")
        self.assertEqual(only_unknown["overall"], "UNKNOWN")

    def test_expected_slots_follow_the_window_length(self):
        six_h = imerg([[t, 0.1] for t in slots(12)], required=12, window_slots=12)
        self.assertEqual(states([six_h], window_min=360)[0]["state"], "COMPLETE")
        self.assertEqual(states([six_h])[0]["state"], "UNKNOWN", "12 slots are complete for 6 h, never for 24 h")
        self.assertEqual(run_js("const out = [expectedSlots(1440, 30), expectedSlots(360, 30), expectedSlots(100, 30), expectedSlots(1440, 0)];"),
                         [48, 12, None, None])


class MissingListCoherence(unittest.TestCase):
    """coverage_24h.missing_half_hours_utc must name exactly the window slots without a valid value."""

    def st(self, im):
        return states([im])[0]

    def test_full_series_with_empty_list_is_complete(self):
        r = self.st(imerg([[t, 0.1] for t in slots(48)], missing=[]))
        self.assertEqual((r["state"], r["missing_list_matches"]), ("COMPLETE", True))

    def test_full_series_with_a_declared_missing_slot_is_unknown(self):
        ts = slots(48)
        r = self.st(imerg([[t, 0.1] for t in ts], missing=[ts[10]]))
        self.assertEqual((r["state"], r["valid"], r["missing_list_matches"]), ("UNKNOWN", 48, False))
        self.assertIn("contradictoria", r["reason"])

    def test_one_gap_with_the_right_slot_listed_is_partial(self):
        ts = slots(48)
        series = [[t, None if k == 10 else 0.1] for k, t in enumerate(ts)]
        self.assertEqual(self.st(imerg(series, missing=[ts[10]]))["state"], "PARTIAL")
        self.assertEqual(self.st(imerg(series, missing=[ts[10].replace("+00:00", "Z")]))["state"], "PARTIAL", "same instant, other notation")

    def test_one_gap_with_an_empty_list_is_unknown(self):
        ts = slots(48)
        series = [[t, None if k == 10 else 0.1] for k, t in enumerate(ts)]
        self.assertEqual(self.st(imerg(series, missing=[]))["state"], "UNKNOWN", "an empty list never proves completeness")
        self.assertEqual(self.st(imerg([[t, 0.1] for t in ts[1:]], missing=[]))["state"], "UNKNOWN", "an unlisted slot must be declared")

    def test_one_gap_with_the_wrong_slot_listed_is_unknown(self):
        ts = slots(48)
        series = [[t, None if k == 10 else 0.1] for k, t in enumerate(ts)]
        self.assertEqual(self.st(imerg(series, missing=[ts[11]]))["state"], "UNKNOWN")
        self.assertEqual(self.st(imerg(series, missing=[ts[10], ts[11]]))["state"], "UNKNOWN")

    def test_duplicated_entries_in_the_list_are_unknown(self):
        ts = slots(48)
        series = [[t, None if k == 10 else 0.1] for k, t in enumerate(ts)]
        for missing in ([ts[10], ts[10]], [ts[10], ts[10].replace("+00:00", "Z")]):
            self.assertEqual(self.st(imerg(series, missing=missing))["state"], "UNKNOWN", missing)

    def test_invalid_or_out_of_window_entries_are_unknown(self):
        ts = slots(48)
        series = [[t, None if k == 10 else 0.1] for k, t in enumerate(ts)]
        bad = {"text": "ayer", "number": 1760990400000, "misaligned": (END - timedelta(minutes=10)).isoformat(),
               "at window end": END.isoformat(), "before window": (END - timedelta(hours=25)).isoformat(), "null": None}
        for name, m in bad.items():
            self.assertEqual(self.st(imerg(series, missing=[ts[10], m]))["state"], "UNKNOWN", name)
        no_list = imerg(series)
        del no_list["coverage_24h"]["missing_half_hours_utc"]
        self.assertEqual(self.st(no_list)["state"], "UNKNOWN", "absent list")
        self.assertEqual(self.st(imerg(series, missing="2026-10-20T03:00:00+00:00"))["state"], "UNKNOWN", "not a list")

    def test_all_gaps_and_empty_series_stay_no_data_only_when_coherent(self):
        gaps = [[t, None] for t in slots(48)]
        self.assertEqual(self.st(imerg(gaps))["state"], "NO_DATA")
        self.assertEqual(self.st(imerg(gaps, missing=[]))["state"], "UNKNOWN")
        self.assertEqual(self.st(imerg([]))["state"], "NO_DATA")
        self.assertEqual(self.st(imerg([], missing=slots(1)))["state"], "UNKNOWN")

    def test_no_contradiction_ever_turns_the_summary_green(self):
        ts = slots(48)
        good = imerg([[t, 0.1] for t in ts])
        contradictions = [imerg([[t, 0.1] for t in ts], missing=[ts[0]]),
                          imerg([[t, None if k == 3 else 0.1] for k, t in enumerate(ts)], missing=[]),
                          imerg([[t, None if k == 3 else 0.1] for k, t in enumerate(ts)], missing=[ts[3], ts[3]])]
        for c in contradictions:
            for zones in ([c], [good, c], [c, good, good]):
                s = run_js(f"const out = imergCoverageSummary({json.dumps([{'imerg': z} for z in zones])});")
                self.assertNotEqual(s["overall"], "COMPLETE")
                self.assertGreaterEqual(s["unknown"], 1)
        only = run_js(f"const out = imergCoverageSummary({json.dumps([{'imerg': c} for c in contradictions])});")
        self.assertEqual(only["overall"], "UNKNOWN")


class BackendAgreement(unittest.TestCase):
    """Case 10 (logic): the page reads the engine's real output the same way the engine counted it."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("v09_zone_rain_engine", ROOT / "scripts/v09_zone_rain_engine.py")
        cls.E = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.E)

    def zone(self, present):
        last = END - timedelta(minutes=30)
        granules = [{"time_utc": (last - timedelta(minutes=30 * k)).isoformat(),
                     "targets": {"z": {"accum_30min_mm": 0.1, "valid_cells": 3 if k in present else 0}}} for k in range(48)]
        return self.E.imerg_for_zone("z", None, {"granules": granules}, None)

    def test_engine_output_and_page_state_agree(self):
        for present, expected_state in ((range(48), "COMPLETE"), (range(47), "PARTIAL"), (range(24), "PARTIAL"), ((0,), "PARTIAL")):
            im = json.loads(json.dumps(self.zone(set(present))))
            st = states([im])[0]
            self.assertEqual(st["state"], expected_state, len(present))
            self.assertEqual(st["valid"], im["coverage_24h"]["available_half_hours"])
            self.assertTrue(st["declared_matches"])
            self.assertTrue(st["missing_list_matches"], "the engine's missing list is exactly the slots without a value")

    def test_registered_files_without_valid_cells_are_not_observations(self):
        im = json.loads(json.dumps(self.zone(set(range(0, 48, 2)))))  # all 48 granules registered, half with no valid cells
        self.assertEqual(len(im["series_24h_half_hourly_mm"]), 48)
        st = states([im])[0]
        self.assertEqual((st["state"], st["valid"], st["registered_without_value"]), ("PARTIAL", 24, 24))

    def test_committed_bundle_is_never_reported_complete_without_full_evidence(self):
        bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
        for k, v in GUARDS.items():
            self.assertEqual(bundle[k], v, k)
        zones = bundle["rain"]["zones"]
        got = states([z.get("imerg") for z in zones])
        for z, st in zip(zones, got):
            c = (z.get("imerg") or {}).get("coverage_24h") or {}
            if st["state"] == "COMPLETE":
                self.assertEqual((c.get("required_half_hours"), c.get("available_half_hours")), (48, 48), z["zone_id"])
                self.assertEqual(c.get("missing_half_hours_utc"), [], z["zone_id"])
            self.assertNotIn("contradictoria", st["reason"], f"committed bundle must be coherent: {z['zone_id']} {st['reason']}")


@unittest.skipIf(os.environ.get("IRFEN_SKIP_BROWSER") == "1", "browser explicitly disabled")
class InBrowser(unittest.TestCase):
    """Case 10 (UI): what the page renders matches the verified states (Playwright, synthetic bundles, no network)."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright  # an ImportError fails the test: it is never silently skipped
        cls.pw = sync_playwright().start()
        args = ["--no-proxy-server"]
        exe = os.environ.get("IRFEN_CHROMIUM")
        cls.browser = cls.pw.chromium.launch(args=args, **({"executable_path": exe} if exe else {}))
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(ROOT / "site"), **k)  # noqa: E731
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.origin = f"http://127.0.0.1:{cls.srv.server_address[1]}/"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()

    def render(self, zones_imerg):
        bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
        template = bundle["rain"]["zones"][0]
        bundle["rain"]["zones"] = [dict(copy.deepcopy(template), zone_id=f"z{i}", display_name=f"Zona {i}", imerg=im)
                                   for i, im in enumerate(zones_imerg)]
        body = json.dumps(bundle)
        page = self.browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # renderAll() catches module errors: they surface only as console.error and an "Error al dibujar" chip.
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        def route(r):
            url = r.request.url
            if url.endswith("/data/v09/dashboard_v0_1.json") or "dashboard_v0_1.json?" in url:
                return r.fulfill(status=200, content_type="application/json", body=body)
            if url.startswith(self.origin):
                return r.continue_()
            return r.abort()  # no external requests
        page.route("**/*", route)
        page.goto(self.origin + "v09/index.html")
        page.wait_for_selector("#continuity-chips [data-coverage-overall]", timeout=15000)
        chip = page.locator("#continuity-chips [data-coverage-overall]")
        res = dict(overall=chip.get_attribute("data-coverage-overall"), cls=chip.get_attribute("class"), text=chip.inner_text(),
                   lines=page.eval_on_selector_all("#center-table [data-coverage-state]", "els => els.map(e => e.getAttribute('data-coverage-state'))"),
                   summary=page.inner_text("#summary"), errors=errors, panel={}, panel_text={},
                   module_errors=page.eval_on_selector_all("#chips .chip", "els => els.map(e => e.textContent).filter(t => t.includes('Error al dibujar'))"),
                   center_rows=page.eval_on_selector_all("#center-table tr", "els => els.map(e => e.innerText)")[1:],
                   rain_cards=page.eval_on_selector_all("#rain-cards .card", "els => els.map(e => ({text: e.innerText, cov: [...e.querySelectorAll('[data-coverage-state]')].map(x => x.getAttribute('data-coverage-state'))}))"))
        for i in range(len(zones_imerg)):
            page.evaluate(f"selectZone('z{i}')")
            res["panel"][f"z{i}"] = page.eval_on_selector_all("[data-coverage-state]:not(#center-table *):not(#rain-cards *)",
                                                              "els => els.map(e => e.getAttribute('data-coverage-state'))")
            res["panel_text"][f"z{i}"] = page.inner_text("#zone-detail") if page.query_selector("#zone-detail") else ""
        page.close()
        return res

    def assert_rendered_cleanly(self, r):
        self.assertEqual(r["errors"], [], "no JavaScript errors (including errors caught by renderAll)")
        self.assertEqual(r["module_errors"], [], "every module rendered")

    def test_null_imerg_zone_next_to_a_valid_zone(self):
        """imerg: null must not break any view, must read NO_DATA, never complete, green or zero rain."""
        full = imerg([[t, 0.4] for t in slots(48)])
        r = self.render([None, full])
        self.assert_rendered_cleanly(r)
        self.assertEqual(r["overall"], "PARTIAL")
        self.assertNotIn(" ok", f" {r['cls']} ")
        self.assertIn("1 completas, 0 parciales, 1 sin datos, 0 desconocidas de 2 zonas", r["text"])
        # Summary: rendered, explicit, no "no rain" reading.
        self.assertIn("Lluvia observada por satélite", r["summary"])
        self.assertIn("nunca como cero", r["summary"])
        # Tracking centre: both zones listed; the null zone shows NO_DATA and the missing IMERG, no mm values.
        self.assertEqual(len(r["center_rows"]), 2)
        self.assertEqual(sorted(r["lines"]), ["COMPLETE", "NO_DATA"])
        null_row = next(x for x in r["center_rows"] if "Zona 0" in x)
        self.assertIn("SIN DATOS (NO_DATA)", null_row)
        self.assertIn("IMERG Early sin muestras para esta zona", null_row)
        self.assertNotIn("IMERG 24h:", null_row)
        self.assertIn("Zona 1", next(x for x in r["center_rows"] if "COMPLETA" in x))
        # Rain cards: both present, each with its verified coverage state; the null zone has no IMERG amounts.
        self.assertEqual(len(r["rain_cards"]), 2)
        cards = {("Zona 0" if "Zona 0" in c["text"] else "Zona 1"): c for c in r["rain_cards"]}
        self.assertEqual(cards["Zona 0"]["cov"], ["NO_DATA"])
        self.assertEqual(cards["Zona 1"]["cov"], ["COMPLETE"])
        self.assertIn("sin muestras IMERG", cards["Zona 0"]["text"])
        self.assertNotRegex(cards["Zona 0"]["text"].split("Observado · GOES-19")[0], r"\b\d+(\.\d+)? mm\b")
        # Zone panels: each selectable, with its own state.
        self.assertEqual(r["panel"], {"z0": ["NO_DATA"], "z1": ["COMPLETE"]})
        self.assertIn("Sin muestras IMERG", r["panel_text"]["z0"])

    def test_contradictory_missing_list_is_unknown_in_every_view(self):
        ts = slots(48)
        contradictory = imerg([[t, 0.1] for t in ts], missing=[ts[5]])
        r = self.render([contradictory, imerg([[t, 0.1] for t in ts])])
        self.assert_rendered_cleanly(r)
        self.assertEqual(r["overall"], "PARTIAL")
        self.assertNotIn(" ok", f" {r['cls']} ")
        self.assertIn("1 completas, 0 parciales, 0 sin datos, 1 desconocidas de 2 zonas", r["text"])
        self.assertEqual(r["panel"]["z0"], ["UNKNOWN"])
        self.assertEqual(sorted(r["lines"]), ["COMPLETE", "UNKNOWN"])
        self.assertEqual(sorted(c["cov"][0] for c in r["rain_cards"]), ["COMPLETE", "UNKNOWN"])
        row = next(x for x in r["center_rows"] if "Zona 0" in x)
        self.assertIn("DESCONOCIDA (UNKNOWN)", row)
        self.assertIn("evidencia contradictoria", row)

    def test_malformed_imerg_block_is_unknown_and_does_not_break_views(self):
        r = self.render(["no es un objeto", imerg([[t, 0.1] for t in slots(48)])])
        self.assert_rendered_cleanly(r)
        self.assertEqual(sorted(r["lines"]), ["COMPLETE", "UNKNOWN"])
        self.assertNotIn(" ok", f" {r['cls']} ")

    def test_zero_zones_render_no_data_not_green(self):
        r = self.render([])
        self.assertEqual(r["overall"], "NO_DATA")
        self.assertNotIn(" ok", f" {r['cls']} ")
        self.assertIn("no hay evidencia", r["text"])
        self.assertIn("Sin zonas en el paquete", r["summary"])
        self.assert_rendered_cleanly(r)

    def test_ui_reflects_each_zone_state(self):
        full = imerg([[t, 0.1] for t in slots(48)])
        one = imerg([[slots(1)[0], 0.1]], available=1, required=1)
        dup = imerg([[t, 0.1] for t in slots(48)[:47]] + [[slots(48)[0], 0.1]], available=48)
        no_archive = {"source": None, "status": "NO_DISPONIBLE", "reason": "zone not sampled by any IMERG Early archive yet",
                      "windows": {k: {"status": "NO_DISPONIBLE"} for k in ("1h", "3h", "6h", "24h")}}  # engine shape
        r = self.render([full, one, dup, no_archive])
        self.assertEqual(r["overall"], "PARTIAL")
        self.assertNotIn(" ok", f" {r['cls']} ")
        self.assertIn("1 completas, 0 parciales, 1 sin datos, 2 desconocidas de 4 zonas", r["text"])
        self.assert_rendered_cleanly(r)
        # Each zone's coverage line (tracking centre and selected-zone panel) shows the verified state, never the self-report.
        self.assertTrue(r["lines"])
        self.assertEqual(sorted(r["lines"]), sorted(["COMPLETE", "UNKNOWN", "UNKNOWN", "NO_DATA"]), "tracking centre, one line per zone")
        self.assertEqual(r["panel"], {"z0": ["COMPLETE"], "z1": ["UNKNOWN"], "z2": ["UNKNOWN"], "z3": ["NO_DATA"]}, "selected-zone panel")

    def test_only_full_verified_evidence_is_green(self):
        r = self.render([imerg([[t, 0.0] for t in slots(48)])] * 2)
        self.assertEqual(r["overall"], "COMPLETE")
        self.assertIn(" ok", f" {r['cls']} ")
        self.assert_rendered_cleanly(r)


if __name__ == "__main__":
    unittest.main()
