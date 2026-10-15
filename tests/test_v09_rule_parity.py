"""IRFEN v0.9: the dashboard (site/v09/index.html, SHARED-RULES block) and the engine apply the same rule.

The browser recomputes aviso status, IMERG/GOES-19 freshness, GEOS-CF sums and the internal review priority R1–R6
with the reader's clock. This test runs the JavaScript block with node and the Python engine on the same evidence
at several instants and compares the results. Cases are the committed real zones plus SYNTHETIC variations (labelled
as such; they only exercise the rules). Skipped when node is not installed; GitHub runners have it.
"""
import importlib.util
import json
import shutil
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_zone_rain_engine", ROOT / "scripts/v09_zone_rain_engine.py")
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)
HTML = (ROOT / "site/v09/index.html").read_text(encoding="utf-8")
NODE = shutil.which("node")


def shared_js() -> str:
    start, end = HTML.index("/* SHARED-RULES-BEGIN"), HTML.index("/* SHARED-RULES-END */")
    return HTML[start:end]


RUNNER = r"""
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = input.cases.map(c => {
  const t = Date.parse(c.at);
  const rp = reviewPriorityAt(c.avisos, c.imerg, c.goes19, c.percentile, t, input.freshness);
  const g = geosWindowsAt(c.geos_cf, t, input.freshness);
  return {code: rp.code, reasons_es: rp.reasons_es, missing_es: rp.missing_es, imerg_usable: rp.imerg_usable,
          goes_usable: rp.goes_usable, data_complete: rp.data_complete, next_change_ms: rp.next_change_ms,
          sort_key: prioritySortKey(c.zone_id, c.imerg, rp),
          geos: {status: g.status, windows: g.windows ? Object.fromEntries(Object.entries(g.windows).map(([k, v]) => [k, {status: v.status, accum_mm: v.accum_mm ?? null}])) : null}};
});
process.stdout.write(JSON.stringify(out));
"""


def cases() -> list[dict]:
    state = json.loads(E.OUT.read_text(encoding="utf-8"))
    base = datetime.fromisoformat(state["evaluated_at_utc"])
    instants = [base, base + timedelta(hours=6), base + timedelta(hours=13), base + timedelta(days=2), base - timedelta(days=1)]
    out = []
    for z in state["zones"]:
        for at in instants:
            out.append(dict(zone_id=z["zone_id"], at=at.isoformat(), avisos=z["avisos"], imerg=z["imerg"], goes19=z["goes19"],
                            percentile=z["percentile"], geos_cf=z["geos_cf"]))
    # SYNTHETIC variations on the first zone: no avisos, cancelled aviso, fresh evidence at the window end, gaps.
    z = state["zones"][0]
    end = z["imerg"].get("window_end_utc")
    if end:
        fresh_at = (E._t(end) + timedelta(minutes=10)).isoformat()
        goes_fresh = dict(z["goes19"], status="CALCULADO", rate_max_mm_h=0.0, rate_mean_mm_h=0.0, scan_end_utc=end)
        out.append(dict(zone_id="synthetic_no_aviso", at=fresh_at, avisos=[], imerg=z["imerg"], goes19=goes_fresh,
                        percentile=dict(status="NO_DISPONIBLE"), geos_cf=z["geos_cf"]))
        out.append(dict(zone_id="synthetic_cancelled", at=fresh_at, avisos=[dict(a, status="CANCELADO") for a in z["avisos"]],
                        imerg=z["imerg"], goes19=goes_fresh, percentile=dict(status="NO_DISPONIBLE"), geos_cf=z["geos_cf"]))
        out.append(dict(zone_id="synthetic_r1", at=fresh_at, avisos=z["avisos"], imerg=z["imerg"], goes19=goes_fresh,
                        percentile=dict(status="CALCULADO", percentile_24h=97), geos_cf=z["geos_cf"]))
    if z["geos_cf"].get("hourly"):
        gapped = dict(z["geos_cf"], hourly=[h for i, h in enumerate(z["geos_cf"]["hourly"]) if i != 8])
        out.append(dict(zone_id="synthetic_geos_gap", at=base.isoformat(), avisos=[], imerg=dict(windows={}), goes19=dict(status="NO_DISPONIBLE"),
                        percentile=dict(status="NO_DISPONIBLE"), geos_cf=gapped))
    return out


