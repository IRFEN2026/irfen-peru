"""Freshness ledger and after-capture rebuild decision (SYNTHETIC archives; no network, no dispatch).

Adversarial cases: future times, duplicates, off-grid times, corrupt JSON, missing file, stale data, duplicate run,
failed dispatch with recovery, bounded retries. The live-refresh control never chains in after_capture mode and never
writes a test rebuild to the real data branch."""
import importlib.util
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F = _load("v091_freshness_t", "scripts/v091_capture_freshness.py")
LR = _load("v091_live_refresh_t", "scripts/v091_live_refresh.py")
UTC = timezone.utc
T0 = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)


def archive(last: datetime, n: int = 48, state="AVAILABLE", written=None, extra=()):
    times = [last - timedelta(minutes=30 * k) for k in range(n)][::-1] + list(extra)
    return dict(status=dict(state=state, written_at_utc=(written or last + timedelta(hours=5)).isoformat()),
                granules=[dict(time_utc=t.isoformat(), rate_mm_hr=[0.1]) for t in times])


class Observation(unittest.TestCase):
    def test_last_observation_age_and_latency(self):
        o = F.observation_state(archive(T0), b"x", T0 + timedelta(hours=6), "c")
        self.assertEqual(o["last_observation_end_utc"], (T0 + timedelta(minutes=30)).isoformat())
        self.assertEqual(o["age_hours"], 5.5)
        self.assertEqual(o["latency_at_write_hours"], 4.5)
        self.assertEqual((o["freshness"], o["state"], o["missing_half_hours_24h"]), ("RECIENTE", "OK", []))

    def test_stale_and_gaps(self):
        a = archive(T0, n=40)
        o = F.observation_state(a, b"x", T0 + timedelta(hours=13), "c")
        self.assertEqual(o["freshness"], "CADUCADA")
        self.assertEqual(len(o["missing_half_hours_24h"]), 8)

    def test_future_duplicate_offgrid_block_the_trigger(self):
        for extra in ([T0 + timedelta(hours=3)], [T0], [T0 - timedelta(minutes=7)]):
            o = F.observation_state(archive(T0, extra=extra), b"x", T0 + timedelta(hours=1), "c")
            self.assertEqual(o["state"], "INVALIDO", extra)
            self.assertFalse(o["trigger_ok"])
        o = F.observation_state(archive(T0, extra=[T0 + timedelta(hours=3)]), b"x", T0 + timedelta(hours=1), "c")
        self.assertEqual(o["last_observation_start_utc"], T0.isoformat())  # the future one is never the "last observation"

    def test_missing_archive(self):
        o = F.observation_state(None, None, T0, "c")
        self.assertEqual((o["state"], o["trigger_ok"]), ("SIN_DATOS", False))


class Decision(unittest.TestCase):
    def obs(self, t, sha="a"):
        o = F.observation_state(archive(t), sha.encode(), t + timedelta(hours=5), "c")
        return o

    def test_new_observation_triggers_once(self):
        o = self.obs(T0)
        self.assertEqual(F.decide(None, o, "m")["action"], "SI")
        prev = dict(last_dispatch=dict(key=f"{o['last_observation_start_utc']}|{o['archive_sha256']}", result="OK",
                                       observation_start_utc=o["last_observation_start_utc"]))
        self.assertEqual(F.decide(prev, o, "m")["action"], "NO")  # duplicate run of the same capture
        o2 = self.obs(T0 + timedelta(minutes=30), sha="b")
        self.assertEqual(F.decide(prev, o2, "m")["action"], "SI")

    def test_no_new_observation_even_if_file_changed(self):
        o = self.obs(T0, sha="b")  # same last half-hour, different bytes (e.g. status only)
        prev = dict(last_dispatch=dict(key="x", result="OK", observation_start_utc=T0.isoformat()))
        self.assertEqual(F.decide(prev, o, "m")["action"], "NO")

    def test_failed_request_is_retried_then_given_up(self):
        o = self.obs(T0)
        prev = dict(pending_retry=dict(key="k", retries=0, error="HTTP 500"))
        d = F.decide(prev, o, "m")
        self.assertEqual((d["action"], d["retries"]), ("REINTENTO", 1))
        prev = dict(pending_retry=dict(key="k", retries=F.MAX_RETRIES_ACROSS_RUNS, error="HTTP 500"),
                    last_dispatch=dict(key="k", result="FALLO", observation_start_utc=T0.isoformat()))
        self.assertEqual(F.decide(prev, o, "m")["action"], "NO")  # exhausted and nothing new: stop

    def test_invalid_archive_never_triggers(self):
        o = F.observation_state(archive(T0, extra=[T0]), b"x", T0 + timedelta(hours=1), "c")
        self.assertEqual(F.decide(None, o, "m")["action"], "NO")


