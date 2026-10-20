"""Frozen QA snapshot of the capture ledger (2026-10-13 to 2026-10-20): provenance, reproducibility and reviewed counts.

The snapshot was produced once on ubuntu-24.04 by github-actions[bot] from real NASA CMR and NOAA S3 catalog answers
(metadata only). These tests never touch the network.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_capture_ledger", ROOT / "scripts/v09_capture_ledger.py")
L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(L)
SNAP = ROOT / "data/v09/capture_ledger/snapshots/20261013T0000Z_20261020T0000Z"


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


class FrozenSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = L.load_contract()
        cls.manifest = json.loads((SNAP / "requests.json").read_text(encoding="utf-8"))
        cls.ledger = json.loads((SNAP / "ledger_v0_1.json").read_text(encoding="utf-8"))

    def test_every_stored_response_matches_its_sha256(self):
        self.assertEqual(len(self.manifest["requests"]), 170)
        for r in self.manifest["requests"]:
            self.assertTrue(r["ok"], r["request_id"])
            data = (SNAP / "raw" / f"{r['sha256']}.bin").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), r["sha256"], r["request_id"])
            self.assertEqual(len(data), r["bytes"], r["request_id"])
        self.assertEqual(self.ledger["responses_manifest_sha256"], hashlib.sha256((SNAP / "requests.json").read_bytes()).hexdigest())

    def test_only_catalog_metadata_was_requested(self):
        for r in self.manifest["requests"]:
            L.check_url(r["url"], self.contract)
        self.assertEqual(self.manifest["downloads_of_granules_or_scans"], 0)
        self.assertEqual(self.ledger["downloads_of_granules_or_scans"], 0)
        self.assertIs(self.ledger["contains_precipitation_values"], False)
        for k, v in L.GUARDS.items():
            self.assertEqual(self.manifest[k], v)
            self.assertEqual(self.ledger[k], v)

    def test_cmr_answer_was_complete(self):
        cmr = [r for r in self.manifest["requests"] if r["product"] == "IMERG_EARLY_HH"]
        hits = int(cmr[0]["response_headers"]["CMR-Hits"])
        entries = sum(len(L.parse_cmr((SNAP / "raw" / f"{r['sha256']}.bin").read_bytes())["entries"]) for r in cmr)
        self.assertEqual(hits, entries)

    def test_classification_re_derives_exactly_from_the_stored_answers(self):
        again = L.build(SNAP, self.contract, root=ROOT, frozen_captures=L.frozen_captures_from(self.ledger))
        for key in ("intervals", "summary", "requests", "window", "responses_manifest_sha256", "states"):
            self.assertEqual(json.dumps(again[key], sort_keys=True), json.dumps(self.ledger[key], sort_keys=True), key)

    def test_reviewed_counts(self):
        s = self.ledger["summary"]
        self.assertEqual(s["IMERG_EARLY_HH"]["intervals"], 336)
        self.assertEqual(s["IMERG_EARLY_HH"]["by_state"], dict(CAPTURED=300, PENDING_SOURCE_LATENCY=1, MISSING_RETRYING=34,
                                                                ABSENT_AT_SOURCE=1, UNRECOVERABLE=0, UNKNOWN=0))
        self.assertEqual(s["GOES19_RRQPEF"]["intervals"], 1008)
        self.assertEqual(s["GOES19_RRQPEF"]["by_state"], dict(CAPTURED=71, PENDING_SOURCE_LATENCY=0, MISSING_RETRYING=937,
                                                               ABSENT_AT_SOURCE=0, UNRECOVERABLE=0, UNKNOWN=0))

    def test_the_only_absence_is_bracketed_by_listed_neighbours(self):
        rows = [r for r in self.ledger["intervals"] if r["product"] == "IMERG_EARLY_HH"]
        idx = [i for i, r in enumerate(rows) if r["state"] == "ABSENT_AT_SOURCE"]
        self.assertEqual([rows[i]["interval_start_utc"] for i in idx], ["2026-10-19T15:00:00Z"])
        i = idx[0]
        self.assertTrue(rows[i - 1]["catalog"]["listed"])
        self.assertTrue(rows[i]["catalog"]["response_complete"])
        self.assertEqual(rows[i]["catalog"]["listed"], [])

    def test_captured_evidence_exists_in_its_commit(self):
        # Checks every evidence commit present in this clone; validate uses a depth-1 clone, where none are present.
        cache, checked = {}, 0
        for r in self.ledger["intervals"]:
            for e in r["captured"]:
                key = (e["git_commit"], e["archive"])
                if key not in cache:
                    if git("cat-file", "-e", f"{e['git_commit']}^{{commit}}").returncode != 0:
                        cache[key] = None
                        continue
                    out = git("show", f"{e['git_commit']}:{e['archive']}")
                    self.assertEqual(out.returncode, 0, key)
                    cache[key] = out.stdout
                if cache[key] is None:
                    continue
                self.assertIn(e["item"], cache[key], (r["interval_start_utc"], key))
                checked += 1
        if not checked:
            self.skipTest("no evidence commit available in this clone (shallow)")

    def test_no_precipitation_values_in_the_snapshot_ledger(self):
        text = (SNAP / "ledger_v0_1.json").read_text(encoding="utf-8")
        for token in ('"rate_mm_h"', '"rate_mean_mm_h"', '"rate_max_mm_h"', '"accum_mm"', '"precipitation"', '"targets"'):
            self.assertNotIn(token, text)
        self.assertFalse(re.search(r'"mm_?h?r?"\s*:', text))


if __name__ == "__main__":
    unittest.main()
