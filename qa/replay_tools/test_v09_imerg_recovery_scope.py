"""Offline scope and isolation tests for the one-off IMERG recovery worker."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[2] / "scripts/v09_imerg_early_recover_34.py"
spec = importlib.util.spec_from_file_location("imerg_recovery_34", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def row(time, state="MISSING_RETRYING"):
    return {"product": "IMERG_EARLY_HH", "state": state,
            "interval_start_utc": time, "catalog": {"response_complete": True,
            "listed": [{"id": "NASA_ID", "title": "granule.V07B.HDF5"}]}}

class RecoveryScope(unittest.TestCase):
    def make34(self):
        from datetime import datetime, timedelta, timezone
        t = datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)
        return [row((t + timedelta(minutes=30*i)).isoformat().replace("+00:00", "Z")) for i in range(34)]

    def test_shard_is_16_16_2(self):
        entries = mod.expected_rows({"deployment_status": "RESEARCH_ONLY",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "intervals": self.make34()})
        self.assertEqual([len(mod.select_shard(entries, i)) for i in range(3)], [16, 16, 2])
        self.assertEqual(len({x["interval_start_utc"] for x in entries}), 34)

    def test_reject_extra_or_unauthorized_slots(self):
        cases = [self.make34()[:-1], self.make34() + [row("2026-10-17T00:00:00Z")],
                 self.make34()[:-1] + [row("2026-10-15T09:30:00Z")]]
        for entries in cases:
            with self.subTest(count=len(entries)), self.assertRaises(RuntimeError):
                mod.expected_rows({"deployment_status": "RESEARCH_ONLY",
                    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "intervals": entries})

    def test_reject_nonmissing_and_incomplete_catalog(self):
        entries = self.make34()
        entries[0]["state"] = "UNKNOWN"
        with self.assertRaises(RuntimeError):
            mod.expected_rows({"deployment_status": "RESEARCH_ONLY",
                "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "intervals": entries})
        entries[0]["state"] = "MISSING_RETRYING"
        entries[0]["catalog"]["response_complete"] = False
        with self.assertRaises(RuntimeError):
            mod.expected_rows({"deployment_status": "RESEARCH_ONLY",
                "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "intervals": entries})

    def test_reject_out_of_range_shards(self):
        with self.assertRaises(ValueError):
            mod.select_shard(self.make34(), 3)

    def test_fail_closed_catalog_mismatch(self):
        fake = types.ModuleType("probe_imerg_early_live")
        fake.timestamp_from_filename = lambda name: None
        with patch.dict(sys.modules, {"probe_imerg_early_live": fake}):
            with self.assertRaises(RuntimeError):
                mod.checked_catalog_match(self.make34()[0], {})

    def test_fixed_safety_guards(self):
        self.assertIs(mod.GUARDS["operational_alerting_enabled"], False)
        self.assertEqual(mod.GUARDS["activation_gate"], "BLOCKED")
        self.assertEqual(mod.GUARDS["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(mod.GUARDS["decision_thresholds"])

if __name__ == "__main__":
    unittest.main()
