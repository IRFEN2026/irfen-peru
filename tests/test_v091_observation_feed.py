"""Contract tests for the IRFEN research-only observation freshness feed."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v091_build_observation_feed.py"
spec = importlib.util.spec_from_file_location("irfen_live_feed", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NOW = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)

def sample(root, spec_row, value, guards=None):
    row = {"deployment_status": "RESEARCH_ONLY", "production_use": False}
    if guards:
        row.update(guards)
    obj = row
    for key in spec_row["time_path"][:-1]:
        obj[key] = {}
        obj = obj[key]
    obj[spec_row["time_path"][-1]] = value
    target = root / spec_row["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(row), encoding="utf-8")

class LiveFeedTests(unittest.TestCase):
    def test_recent_archives_are_not_claimed_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for s in module.SOURCES:
                sample(root, s, "2026-11-02T02:15:00Z")
            result = module.build(root, NOW)
            byid = {s["id"]: s for s in result["sources"]}
            self.assertEqual(byid["avisos_indeci_coen"]["status"], "RECENT_ARCHIVED")
            self.assertEqual(byid["imerg_early_north"]["status"], "RECENT_ARCHIVED")
            self.assertEqual(byid["goes19_rrqpe_north"]["status"], "RECENT_ARCHIVED")
            self.assertEqual(byid["imerg_early_coast_snapshot"]["status"], "SNAPSHOT_ONLY")
            self.assertFalse(result["public_alerting"])
            self.assertFalse(result["predictive"])
            self.assertEqual(result["activation_gate"], "BLOCKED")

    def test_stale_missing_invalid_and_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = module.SOURCES
            sample(root, sources[0], "2026-11-01T22:00:00Z")
            sample(root, sources[1], "2026-11-02T05:00:00Z")
            sample(root, sources[2], "2026-11-02T02:55:00Z",
                   guards={"production_use": True})
            result = module.build(root, NOW)
            states = {s["id"]: s["status"] for s in result["sources"]}
            self.assertEqual(states["avisos_indeci_coen"], "STALE")
            self.assertEqual(states["imerg_early_north"], "INVALID_TIME")
            self.assertEqual(states["goes19_rrqpe_north"], "INVALID_GUARD")
            self.assertEqual(states["imerg_early_coast_snapshot"], "UNKNOWN")

    def test_as_of_roundtrip_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = Path("feed.json")
            self.assertEqual(module.main(["--root",str(root),"--output",str(out),
                                          "--as-of","2026-11-02T03:00:00Z"]), 0)
            self.assertEqual(module.main(["--root",str(root),"--output",str(out),
                                          "--as-of","2026-11-02T03:00:00Z","--check"]), 0)
            loaded=json.loads((root/out).read_text(encoding="utf-8"))
            self.assertEqual(len(loaded["sources"]), 4)
            self.assertTrue(all(x["status"]=="UNKNOWN" for x in loaded["sources"]))

if __name__=="__main__":
    unittest.main()
