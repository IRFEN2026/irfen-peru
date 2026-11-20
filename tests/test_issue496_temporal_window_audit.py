"""Synthetic, offline tests; no claim of station or NASA scientific validation."""
import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

path = Path(__file__).resolve().parents[1] / "research/issue496/temporal_window_audit.py"
spec = importlib.util.spec_from_file_location("temporal_window_audit", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class WindowAuditTests(unittest.TestCase):
    def setUp(self):
        self.start = "2026-11-04T12:00:00Z"
        self.end = "2026-11-05T12:00:00Z"
        t = datetime(2026,11,4,12,tzinfo=timezone.utc)
        self.intervals = [(t + timedelta(minutes=30*i)).isoformat() for i in range(48)]

    def test_48_original_half_hours(self):
        a = mod.audit_window(self.start, self.end, self.intervals)
        self.assertTrue(a["complete"])
        self.assertEqual(a["expected_intervals"],48)
        self.assertTrue(a["start_pet"].startswith("2026-11-04T07:00"))
        self.assertFalse(a["missing_is_zero"])

    def test_missing_not_zero(self):
        a = mod.audit_window(self.start,self.end,self.intervals[:-1])
        self.assertFalse(a["complete"])
        self.assertEqual(len(a["missing_interval_starts_utc"]),1)

    def test_duplicate(self):
        a = mod.audit_window(self.start,self.end,self.intervals+[self.intervals[0]])
        self.assertEqual(len(a["duplicate_interval_starts_utc"]),1)

    def test_end_exclusive(self):
        a = mod.audit_window(self.start,self.end,self.intervals+[self.end])
        self.assertEqual(len(a["outside_or_misaligned_utc"]),1)

    def test_reject_naive(self):
        with self.assertRaises(ValueError):
            mod.audit_window("2026-11-04T12:00:00","2026-11-05T12:00:00Z",[])

    def test_reject_non_utc(self):
        with self.assertRaises(ValueError):
            mod.audit_window("2026-11-04T07:00:00-05:00",self.end,[])

    def test_seven_day_versus_eight_day_window(self):
        seven=mod.audit_window("2026-10-31T12:00:00Z","2026-11-07T12:00:00Z",[])
        eight=mod.audit_window("2026-10-30T12:00:00Z","2026-11-07T12:00:00Z",[])
        self.assertEqual(seven["expected_intervals"],336)
        self.assertEqual(eight["expected_intervals"],384)

if __name__ == "__main__":
    unittest.main()
