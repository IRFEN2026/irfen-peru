import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "site/data/phase2/source_assessments/rimac_jicamarca_probe_freeze_manifest_v0_1.json"

class RimacJicamarcaProbeFreezeTests(unittest.TestCase):
    def setUp(self):
        self.m = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_fail_closed_guards(self):
        m=self.m
        self.assertEqual(m["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(m["test_mode"], "TEST_ONLY")
        self.assertFalse(m["production_use"])
        self.assertFalse(m["production_ready"])
        self.assertFalse(m["operational_alerting_enabled"])
        self.assertEqual(m["activation_gate"], "BLOCKED")
        self.assertFalse(m["map_publication_authorized"])
        self.assertFalse(m["routing_enabled"])
        self.assertFalse(m["capacity_inference_enabled"])
        self.assertFalse(m["thresholds_enabled"])
        self.assertFalse(m["raw_source_bytes_frozen"])
        self.assertTrue(m["probe_output_bytes_frozen"])

    def test_snapshot_hashes_match(self):
        for row in self.m["probes"].values():
            p=ROOT / row["path"]
            self.assertTrue(p.is_file(), p)
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), row["sha256"])

    def test_minam_zero_is_not_absence(self):
        row=self.m["probes"]["minam_huaycoloro_rimac"]
        d=json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))
        self.assertTrue(d["query_completed"])
        self.assertEqual(d["candidate_counts"], {"huaycoloro":0,"rimac":0})
        self.assertFalse(d["guards"]["zero_query_result_may_be_inferred_as_hydrologic_absence"])
        self.assertFalse(d["guards"]["map_publish_enabled"])
        self.assertEqual(row["interpretation"], "ZERO_RESULTS_NOT_HYDROLOGIC_ABSENCE")

    def test_ana_unavailable_is_not_negative(self):
        row=self.m["probes"]["ana_rimac_hydrography"]
        d=json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))
        self.assertFalse(d["query_completed"])
        self.assertEqual(d["status"], "SOURCE_ACCESS_UNAVAILABLE")
        self.assertTrue(all(v is None for v in d["candidate_counts"].values()))
        self.assertFalse(d["access"]["zero_candidates_inferred"])
        self.assertFalse(d["access"]["hydrologic_absence_inferred"])
        self.assertEqual(row["interpretation"], "SOURCE_UNAVAILABLE_NOT_NEGATIVE")

if __name__ == "__main__":
    unittest.main()