@unittest.skipUnless(NODE, "node not installed; the parity test runs on the GitHub runner")
class RuleParity(unittest.TestCase):
    def test_python_engine_and_dashboard_agree(self):
        cs = cases()
        self.assertGreater(len(cs), 50)
        js = subprocess.run([NODE, "-e", shared_js() + RUNNER], input=json.dumps(dict(cases=cs, freshness=E.FRESHNESS)),
                            capture_output=True, text=True, check=True, timeout=60)
        results = json.loads(js.stdout)
        seen_codes, stale = set(), 0
        for c, j in zip(cs, results):
            at = E._t(c["at"])
            p = E.review_priority(c["avisos"], c["imerg"], c["goes19"], c["percentile"], at)
            label = f"{c['zone_id']} @ {c['at']}"
            for key in ("code", "reasons_es", "missing_es", "imerg_usable", "goes_usable", "data_complete"):
                self.assertEqual(p[key], j[key], f"{key} differs for {label}")
            nxt = int(E._t(p["next_change_utc"]).timestamp() * 1000) if p["next_change_utc"] else None
            self.assertEqual(nxt, j["next_change_ms"], f"next change differs for {label}")
            row = dict(zone_id=c["zone_id"], imerg=c["imerg"], review_priority=p)
            py_key = list(E.sort_key(row))
            self.assertEqual(py_key[:3], j["sort_key"][:3], f"sort key differs for {label}")
            g = E.geos_windows_at(c["geos_cf"], at)
            self.assertEqual(g["status"], j["geos"]["status"], f"GEOS status differs for {label}")
            for k, w in (g.get("windows") or {}).items():
                self.assertEqual(w["status"], j["geos"]["windows"][k]["status"], f"GEOS {k} differs for {label}")
                if w["status"] == "CALCULADO":
                    self.assertAlmostEqual(w["accum_mm"], j["geos"]["windows"][k]["accum_mm"], delta=0.051)
            seen_codes.add(p["code"])
            stale += not p["imerg_usable"]
        self.assertGreaterEqual(len(seen_codes), 3, "cases should exercise several tiers")
        self.assertGreater(stale, 0, "cases should exercise stale observations")


class SharedBlockHygiene(unittest.TestCase):
    def test_shared_block_is_pure(self):
        block = shared_js()
        for forbidden in ("document.", "window.", "fetch(", "Date.now(", "localStorage", "innerHTML"):
            self.assertNotIn(forbidden, block)

    def test_dashboard_uses_the_shared_rule_everywhere(self):
        self.assertNotIn("geosSums", HTML)
        self.assertIn("reviewPriorityAt(zoneAvisos(z)", HTML)
        self.assertGreaterEqual(HTML.count("geosWindowsAt(z.geos_cf, Date.now(), FR())"), 3)
        self.assertIn("staleTag(", HTML)

    def test_freshness_parameters_match(self):
        js = shared_js()
        for k, v in E.FRESHNESS.items():
            self.assertIn(f"{k}:{v}", js)


class GeosSumRoundingParity(unittest.TestCase):
    """Regression (15-10-2026): on 5 of 28 committed states (e.g. main 06142f05, 077fbcfc, dbf996a0, 73b04296,
    607d4d83) the engine and the dashboard disagreed by 0.1 mm on a GEOS-CF window sum near a .x5 boundary, because
    Python summed with compensation and rounded half-even while the browser summed naively and rounded half up.
    Both now use the same IEEE-754 operations, so the results must be identical, not merely within a tolerance."""

    @unittest.skipUnless(NODE, "node not installed")
    def test_window_sums_are_bit_identical_near_half_tenths(self):
        import random
        rng = random.Random(20261015)
        at = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
        series = [[0.05] + [0.0] * 23, [0.1, 0.2, 0.15] + [0.0] * 21, [0.35, 0.1] + [0.0] * 22]
        series += [[round(rng.random() * rng.choice((0.05, 0.3, 2.0)), rng.choice((2, 3, 6))) for _ in range(24)] for _ in range(400)]
        cases = []
        for vals in series:
            geos = dict(status="CALCULADO", dataset_time_start=(at - timedelta(hours=1)).isoformat(),
                        hourly=[dict(valid_time_utc=(at + timedelta(hours=i)).isoformat(), precip_mm=v) for i, v in enumerate(vals)])
            cases.append(dict(zone_id="synthetic", at=at.isoformat(), avisos=[], imerg=dict(windows={}), goes19=dict(status="NO_DISPONIBLE"),
                              percentile=dict(status="NO_DISPONIBLE"), geos_cf=geos))
        js = subprocess.run([NODE, "-e", shared_js() + RUNNER], input=json.dumps(dict(cases=cases, freshness=E.FRESHNESS)),
                            capture_output=True, text=True, check=True, timeout=60)
        for c, j in zip(cases, json.loads(js.stdout)):
            g = E.geos_windows_at(c["geos_cf"], at)
            for k in ("6h", "24h"):
                self.assertEqual(g["windows"][k]["accum_mm"], j["geos"]["windows"][k]["accum_mm"], (k, c["geos_cf"]["hourly"][:6]))
        self.assertEqual(E.sum_tenths([0.05]), 0.1)
        self.assertEqual(E.sum_tenths([]), 0.0)


if __name__ == "__main__":
    unittest.main()
