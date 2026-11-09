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

    def test_capture_workflow_serialises_runs_and_never_fails_on_freshness(self):
        wf = (ROOT / ".github/workflows/v09-rain-north.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:", wf)
        self.assertIn("cancel-in-progress: false", wf)
        self.assertEqual(wf.count("scripts/v091_capture_freshness.py"), 2)  # decide before the commit, dispatch after the push
        self.assertGreaterEqual(wf.count("continue-on-error: true"), 2)      # never breaks the capture
        self.assertIn("mode=after_capture", wf)
        self.assertNotIn("mode=chain", wf)

    def test_stale_but_new_observation_is_rebuilt_and_labelled_stale(self):
        o = F.observation_state(archive(T0), b"x", T0 + timedelta(hours=20), "c")  # late backfill: new for us, but old
        self.assertEqual((o["freshness"], F.decide(None, o, "m")["action"]), ("CADUCADA", "SI"))


if __name__ == "__main__":
    unittest.main()