class Dispatch(unittest.TestCase):
    def test_bounded_retries_with_backoff(self):
        waits, calls = [], []

        def run(cmd, **kw):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=1, stderr="HTTP 502", stdout="")
        r = F.dispatch(["gh", "x"], sleep=waits.append, run=run)
        self.assertEqual((r["result"], len(calls), waits), ("FALLO", F.DISPATCH_ATTEMPTS, list(F.DISPATCH_BACKOFF_S)))

    def test_ledger_roundtrip_records_failure_and_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "ledger.json"
            fail = lambda cmd, **kw: types.SimpleNamespace(returncode=1, stderr="boom", stdout="")
            ok = lambda cmd, **kw: types.SimpleNamespace(returncode=0, stderr="", stdout="")
            r1 = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "1", ["gh"], False, sleep=lambda s: None, runner=fail)
            self.assertEqual(r1["last_dispatch"]["result"], "FALLO")
            self.assertIn("pending_retry", r1)
            r2 = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=6), "m", "2", ["gh"], False, sleep=lambda s: None, runner=ok)
            self.assertEqual((r2["decision"]["action"], r2["last_dispatch"]["result"]), ("REINTENTO", "OK"))
            self.assertNotIn("pending_retry", r2)
            r3 = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=7), "m", "3", ["gh"], False, sleep=lambda s: None, runner=ok)
            self.assertEqual(r3["decision"]["action"], "NO")
            self.assertEqual([h["capture_run_id"] for h in r3["history"]], ["1", "2", "3"])
            for k, v in F.GUARDS.items():
                self.assertEqual(r3[k], v)

    def test_corrupt_archive_is_recorded_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text("{not json", encoding="utf-8")
            r = F.run_once(d / "c.json", None, d / "l.json", T0, "m", "1", ["gh"], True)
            self.assertEqual(r["decision"]["action"], "NO")


class Control(unittest.TestCase):
    CFG = dict(enabled=True, expires_at_utc="2026-11-20T00:00:00Z", max_hops_per_chain=10, poll_minutes=20, data_branch="research/v091-live-data",
               public_alerting=False, notifications_enabled=False, merged_into_main=False, predictive=False,
               after_capture=dict(enabled=False, expires_at_utc=None))

    def test_after_capture_never_chains_and_is_off_by_default(self):
        c = LR.control(self.CFG, T0, 0, "after_capture")
        self.assertEqual((c["run"], c["chain"]), ("false", "false"))
        cfg = dict(self.CFG, after_capture=dict(enabled=True, expires_at_utc="2026-11-10T00:00:00Z"))
        c = LR.control(cfg, T0, 0, "after_capture")
        self.assertEqual((c["run"], c["chain"], c["data_branch"]), ("true", "false", "research/v091-live-data"))
        self.assertEqual(LR.control(cfg, T0 + timedelta(days=2), 0, "after_capture")["run"], "false")  # own expiry

    def test_test_rebuild_only_to_a_test_data_branch(self):
        c = LR.control(self.CFG, T0, 0, "after_capture", "research/v091-live-data-test-x")
        self.assertEqual((c["run"], c["chain"], c["data_branch"]), ("true", "false", "research/v091-live-data-test-x"))
        self.assertEqual(LR.control(self.CFG, T0, 0, "after_capture", "research/v091-live-data")["run"], "false")

    def test_isolated_source_branch_only_for_test_rebuilds(self):
        c = LR.control(self.CFG, T0, 0, "after_capture", "research/v091-live-data-test-x", "research/v091-e2e-capture-x")
        self.assertEqual((c["run"], c["source_ref"], c["chain"]), ("true", "research/v091-e2e-capture-x", "false"))
        self.assertEqual(LR.control(self.CFG, T0, 0, "after_capture", None, "research/v091-e2e-capture-x")["run"], "false")
        self.assertEqual(LR.control(self.CFG, T0, 0, "after_capture", "research/v091-live-data-test-x", "main-copy")["run"], "false")
        self.assertEqual(LR.control(self.CFG, T0, 0, "chain", None, "research/v091-e2e-capture-x")["run"], "false")

    def test_chain_still_obeys_its_expiry(self):
        self.assertEqual(LR.control(self.CFG, T0, 0)["chain"], "true")
        self.assertEqual(LR.control(self.CFG, T0 + timedelta(days=30), 0)["run"], "false")

    def test_repository_config_keeps_both_mechanisms_inactive(self):
        cfg = json.loads((ROOT / "config/v091_live_refresh.json").read_text(encoding="utf-8"))
        self.assertIs(cfg["after_capture"]["enabled"], False)
        self.assertEqual(LR.control(cfg, datetime(2026, 11, 9, 16, tzinfo=UTC), 0)["run"], "false")  # chain expired 09-11



