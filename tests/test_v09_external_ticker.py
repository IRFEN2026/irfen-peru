"""IRFEN v0.9 continuity: external ticker (outside GitHub Actions) and the continuity report. Offline.

Runs below are SYNTHETIC (shape of the GitHub API), used only to exercise the rules.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKER = ROOT / "ops/external_ticker"
SPEC = importlib.util.spec_from_file_location("v09_continuity_report", ROOT / "scripts/v09_continuity_report.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
NODE = shutil.which("node")
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def run(minutes_ago, conclusion="success", event="schedule", duration=2):
    t = (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
    end = (NOW - timedelta(minutes=minutes_ago - duration)).isoformat().replace("+00:00", "Z")
    return dict(created_at=t, run_started_at=t, updated_at=end, conclusion=conclusion, event=event)


class ContinuityReport(unittest.TestCase):
    def test_gaps_include_the_open_gap_and_ignore_failures(self):
        runs = [run(600), run(420), run(400, "failure"), run(60, event="workflow_dispatch"), run(30)]
        s = C.summarize(runs, NOW - timedelta(hours=8), NOW, 30)
        self.assertEqual(s["successful_runs"], 3)  # 420, 60, 30 inside the 8 h window
        self.assertEqual(s["expected_at_nominal"], 16)
        self.assertEqual(s["by_event"], {"schedule": 2, "workflow_dispatch": 1})
        self.assertEqual(s["max_gap_min"], 360.0)  # 420 -> 60
        self.assertEqual(s["open_gap_min"], 30.0)
        self.assertEqual(s["failed_runs"], 1)

    def test_no_success_at_all(self):
        s = C.summarize([run(30, "failure")], NOW - timedelta(hours=8), NOW, 30)
        self.assertEqual((s["successful_runs"], s["max_gap_min"], s["open_gap_min"]), (0, None, None))

    def test_owner_criterion(self):
        """SYNTHETIC 48 h: runs every 30 min pass; a 100-min hole, a duplicate or a late start fail."""
        since = NOW - timedelta(hours=48)
        good = [run(m) for m in range(0, 48 * 60 + 30, 30)]
        rep = lambda runs: C.evaluate(dict(workflows={wf: C.summarize(runs, since, NOW, 30) for wf in C.CRITERION_WORKFLOWS}))
        self.assertEqual(rep(good)["v09-senamhi-avisos-capture.yml"]["result"], "PASA")
        hole = [r for r in good if not 600 < int((NOW - C.parse(r["created_at"])).total_seconds() / 60) < 700]  # 100-min gap
        r = rep(hole)["v09-rain-north.yml"]
        self.assertEqual((r["result"], r["items"]["all_intervals_within_90_min"]), ("NO_PASA", False))
        edge = [r for r in good if not 600 < int((NOW - C.parse(r["created_at"])).total_seconds() / 60) < 690]  # exactly 90 min
        self.assertEqual(rep(edge)["v09-rain-north.yml"]["result"], "PASA")
        dup = good + [run(301, event="workflow_dispatch")]  # 1 min after a scheduled run
        r = rep(dup)["v09-rain-north.yml"]
        self.assertEqual((r["result"], r["items"]["zero_duplicates"]), ("NO_PASA", False))
        overlap = good + [run(316, duration=20)]  # starts 14 min before the 300-min run, still running when it starts
        self.assertEqual(C.summarize(overlap, since, NOW, 30)["duplicates"], 1)
        self.assertEqual(rep([])["v09-rain-north.yml"]["result"], "SIN_DATOS")
        late_start = rep([run(5)])["v09-rain-north.yml"]  # one success 5 min ago, nothing before: 47 h 55 min gap
        self.assertEqual(late_start["result"], "NO_PASA")
        self.assertEqual(rep(good)["stale_data_visibility"]["result"], "VERIFICAR")
        self.assertEqual(C.CRITERION, dict(share_intervals_within_min=90, required_share=1.0, max_gap_min=90, max_duplicates=0, duplicate_window_min=10))

    def test_fallback_trace_and_table(self):
        pages = {
            "/actions/workflows/v08-scheduler-fallback.yml/runs": dict(workflow_runs=[
                dict(id=2, created_at="2026-10-13T12:10:00Z", event="workflow_dispatch", triggering_actor=dict(login="IRFEN2026"), status="completed", conclusion="success"),
                dict(id=1, created_at="2026-10-13T12:00:00Z", event="workflow_dispatch", triggering_actor=dict(login="IRFEN2026"), status="completed", conclusion="success")]),
            "/actions/runs/1/jobs": dict(jobs=[dict(id=11)]), "/actions/runs/2/jobs": dict(jobs=[dict(id=22)]),
            "/check-runs/11/annotations": [dict(title="FALLBACK_DISPATCH", message="v09-rain-north.yml | STALE: last run 4000s ago (schedule) >= 3600s"),
                                          dict(title="SCHEDULER_FALLBACK", message="dispatched=1")],
            "/check-runs/22/annotations": [dict(title="SCHEDULER_FALLBACK", message="dispatched=0")]}
        get = lambda path: pages[path.split("?")[0]]
        trace = C.fallback_trace("o/r", NOW - timedelta(hours=1), "t", get=get)
        self.assertEqual([t["id"] for t in trace], [1, 2])
        self.assertEqual(trace[0]["dispatched"], ["v09-rain-north.yml | STALE: last run 4000s ago (schedule) >= 3600s"])
        self.assertEqual((trace[1]["dispatched"], trace[0]["actor"]), ([], "IRFEN2026"))
        since = NOW - timedelta(hours=48)
        report = dict(since_utc=since.isoformat(), now_utc=NOW.isoformat(),
                      workflows={wf: C.summarize([run(m) for m in range(0, 48 * 60 + 30, 30)], since, NOW, C.WORKFLOWS[wf]) for wf in C.WORKFLOWS},
                      fallback_trace=trace)
        report["criterion"] = C.evaluate(report)
        md = C.markdown(report)
        for col in ("Frecuencia esperada", "Ejecuciones reales", "Hueco máximo", "Duplicados", "% intervalos ≤ 90 min", "Resultado"):
            self.assertIn(col, md)
        self.assertIn("| v09-rain-north.yml | cada 30 min |", md)
        self.assertIn("**PASA**", md)
        self.assertIn("**informativo**", md)
        self.assertIn("v09-rain-north.yml | STALE", md)

    def test_report_is_read_only(self):
        text = (ROOT / "scripts/v09_continuity_report.py").read_text(encoding="utf-8")
        self.assertNotIn("dispatches", text)
        self.assertNotIn('method="POST"', text)


class TickerFiles(unittest.TestCase):
    def test_ticker_dispatches_only_the_fallback_on_main(self):
        js = (TICKER / "worker.js").read_text(encoding="utf-8")
        sh = (TICKER / "tick.sh").read_text(encoding="utf-8")
        toml = (TICKER / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn('WORKFLOW = "v08-scheduler-fallback.yml"', toml)
        self.assertIn('ENABLED = "false"', toml)
        self.assertIn('crons = ["*/10 * * * *"]', toml)
        self.assertIn('JSON.stringify({ ref: "main" })', js)
        self.assertEqual(js.count("/dispatches"), 1)
        self.assertEqual(sh.count("/dispatches"), 1)
        self.assertIn('{"ref":"main"}', sh)
        for text in (js, sh):
            for forbidden in ("/merges", "/git/refs", "contents/", "/pulls", "force"):
                self.assertNotIn(forbidden, text)

    def test_no_secret_can_be_committed_and_guide_is_safe(self):
        ignore = (TICKER / ".gitignore").read_text(encoding="utf-8")
        for pattern in (".dev.vars", ".env", ".wrangler/"):
            self.assertIn(pattern, ignore)
        guide = (TICKER / "GUIA_PROPIETARIO.md").read_text(encoding="utf-8")
        self.assertIn("Actions → Read and write", guide)
        self.assertIn("secret put GITHUB_TOKEN", guide)
        self.assertIn("--var ENABLED:true", guide)
        self.assertNotRegex(guide + (TICKER / "README.md").read_text(encoding="utf-8") + (TICKER / "wrangler.toml").read_text(encoding="utf-8"),
                            r"(ghp_|github_pat_)[A-Za-z0-9_]{10,}")  # no token-shaped string anywhere
        self.assertIn("workers_dev = false", (TICKER / "wrangler.toml").read_text(encoding="utf-8"))

    def test_fallback_workflow_exists_and_keeps_minimal_permissions(self):
        wf = (ROOT / ".github/workflows/v08-scheduler-fallback.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("actions: write", wf)
        self.assertNotIn("contents: write", wf)
        self.assertIn("concurrency:", wf)


class GapCauses(unittest.TestCase):
    def test_gaps_are_classified_by_cause(self):
        since, now = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc), datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
        r = lambda h, m, c="success", ev="schedule": dict(created_at=f"2026-10-14T{h:02d}:{m:02d}:00Z", event=ev, conclusion=c, status="completed",
                                                         updated_at=f"2026-10-14T{h:02d}:{m + 1:02d}:00Z")
        runs = [r(0, 10), r(0, 40), r(3, 10), r(4, 0, "failure"), r(6, 10), r(6, 40, "cancelled"), r(9, 40)]
        gaps = C.classify_gaps(runs, since, now)
        self.assertEqual([(g["start_utc"][11:16], g["cause"]) for g in gaps],
                         [("00:40", "SIN_EJECUCION"), ("03:10", "EJECUCION_FALLIDA"), ("06:10", "CANCELADA"), ("09:40", "SIN_EJECUCION")])
        self.assertTrue(gaps[-1]["open"])  # the stretch up to 'now' counts
        lag = C.schedule_lag(runs, (7, 37))
        self.assertEqual(lag["cron_creation_lag_min"]["n"], 5)
        self.assertEqual(lag["run_to_published_min"]["max"], 1.0)


class GapForensics(unittest.TestCase):
    def test_missed_cron_slots(self):
        spec = importlib.util.spec_from_file_location("v09_continuity_forensics", ROOT / "scripts/v09_continuity_forensics.py")
        F = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(F)
        a, b = datetime(2026, 10, 14, 1, 54, tzinfo=timezone.utc), datetime(2026, 10, 14, 7, 31, tzinfo=timezone.utc)
        self.assertEqual(F.missed_slots(a, b, (7, 37)), 11)  # 02:07 ... 07:07
        self.assertEqual(F.missed_slots(a, a + timedelta(minutes=20), (7, 37)), 1)
        self.assertEqual(set(F.COLLECTORS), set(C.CRITERION_WORKFLOWS))


class TickShellFailsClosed(unittest.TestCase):
    """QA 14-10-2026: tick.sh dispatched when the run listing failed (curl error swallowed by `|| true`)."""

    def run_tick(self, list_mode, env_extra=None):
        with tempfile.TemporaryDirectory() as d:
            bin_dir, log = Path(d) / "bin", Path(d) / "calls.log"
            bin_dir.mkdir()
            listing = {"fail": 'echo "curl: (22) 503" >&2; exit 22', "html": "echo '<html>maintenance</html>'",
                       "empty": 'echo \'{"total_count":0,"workflow_runs":[]}\'',
                       "active": 'echo \'{"total_count":1,"workflow_runs":[{"id":1,"run_number":7,"status":"queued"}]}\''}[list_mode]
            (bin_dir / "curl").write_text("#!/bin/sh\n" f'echo "$*" >> "{log}"\n'
                                          'case "$*" in *dispatches*) printf 204; exit 0;; esac\n' + listing + "\n", encoding="utf-8")
            (bin_dir / "curl").chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GITHUB_TOKEN": "x", "ENABLED": "true", **(env_extra or {})}
            res = subprocess.run(["sh", str(TICKER / "tick.sh")], env=env, capture_output=True, text=True, timeout=30)
            calls = log.read_text(encoding="utf-8") if log.exists() else ""
            return res, calls.count("/dispatches")

    def test_failed_or_unexpected_listing_never_dispatches(self):
        for mode in ("fail", "html"):
            res, posts = self.run_tick(mode)
            self.assertEqual(posts, 0, mode)
            self.assertNotEqual(res.returncode, 0, mode)

    def test_idle_dispatches_once_and_active_skips(self):
        self.assertEqual(self.run_tick("empty")[1], 1)
        self.assertEqual(self.run_tick("active")[1], 0)
        self.assertEqual(self.run_tick("empty", {"ENABLED": "false"})[1], 0)

    def test_only_the_fallback_workflow(self):
        res, posts = self.run_tick("empty", {"WORKFLOW": "update-and-deploy.yml"})
        self.assertEqual(posts, 0)
        self.assertIn("CONFIG_REFUSED", res.stdout)


@unittest.skipUnless(NODE, "node not installed; runs on the GitHub runner")
class TickerDecision(unittest.TestCase):
    def node(self, script):
        mod = (TICKER / "worker.js").read_text(encoding="utf-8").replace("export default", "const _default =").replace("export ", "")
        return json.loads(subprocess.run([NODE, "-e", mod + script], capture_output=True, text=True, check=True, timeout=30).stdout)

    def test_decision(self):
        out = self.node('console.log(JSON.stringify([decideTick(true, []), decideTick(true, [{status:"queued"}]), decideTick(false, [])]))')
        self.assertEqual([o["dispatch"] for o in out], [True, False, False])
        self.assertTrue(out[1]["reason"].startswith("FALLBACK_ACTIVE"))
        self.assertTrue(out[2]["reason"].startswith("DRY_RUN"))

    def test_tick_with_fake_api(self):
        script = r"""
        const calls = [];
        const mk = (active) => async (url, opts={}) => { calls.push([opts.method||"GET", url]);
          if (url.endsWith("/dispatches")) return {status:204, ok:true};
          const st = new URL(url).searchParams.get("status");
          return {ok:true, status:200, json: async () => ({workflow_runs: active && st === "in_progress" ? [{status:"in_progress"}] : []})}; };
        const env = {REPO:"IRFEN2026/irfen-peru", WORKFLOW:"v08-scheduler-fallback.yml", GITHUB_TOKEN:"t", ENABLED:"true"};
        (async () => {
          const a = await tick(env, mk(false)); const nA = calls.filter(c => c[0]==="POST").length;
          const b = await tick(env, mk(true)); const nB = calls.filter(c => c[0]==="POST").length;
          const c = await tick({...env, ENABLED:"false"}, mk(false)); const nC = calls.filter(c => c[0]==="POST").length;
          console.log(JSON.stringify({a, b, c, nA, nB, nC, post: calls.filter(c => c[0]==="POST").map(c => c[1])}));
        })();"""
        out = self.node(script)
        self.assertTrue(out["a"]["dispatched"])
        self.assertFalse(out["b"]["dispatched"])
        self.assertFalse(out["c"]["dispatched"])
        self.assertEqual((out["nA"], out["nB"], out["nC"]), (1, 1, 1))
        self.assertEqual(out["post"], ["https://api.github.com/repos/IRFEN2026/irfen-peru/actions/workflows/v08-scheduler-fallback.yml/dispatches"])

    def test_worker_fails_closed(self):
        script = r"""
        let posts = 0;
        const ok = async (url, opts={}) => { if (url.endsWith("/dispatches")) { posts++; return {status:204, ok:true}; }
          return {ok:true, status:200, json: async () => ({workflow_runs: []})}; };
        const env = {REPO:"IRFEN2026/irfen-peru", WORKFLOW:"v08-scheduler-fallback.yml", GITHUB_TOKEN:"t", ENABLED:"true"};
        (async () => {
          const r = {};
          r.throws = await tick(env, async () => { throw new Error("network down"); });
          r.badJson = await tick(env, async () => ({ok:true, status:200, json: async () => { throw new Error("bad json"); }}));
          r.shape = await tick(env, async () => ({ok:true, status:200, json: async () => ({message:"x"})}));
          r.noToken = await tick({...env, GITHUB_TOKEN: ""}, ok);
          r.otherWf = await tick({...env, WORKFLOW: "update-and-deploy.yml"}, ok);
          r.otherRepo = await tick({...env, REPO: "someone/else"}, ok);
          console.log(JSON.stringify({r, posts}));
        })();"""
        out = self.node(script)
        self.assertEqual(out["posts"], 0)
        for k, v in out["r"].items():
            self.assertFalse(v["dispatched"], k)
        self.assertTrue(out["r"]["throws"]["reason"].startswith("ERROR"))
        self.assertEqual(out["r"]["noToken"]["reason"], "MISSING_TOKEN")
        self.assertEqual(out["r"]["otherWf"]["reason"], "CONFIG_REFUSED")
        self.assertTrue(out["r"]["shape"]["reason"].startswith("LIST_UNEXPECTED"))


if __name__ == "__main__":
    unittest.main()
