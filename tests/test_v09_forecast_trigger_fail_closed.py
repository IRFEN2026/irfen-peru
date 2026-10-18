"""v0.9 forecast trigger (main): inert unless IRFEN_FORECAST_ENGINE_ENABLED == 'true', never dispatches training,
and fail-closed on GitHub API errors. The dispatch script is extracted from the workflow and run with a fake `gh`
on PATH, so the behaviour (not just the text) is checked. No network, no GitHub call."""
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = (ROOT / ".github/workflows/v09-forecast-trigger.yml").read_text(encoding="utf-8")


def script() -> str:
    body = WF.split("run: |", 1)[1]
    lines = [l for l in body.splitlines()[1:]]
    indent = len(lines[0]) - len(lines[0].lstrip())
    out = []
    for l in lines:
        if l.strip() and len(l) - len(l.lstrip()) < indent:
            break
        out.append(l[indent:])
    return "\n".join(out)


def run(fake_gh: str):
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "calls.log"
        gh = Path(d) / "gh"
        gh.write_text("#!/bin/bash\necho \"$*\" >> " + str(log) + "\n" + fake_gh, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}", GH_TOKEN="x", GH_REPO="o/r")
        p = subprocess.run(["bash", "-c", script()], env=env, capture_output=True, text=True, timeout=30)
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return p, calls


class TriggerContract(unittest.TestCase):
    def test_inert_unless_variable_is_exactly_true(self):
        self.assertIn("if: vars.IRFEN_FORECAST_ENGINE_ENABLED == 'true'", WF)

    def test_minimal_permissions_and_no_repository_code(self):
        self.assertRegex(WF, r"permissions:\n  actions: write\n\n")
        self.assertNotIn("actions/checkout", WF)
        self.assertNotIn("${{", script())

    def test_only_the_engine_is_dispatched_never_training(self):
        dispatches = re.findall(r"gh workflow run (\S+)", WF)
        self.assertEqual(dispatches, ["v09-forecast-engine.yml"])
        self.assertIn("--ref v09/forecast-engine", WF)


class TriggerBehaviour(unittest.TestCase):
    def test_idle_queue_dispatches_engine_once(self):
        p, calls = run('case "$1 $2" in "run list") echo 0;; "workflow run") exit 0;; esac\n')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([c for c in calls if c.startswith("workflow run")], ["workflow run v09-forecast-engine.yml --ref v09/forecast-engine"])

    def test_waiting_run_skips_cycle(self):
        p, calls = run('case "$1 $2" in "run list") echo 1;; esac\n')
        self.assertEqual(p.returncode, 0)
        self.assertFalse([c for c in calls if c.startswith("workflow run")])
        self.assertIn("ciclo omitido", p.stdout)

    def test_github_api_error_is_fail_closed(self):
        p, calls = run('case "$1 $2" in "run list") echo "HTTP 502" >&2; exit 1;; esac\n')
        self.assertEqual(p.returncode, 0)
        self.assertFalse([c for c in calls if c.startswith("workflow run")], "dispatched despite an API error")
        self.assertIn("ciclo omitido", p.stdout)

    def test_dispatch_failure_is_visible(self):
        p, _ = run('case "$1 $2" in "run list") echo 0;; "workflow run") echo "HTTP 404" >&2; exit 1;; esac\n')
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