class TwoPhase(unittest.TestCase):
    def test_decide_before_commit_then_dispatch_after_push(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "l.json"
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "1", ["gh"], False, defer=True)
            self.assertEqual((r["decision"]["action"], r["last_dispatch"]["result"]), ("SI", "PEDIDA"))
            # the same capture seen again before phase 2: not requested twice
            self.assertEqual(F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "1b", ["gh"], False, defer=True)["decision"]["action"], "NO")
            fail = lambda cmd, **kw: types.SimpleNamespace(returncode=1, stderr="HTTP 403", stdout="")
            r2 = F.dispatch_pending(led, T0 + timedelta(hours=5, minutes=2), ["gh"], sleep=lambda s: None, runner=fail)
            self.assertEqual(r2["last_dispatch"]["result"], "FALLO")
            self.assertEqual(r2["pending_retry"]["key"], r2["last_dispatch"]["key"])
            r3 = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=6), "m", "2", ["gh"], False, defer=True)
            self.assertEqual((r3["decision"]["action"], r3["last_dispatch"]["result"]), ("REINTENTO", "PEDIDA"))
            ok = lambda cmd, **kw: types.SimpleNamespace(returncode=0, stderr="", stdout="")
            r4 = F.dispatch_pending(led, T0 + timedelta(hours=6, minutes=2), ["gh"], sleep=lambda s: None, runner=ok)
            self.assertEqual(r4["last_dispatch"]["result"], "OK")
            self.assertNotIn("pending_retry", r4)
            self.assertEqual(F.dispatch_pending(led, T0 + timedelta(hours=7), ["gh"], runner=ok)["phase2"]["action"], "NADA_PENDIENTE")



