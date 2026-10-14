import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "v08-scheduler-fallback.yml"
SPEC = importlib.util.spec_from_file_location("scheduler_fallback", ROOT / "scripts/scheduler_fallback.py")
FB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FB)
NOW = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)


def run_at(minutes_ago, status="completed", event="schedule"):
    return dict(status=status, event=event, created_at=(NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z"))


class V08SchedulerFallbackWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()

    def test_trigger_is_scoped_to_authenticated_owner_and_dedicated_issue(self):
        self.assertIn("issues:", self.text)
        self.assertIn("types: [opened, edited, reopened]", self.text)
        self.assertIn("github.actor == 'IRFEN2026'", self.text)
        self.assertIn("[automation] IRFEN v0.8 evidence sweep", self.text)
        self.assertIn("IRFEN_V08_EVIDENCE_SWEEP", self.text)
        self.assertNotIn("schedule:", self.text)  # not an independent scheduler

    def test_permissions_are_minimal_for_dispatch(self):
        self.assertIn("contents: read", self.text)
        self.assertIn("actions: write", self.text)
        self.assertNotIn("contents: write", self.text)

    def test_no_repository_wide_schedule_gate(self):
        # Replaced on purpose (v0.9): a recent run of another workflow must not stop a stale one.
        self.assertNotIn("event=schedule&per_page=1", self.text)
        self.assertNotIn("schedule_age_seconds", self.text)
        self.assertIn("python scripts/scheduler_fallback.py", self.text)

    def test_safety_contract_is_checked_before_dispatch(self):
        self.assertIn('contract.get("production_use") is False', self.text)
        self.assertIn('["san_ildefonso", "chosica", "catacaos"]', self.text)
        self.assertIn("all v0.8 recommendations remain TEST_ONLY", self.text)
        self.assertIn("phase-2 candidates remain RESEARCH_ONLY", self.text)
        self.assertIn("config/v09_senamhi_avisos_contract_v0_1.json", self.text)
        self.assertIn('"operational_alerting_enabled": False', self.text)
        self.assertLess(self.text.index("Verificar guardas v0.9"), self.text.index("python scripts/scheduler_fallback.py"))

    def test_targets_and_cooldowns(self):
        expected = {
            "igp-cendehua-probe.yml": 5400, "goes19-rrqpe-probe.yml": 5400,
            "imerg-early-probe.yml": 5400, "shadow-validation.yml": 7200,
            "geos-forecast.yml": 90000,
            "v09-senamhi-avisos-capture.yml": 3600, "v09-rain-north.yml": 3600,
        }
        self.assertEqual(FB.TARGETS, expected)

    def test_no_target_queries_senamhi_directly(self):
        """Owner decision 13-10-2026: the fallback never triggers automated direct queries to SENAMHI hosts."""
        import re
        for wf in FB.TARGETS:
            text = (ROOT / ".github/workflows" / wf).read_text(encoding="utf-8")
            for script in sorted(set(re.findall(r"scripts/[A-Za-z0-9_]+\.py", text))):
                path = ROOT / script
                if not path.is_file():
                    continue
                code = path.read_text(encoding="utf-8")
                calls = re.search(r"urlopen|requests\.(get|post|Session)|session\.(get|post)|Request\(", code)
                self.assertFalse(bool(calls) and "senamhi.gob.pe" in code, f"{wf} runs {script}, which requests a SENAMHI host")
        for wf in FB.EXCLUDED_DIRECT_SENAMHI:
            self.assertNotIn(wf, FB.TARGETS)
            self.assertEqual(FB.decide(wf, 60, True, [], NOW), (False, "EXCLUDED: direct SENAMHI queries are not automated"))

    def test_fallback_never_publishes_pages(self):
        for wf in FB.TARGETS:
            self.assertNotIn("upload-pages-artifact", (ROOT / ".github/workflows" / wf).read_text(encoding="utf-8"), wf)
        self.assertIn("update-and-deploy.yml", FB.EXCLUDED_PAGES_DEPLOY)
        self.assertFalse(FB.decide("update-and-deploy.yml", 0, True, [], NOW)[0])

    def test_each_dispatch_is_annotated(self):
        import contextlib, io, os
        from unittest import mock
        buf = io.StringIO()
        fake = [dict(workflow="v09-rain-north.yml", dispatched=True, would_dispatch=True, reason="STALE: x"),
                dict(workflow="geos-forecast.yml", dispatched=False, would_dispatch=False, reason="COOLDOWN: y")]
        with mock.patch.dict(os.environ, {"GH_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}), mock.patch.object(FB, "run", return_value=fake), \
                contextlib.redirect_stdout(buf):
            FB.main([])
        out = buf.getvalue()
        self.assertIn("::notice title=FALLBACK_DISPATCH::v09-rain-north.yml | STALE: x", out)
        self.assertNotIn("FALLBACK_DISPATCH::geos-forecast.yml", out)

    def test_nacara_probe_has_no_automatic_trigger(self):
        text = (ROOT / ".github/workflows/senamhi-nacara-probe.yml").read_text(encoding="utf-8")
        on_block = text.split("\npermissions:")[0]
        self.assertIn("workflow_dispatch:", on_block)
        self.assertNotIn("schedule:", on_block)
        self.assertNotIn("push:", on_block)


class PerWorkflowDecision(unittest.TestCase):
    def test_stale_workflow_is_dispatched(self):
        go, reason = FB.decide("v09-senamhi-avisos-capture.yml", 3600, True, [run_at(500)], NOW)
        self.assertTrue(go)
        self.assertTrue(reason.startswith("STALE"))

    def test_cooldown_and_any_event_counts(self):
        go, reason = FB.decide("v09-senamhi-avisos-capture.yml", 3600, True, [run_at(500), run_at(20, event="workflow_dispatch")], NOW)
        self.assertFalse(go)
        self.assertTrue(reason.startswith("COOLDOWN"))

    def test_active_or_queued_run_is_never_duplicated(self):
        for status in FB.ACTIVE_STATUSES:
            go, reason = FB.decide("imerg-early-probe.yml", 5400, True, [run_at(900), run_at(1, status=status)], NOW)
            self.assertFalse(go, status)
            self.assertTrue(reason.startswith("ACTIVE_RUN"))

    def test_workflow_missing_on_main_is_not_dispatched(self):
        go, reason = FB.decide("v09-rain-north.yml", 3600, False, [], NOW)
        self.assertFalse(go)
        self.assertTrue(reason.startswith("NOT_ON_MAIN"))

    def test_never_run_but_present_is_dispatched(self):
        self.assertEqual(FB.decide("x.yml", 3600, True, [], NOW), (True, "NO_RUN_ON_MAIN_YET"))

    def test_disabled_workflow_is_never_dispatched(self):
        for state in ("disabled_manually", "disabled_inactivity", "not_found", "error_403"):
            go, reason = FB.decide("imerg-early-probe.yml", 5400, True, [run_at(900)], NOW, state)
            self.assertFalse(go, state)
            self.assertTrue(reason.startswith("DISABLED"))


class FakeApi:
    def __init__(self, runs, states=None):
        self._runs, self.dispatched, self.queried, self._states = runs, [], [], states or {}

    def state(self, workflow):
        return self._states.get(workflow, "active")

    def runs(self, workflow):
        self.queried.append(workflow)
        return self._runs.get(workflow, [])

    def dispatch(self, workflow):
        self.dispatched.append(workflow)


class Sweep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for wf in FB.TARGETS:
            if wf != "v09-rain-north.yml":  # simulate: not yet on main
                (self.dir / wf).write_text("name: x\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_workflow_is_judged_on_its_own_history(self):
        runs = {wf: [run_at(10)] for wf in FB.TARGETS}  # everything ran recently ...
        runs["v09-senamhi-avisos-capture.yml"] = [run_at(8 * 60)]  # ... except the aviso capture (8 h)
        api = FakeApi(runs)
        report = FB.run(api, NOW, dry_run=False, workflows_dir=self.dir)
        self.assertEqual(api.dispatched, ["v09-senamhi-avisos-capture.yml"])
        self.assertNotIn("v09-rain-north.yml", api.queried)
        rain = next(r for r in report if r["workflow"] == "v09-rain-north.yml")
        self.assertFalse(rain["dispatched"])
        self.assertTrue(rain["reason"].startswith("NOT_ON_MAIN"))

    def test_dry_run_dispatches_nothing(self):
        api = FakeApi({})
        report = FB.run(api, NOW, dry_run=True, workflows_dir=self.dir)
        self.assertEqual(api.dispatched, [])
        self.assertTrue(all(r["would_dispatch"] for r in report if r["workflow"] in FB.TARGETS and r["workflow"] != "v09-rain-north.yml"))
        excluded = [r for r in report if r["workflow"] in FB.EXCLUDED_DIRECT_SENAMHI + FB.EXCLUDED_PAGES_DEPLOY]
        self.assertEqual(len(excluded), 4)
        self.assertTrue(all(not r["would_dispatch"] and r["reason"].startswith("EXCLUDED") for r in excluded))
        self.assertTrue(set(FB.EXCLUDED_DIRECT_SENAMHI).isdisjoint(api.queried))

    def test_disabled_workflow_is_skipped_and_the_sweep_continues(self):
        runs = {wf: [run_at(8 * 60)] for wf in FB.TARGETS}
        api = FakeApi(runs, states={"igp-cendehua-probe.yml": "disabled_manually"})
        report = FB.run(api, NOW, dry_run=False, workflows_dir=self.dir)
        self.assertNotIn("igp-cendehua-probe.yml", api.dispatched)
        self.assertIn("v09-senamhi-avisos-capture.yml", api.dispatched)
        igp = next(r for r in report if r["workflow"] == "igp-cendehua-probe.yml")
        self.assertTrue(igp["reason"].startswith("DISABLED"))

    def test_rain_north_is_dispatched_once_it_exists_on_main(self):
        (self.dir / "v09-rain-north.yml").write_text("name: x\n")
        api = FakeApi({wf: [run_at(10)] for wf in FB.TARGETS if wf != "v09-rain-north.yml"})
        FB.run(api, NOW, dry_run=False, workflows_dir=self.dir)
        self.assertEqual(api.dispatched, ["v09-rain-north.yml"])


if __name__ == "__main__":
    unittest.main()
