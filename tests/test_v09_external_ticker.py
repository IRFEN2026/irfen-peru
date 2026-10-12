"""IRFEN v0.9 continuity: external ticker (outside GitHub Actions) and the continuity report. Offline.

Runs below are SYNTHETIC (shape of the GitHub API), used only to exercise the rules.
"""
import importlib.util
import json
import shutil
import subprocess
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


def run(minutes_ago, conclusion="success", event="schedule"):
    return dict(created_at=(NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z"), conclusion=conclusion, event=event)


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

    def test_fallback_workflow_exists_and_keeps_minimal_permissions(self):
        wf = (ROOT / ".github/workflows/v08-scheduler-fallback.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("actions: write", wf)
        self.assertNotIn("contents: write", wf)
        self.assertIn("concurrency:", wf)


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
        const env = {REPO:"o/r", WORKFLOW:"v08-scheduler-fallback.yml", GITHUB_TOKEN:"t", ENABLED:"true"};
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
        self.assertEqual(out["post"], ["https://api.github.com/repos/o/r/actions/workflows/v08-scheduler-fallback.yml/dispatches"])


if __name__ == "__main__":
    unittest.main()