class NoChurn(unittest.TestCase):
    def test_unchanged_capture_does_not_rewrite_the_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "l.json"
            F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "1", ["gh"], False, defer=True)
            before = led.read_bytes()
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5, minutes=30), "m", "2", ["gh"], False, defer=True)
            self.assertEqual((r["decision"]["action"], r.get("written")), ("NO", False))
            self.assertEqual(led.read_bytes(), before)
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=13), "m", "3", ["gh"], False, defer=True)
            self.assertNotEqual(led.read_bytes(), before)  # becoming stale is a change worth recording

    def test_duplicate_after_successful_dispatch_is_not_requested_nor_written(self):
        """Real e2e sequence (run 42668802320): decide -> dispatch OK -> same capture again = NO, ledger bytes unchanged."""
        ok = lambda cmd, **kw: types.SimpleNamespace(returncode=0, stderr="", stdout="")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "l.json"
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "1", ["gh"], False, defer=True)
            self.assertEqual(r["decision"]["action"], "SI")
            F.dispatch_pending(led, T0 + timedelta(hours=5), ["gh"], runner=ok)
            before = led.read_bytes()
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5, minutes=10), "m", "dup", ["gh"], False, defer=True)
            self.assertEqual(r["decision"]["action"], "NO")
            self.assertIn("duplicada", r["decision"]["reason"])
            self.assertEqual(led.read_bytes(), before)
            self.assertEqual(json.loads(before)["last_dispatch"]["result"], "OK")

    def test_stale_pending_from_an_earlier_run_is_never_sent_again(self):
        """#504 flow: phase 2 success is not committed, so the committed ledger keeps PEDIDA. A later capture without new
        data leaves the file untouched (no churn); phase 2 of that later run must not send the old request again."""
        calls = []
        ok = lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=0, stderr="", stdout="")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "l.json"
            F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "run1", ["gh"], False, defer=True)
            committed = led.read_bytes()  # what the capture commit contains (PEDIDA)
            F.dispatch_pending(led, T0 + timedelta(hours=5), ["gh"], runner=ok, run_id="run1")
            self.assertEqual(len(calls), 1)
            led.write_bytes(committed)  # next run starts from the committed ledger
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5, minutes=30), "m", "run2", ["gh"], False, defer=True)
            self.assertEqual((r["decision"]["action"], r.get("written")), ("NO", False))
            r = F.dispatch_pending(led, T0 + timedelta(hours=5, minutes=30), ["gh"], runner=ok, run_id="run2")
            self.assertEqual(len(calls), 1)
            self.assertEqual(r["phase2"]["action"], "NADA_PENDIENTE")
            self.assertEqual(led.read_bytes(), committed)

    def test_dispatch_phase_without_run_id_does_nothing(self):
        calls = []
        ok = lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=0, stderr="", stdout="")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "l.json"
            F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "run1", ["gh"], False, defer=True)
            before = led.read_bytes()
            self.assertEqual(F.main(["--phase", "dispatch", "--catchments", str(d / "c.json"), "--ledger", str(led),
                                     "--dispatch-workflow", "x.yml", "--dispatch-ref", "research/x"]), 0)
            self.assertEqual(led.read_bytes(), before)


