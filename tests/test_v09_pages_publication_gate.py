"""IRFEN v0.9: merging the dashboard into main must not publish it on GitHub Pages until QA opens the gate."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_pages_publication_gate", ROOT / "scripts/v09_pages_publication_gate.py")
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)
BUNDLE_OK = dict(G.REQUIRED_BUNDLE_GUARDS)
OPEN = dict(publish_v09_dashboard=True, qa_approved_by="QA", qa_approved_at_utc="2026-10-18T12:00:00Z", public_alerting=False)


class Gate(unittest.TestCase):
    def test_committed_gate_is_closed(self):
        gate = json.loads(G.GATE.read_text(encoding="utf-8"))
        self.assertIs(gate["publish_v09_dashboard"], False)
        self.assertIsNone(gate["qa_approved_by"])
        self.assertIs(gate["public_alerting"], False)
        self.assertEqual((gate["deployment_status"], gate["test_mode"]), ("RESEARCH_ONLY", "TEST_ONLY"))

    def test_decision(self):
        self.assertTrue(G.decide(OPEN, BUNDLE_OK)[0])
        self.assertFalse(G.decide(None, BUNDLE_OK)[0])
        self.assertFalse(G.decide(dict(OPEN, publish_v09_dashboard="true"), BUNDLE_OK)[0])
        self.assertFalse(G.decide(dict(OPEN, qa_approved_by=None), BUNDLE_OK)[0])
        self.assertFalse(G.decide(dict(OPEN, public_alerting=True), BUNDLE_OK)[0])
        self.assertFalse(G.decide(OPEN, None)[0])
        for key in G.REQUIRED_BUNDLE_GUARDS:
            self.assertFalse(G.decide(OPEN, dict(BUNDLE_OK, **{key: "CHANGED"}))[0], key)

    def test_closed_gate_removes_the_dashboard_from_the_pages_workspace_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("site/v09/index.html", "site/data/v09/dashboard_v0_1.json", "site/index.html", "config/v09_public_demo_v0_1.json"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / "site/v09/index.html").write_text("x")
            (root / "site/index.html").write_text("x")
            (root / "site/data/v09/dashboard_v0_1.json").write_text(json.dumps(BUNDLE_OK))
            (root / "config/v09_public_demo_v0_1.json").write_text(json.dumps(dict(OPEN, publish_v09_dashboard=False)))
            with contextlib.redirect_stdout(io.StringIO()):  # keep synthetic gate notices out of CI annotations
                G.main(["--dry-run"], root=root)
            self.assertTrue((root / "site/v09").exists())
            with contextlib.redirect_stdout(io.StringIO()):
                G.main([], root=root)
            self.assertFalse((root / "site/v09").exists())
            self.assertFalse((root / "site/data/v09").exists())
            self.assertTrue((root / "site/index.html").exists())

    def test_open_gate_keeps_the_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "site/v09").mkdir(parents=True)
            (root / "site/data/v09").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "site/data/v09/dashboard_v0_1.json").write_text(json.dumps(BUNDLE_OK))
            (root / "config/v09_public_demo_v0_1.json").write_text(json.dumps(OPEN))
            with contextlib.redirect_stdout(io.StringIO()):
                G.main([], root=root)
            self.assertTrue((root / "site/v09").exists())

    def test_open_panel_gate_does_not_publish_the_territorial_viewer(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("site/v09/index.html", "site/v09/territorio.html", "site/v09/shared_rules.js", "site/data/v09/territory_v0_1.json"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("{}")
            (root / "config").mkdir()
            (root / "site/data/v09/dashboard_v0_1.json").write_text(json.dumps(BUNDLE_OK))
            (root / "config/v09_public_demo_v0_1.json").write_text(json.dumps(OPEN))
            with contextlib.redirect_stdout(io.StringIO()):
                G.main([], root=root)
            self.assertTrue((root / "site/v09/index.html").exists())
            for rel in G.TERRITORY_PATHS:
                self.assertFalse((root / rel).exists(), rel)
        self.assertFalse(G.decide_territory(dict(publish_v09_territory=True), {})[0])
        self.assertTrue(G.decide_territory(dict(publish_v09_territory=True, territory_qa_approved_by="QA", territory_qa_approved_at_utc="x"),
                                           dict(BUNDLE_OK, map_publishable=False))[0])

    def test_committed_gate_keeps_the_territorial_viewer_closed(self):
        gate = json.loads((ROOT / "config/v09_public_demo_v0_1.json").read_text(encoding="utf-8"))
        self.assertIsNot(gate.get("publish_v09_territory"), True)

    def test_every_pages_workflow_runs_the_gate_before_upload(self):
        for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
            text = wf.read_text(encoding="utf-8")
            if "upload-pages-artifact" not in text:
                continue
            self.assertIn("python scripts/v09_pages_publication_gate.py", text, wf.name)
            self.assertLess(text.index("v09_pages_publication_gate.py"), text.index("upload-pages-artifact"), wf.name)

    def test_committed_bundle_keeps_the_guards(self):
        bundle = json.loads(G.BUNDLE.read_text(encoding="utf-8"))
        self.assertEqual({k: bundle.get(k) for k in G.REQUIRED_BUNDLE_GUARDS}, G.REQUIRED_BUNDLE_GUARDS)


if __name__ == "__main__":
    unittest.main()
