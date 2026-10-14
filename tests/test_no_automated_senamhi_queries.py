"""Owner decision 13-10-2026: no automated direct queries to SENAMHI hosts.

The official-outcome archive and the Piura source-status collector keep their other sources (INDECI/COEN, ANIN,
IGP-CENDEHUA, PECHP, GORE Piura) and never request a SENAMHI host unless IRFEN_SENAMHI_DIRECT_ACCESS=enabled is set
explicitly, which no workflow does. Skipped SENAMHI sources are recorded as unknown, never as zero. Offline: every
HTTP call is intercepted (SYNTHETIC responses).
"""
import importlib.util
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OUTCOME = load("archive_official_outcome_sources")
PIURA = load("fetch_piura_source_status")
NOW = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)


class OutcomeArchive(unittest.TestCase):
    def test_senamhi_sources_are_not_requested_and_stay_unknown(self):
        requested = []

        def fake_fetch(sources, captured_at, snapshot_date):
            requested.extend(s["url"] for s in sources)
            return [dict(source_id=s["source_id"], url=s["url"], capture_status="CAPTURED") for s in sources]

        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(OUTCOME, "fetch_sources", side_effect=fake_fetch):
            os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
            rows = OUTCOME.fetch_policy_sources(NOW, "2026-10-13")
        self.assertFalse([u for u in requested if "senamhi.gob.pe" in u])
        self.assertIn("https://portal.indeci.gob.pe/emergencias/", requested)
        self.assertEqual([r["source_id"] for r in rows], [s["source_id"] for s in OUTCOME.SOURCES])  # order kept
        for r in rows:
            if r["source_id"] in OUTCOME.SENAMHI_DIRECT_SOURCE_IDS:
                self.assertEqual(r["capture_status"], "NOT_QUERIED_POLICY")
                self.assertIs(r["unknown_not_zero"], True)
            else:
                self.assertEqual(r["capture_status"], "CAPTURED")

    def test_explicit_opt_in_is_the_only_way(self):
        requested = []
        fake = lambda sources, *a: requested.extend(s["url"] for s in sources) or []
        with mock.patch.dict(os.environ, {"IRFEN_SENAMHI_DIRECT_ACCESS": "enabled"}), mock.patch.object(OUTCOME, "fetch_sources", side_effect=fake):
            OUTCOME.fetch_policy_sources(NOW, "2026-10-13")
        self.assertTrue(any("senamhi.gob.pe" in u for u in requested))
        for value in ("1", "true", "yes", "ENABLED"):
            with mock.patch.dict(os.environ, {"IRFEN_SENAMHI_DIRECT_ACCESS": value}):
                self.assertFalse(OUTCOME.senamhi_direct_access_enabled(), value)


class PiuraSourceStatus(unittest.TestCase):
    def test_gore_piura_kept_senamhi_not_requested(self):
        calls = []

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return [{"fkey": "2026-10-13"}]

        def fake_get(url, **kw):
            calls.append(url)
            if "senamhi.gob.pe" in url:
                raise AssertionError("SENAMHI host requested")
            return Resp()

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "piura_source_status.json"
            out.write_text(json.dumps(dict(senamhi=dict(latest_forecast_bulletin_date="2026-03-01",
                                                        latest_verified_forecast_bulletin_url="https://example.invalid/b.pdf",
                                                        forecast_catalog_document_checks=[dict(document_status="VERIFIED_HYDROLOGICAL_BULLETIN",
                                                                                               catalog_date="2026-03-01",
                                                                                               url="https://example.invalid/b.pdf")]))))
            env = {k: v for k, v in os.environ.items() if k != "IRFEN_SENAMHI_DIRECT_ACCESS"}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(PIURA, "OUT", out), \
                    mock.patch.object(PIURA.requests, "get", side_effect=fake_get), mock.patch("builtins.print"):
                PIURA.main()
            status = json.loads(out.read_text())
        self.assertTrue(calls and all("regionpiura.gob.pe" in u for u in calls))
        self.assertEqual(status["gore_piura"]["catalog_status"], "available")
        sen = status["senamhi"]
        self.assertEqual(sen["forecast_page_access_status"], "not_queried_policy")
        self.assertIs(sen["forecast_bulletin_stale"], True)  # the last verified bulletin is carried forward as stale
        self.assertIs(sen["numeric_river_state_available"], False)


class Workflows(unittest.TestCase):
    def test_no_workflow_enables_direct_senamhi_access(self):
        for wf in (ROOT / ".github/workflows").glob("*.yml"):
            self.assertNotRegex(wf.read_text(encoding="utf-8"), r"IRFEN_SENAMHI_DIRECT_ACCESS\s*:\s*['\"]?enabled", wf.name)

    def test_collectors_request_senamhi_only_behind_the_policy(self):
        for name in ("archive_official_outcome_sources", "fetch_piura_source_status"):
            code = (ROOT / f"scripts/{name}.py").read_text(encoding="utf-8")
            self.assertIn("IRFEN_SENAMHI_DIRECT_ACCESS", code)
            self.assertTrue(re.search(r"senamhi_direct_access_enabled\(\)", code))


class EveryWorkflowThatCanReachSenamhi(unittest.TestCase):
    """A workflow that runs a script naming a SENAMHI host either goes through the policy gate (default disabled)
    or can only be started by hand (workflow_dispatch). Push triggers were removed on 14-10-2026: a push to main
    touching e.g. site/data/latest.json started the WIS2 discovery without anyone deciding it."""

    HOST = re.compile(r"https?://[\w.-]*senamhi\.gob\.pe")
    # Scripts that only carry a SENAMHI URL as data (synthetic review fixtures), with no HTTP client.
    URL_AS_DATA_ONLY = ("run_v08_regression_tests",)

    def _workflows(self):
        for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
            text = wf.read_text(encoding="utf-8")
            block = re.search(r"^on:[ \t]*(.*?)\n(.*?)(?=^\S)", text, re.S | re.M)  # no PyYAML in the CI image
            inline = block.group(1).strip()
            if inline:
                triggers = set(re.findall(r"[\w]+", inline))
            else:
                triggers = set(re.findall(r"^  ([a-z_]+):", block.group(2), re.M))
            scripts = [s for s in sorted(set(re.findall(r"scripts/(\w+)\.py", text))) if (ROOT / f"scripts/{s}.py").is_file()]
            yield wf.name, triggers, [s for s in scripts if self.HOST.search((ROOT / f"scripts/{s}.py").read_text(encoding="utf-8"))]

    def test_ungated_senamhi_scripts_are_manual_only(self):
        seen = []
        for name, triggers, scripts in self._workflows():
            for s in scripts:
                code = (ROOT / f"scripts/{s}.py").read_text(encoding="utf-8")
                if "senamhi_direct_access_enabled()" in code:
                    continue  # behind the policy gate, disabled by default
                if s in self.URL_AS_DATA_ONLY:
                    self.assertNotRegex(code, r"import requests|urllib\.request|urlopen|http\.client|httpx", s)
                    continue
                seen.append(name)
                self.assertEqual(triggers, {"workflow_dispatch"}, f"{name} runs {s} (SENAMHI host) and can start without a person")
        self.assertIn("senamhi-wis2-discovery.yml", seen)

    def test_fallback_never_dispatches_them(self):
        spec = importlib.util.spec_from_file_location("scheduler_fallback", ROOT / "scripts/scheduler_fallback.py")
        fb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fb)
        for name, _, scripts in self._workflows():
            if scripts and name not in ("pr-validation.yml", "update-and-deploy.yml"):
                self.assertNotIn(name, fb.TARGETS)


if __name__ == "__main__":
    unittest.main()