class Safety(unittest.TestCase):
    def test_original_archives_are_never_modified(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            c, n = d / "c.json", d / "n.json"
            c.write_text(json.dumps(archive(T0)), encoding="utf-8")
            n.write_text(json.dumps(archive(T0)), encoding="utf-8")
            before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (c, n)]
            ok = lambda cmd, **kw: types.SimpleNamespace(returncode=0, stderr="", stdout="")
            F.run_once(c, n, d / "l.json", T0 + timedelta(hours=5), "m", "1", ["gh"], False, runner=ok, defer=True)
            F.dispatch_pending(d / "l.json", T0 + timedelta(hours=5), ["gh"], runner=ok)
            self.assertEqual([hashlib.sha256(p.read_bytes()).hexdigest() for p in (c, n)], before)

    def test_truncated_and_empty_archives_never_trigger(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            full = json.dumps(archive(T0))
            for i, text in enumerate((full[: len(full) // 2], "", json.dumps(dict(granules=[], status={})))):
                (d / "c.json").write_text(text, encoding="utf-8")
                r = F.run_once(d / "c.json", None, d / f"l{i}.json", T0 + timedelta(hours=5), "m", "1", ["gh"], True)
                self.assertEqual(r["decision"]["action"], "NO", i)

    def test_live_refresh_workflow_serialises_runs_and_never_chains_after_capture(self):
        wf = (ROOT / ".github/workflows/v091-live-refresh.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:\n  group: v091-live-refresh\n  cancel-in-progress: false", wf)  # one at a time, none lost
        self.assertIn("needs.refresh.outputs.chain == 'true'", wf)                               # after_capture never chains
        self.assertIn("steps.src.outcome == 'failure'", wf)                                         # bad data -> package withdrawn

    def test_dry_run_decide_never_leaves_a_pending_request(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.json").write_text(json.dumps(archive(T0)), encoding="utf-8")
            led = d / "l.json"
            r = F.run_once(d / "c.json", None, led, T0 + timedelta(hours=5), "m", "1", None, True, defer=True)
            self.assertEqual((r["decision"]["action"], r["last_dispatch"]["result"]), ("SI", "SIMULADO"))
            calls = []
            ok = lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=0, stderr="", stdout="")
            self.assertEqual(F.dispatch_pending(led, T0 + timedelta(hours=5), ["gh"], runner=ok, run_id="1")["phase2"]["action"],
                             "NADA_PENDIENTE")
            self.assertEqual(calls, [])

    def test_stale_but_new_observation_is_rebuilt_and_labelled_stale(self):
        o = F.observation_state(archive(T0), b"x", T0 + timedelta(hours=20), "c")  # late backfill: new for us, but old
        self.assertEqual((o["freshness"], F.decide(None, o, "m")["action"]), ("CADUCADA", "SI"))

    def test_capture_workflow_serialises_runs_and_never_fails_on_freshness(self):
        wf = (ROOT / ".github/workflows/v09-rain-north.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:", wf)
        self.assertIn("cancel-in-progress: false", wf)
        self.assertEqual(wf.count("scripts/v091_capture_freshness.py"), 2)  # decide before the commit, dispatch after the push
        self.assertGreaterEqual(wf.count("continue-on-error: true"), 2)      # never breaks the capture
        self.assertIn("mode=after_capture", wf)
        self.assertNotIn("mode=chain", wf)

    def test_capture_workflow_commits_only_failed_requests_and_binds_the_run(self):
        wf = (ROOT / ".github/workflows/v09-rain-north.yml").read_text(encoding="utf-8")
        step = wf[wf.index("Request ONE private-viewer rebuild"):]
        self.assertNotIn("if: always()", step.split("- name:", 1)[0])  # no rebuild request when the capture was not pushed
        self.assertIn('--run-id "$GITHUB_RUN_ID"', step)
        self.assertIn("=='FALLO'", step)                                # a success is never committed (no churn)
        self.assertNotIn("git diff --quiet -- data/v09/rain/freshness_ledger_v0_1.json", step)

    def test_rebuild_switch_is_off_by_default_and_only_opens_for_isolated_manual_tests(self):
        import subprocess
        import textwrap
        wf = (ROOT / ".github/workflows/v09-rain-north.yml").read_text(encoding="utf-8")  # no PyYAML in CI: plain text

        def step(marker):
            i = wf.index(marker)
            j = wf.find("\n      - ", i)
            return wf[i:j if j > 0 else len(wf)]

        g = step("id: gate")
        gate = textwrap.dedent(g[g.index("run: |") + len("run: |") + 1:])
        send = step("Request ONE private-viewer rebuild")
        self.assertIn("if: steps.gate.outputs.on == 'true'", send)
        self.assertIn('DRY=--dry-run; [ "$GATE_ON" = true ] && DRY=""', step("Freshness ledger and rebuild decision"))

        def run(ref, event, switch="", viewer="", db=""):
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / "o"
                out.write_text("")
                env = dict(GITHUB_OUTPUT=str(out), GITHUB_REF_NAME=ref, GITHUB_EVENT_NAME=event, SWITCH=switch,
                           E2E_VIEWER_REF=viewer, E2E_TEST_DB=db, PATH="/usr/bin:/bin")
                subprocess.run(["bash", "-c", gate], env=env, check=True, capture_output=True)
                return dict(l.split("=", 1) for l in out.read_text().splitlines())

        self.assertEqual(run("main", "schedule")["on"], "false")                      # default: OFF
        # default target: a research viewer branch that accepts mode=after_capture (the 02-11 live branch only takes `hop`)
        self.assertEqual(run("main", "schedule", "true")["viewer_ref"], "research/v091-viewer-after-capture-20261110")
        self.assertNotIn("research/v091-live-integration-20261102", g)
        self.assertEqual(run("main", "workflow_dispatch", "", "research/x", "research/v091-live-data-test-1")["on"], "false")
        self.assertEqual(run("main", "schedule", "true")["on"], "true")              # only an explicit repository switch
        ok = run("research/v091-e2e-capture-1", "workflow_dispatch", "", "research/v091-int", "research/v091-live-data-test-1")
        self.assertEqual((ok["on"], ok["viewer_ref"]), ("true", "research/v091-int"))
        self.assertIn("source_ref=research/v091-e2e-capture-1", ok["extra"])
        for bad in (("research/v091-e2e-capture-1", "workflow_dispatch", "", "research/v091-int", "research/v091-live-data"),
                    ("research/v091-e2e-capture-1", "push", "", "research/v091-int", "research/v091-live-data-test-1"),
                    ("research/v091-e2e-capture-1", "workflow_dispatch", "", "main", "research/v091-live-data-test-1"),
                    ("research/other", "workflow_dispatch", "", "research/v091-int", "research/v091-live-data-test-1")):
            self.assertEqual(run(*bad)["on"], "false", bad)


if __name__ == "__main__":
    unittest.main()
