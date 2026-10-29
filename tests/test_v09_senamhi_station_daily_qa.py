"""IRFEN SENAMHI station QA: synthetic tests, NOT meteorological evidence."""
import importlib.util
import unittest
from datetime import date
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "scripts/v09_senamhi_station_daily_qa.py"
spec = importlib.util.spec_from_file_location("stationqa", FILE)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class StationDailyQA(unittest.TestCase):
    def test_missing_is_not_zero_and_october_extreme(self):
        raw = b"2026 10 1 0 29 20\n2026 10 2 -99.9 28 19\n2026 10 3 12.5 30 21\n"
        s = qa.report_station("000135", raw, date(2026, 10, 2))
        p = s["precipitation"]
        self.assertEqual((p["valid_days"], p["missing_sentinel_days"], p["explicit_zero_days"]), (2, 1, 1))
        self.assertEqual(p["october_max_daily_mm"]["mm"], 12.5)
        self.assertEqual(s["event_date_observation"]["status"], "MISSING_NOT_ZERO")

    def test_missing_calendar_day_does_not_mean_zero(self):
        s = qa.report_station("000132", b"2026 1 1 2 20 10\n2026 1 3 0 20 10\n", date(2026, 1, 2))
        self.assertEqual(s["missing_calendar_dates"], 1)
        self.assertEqual(s["event_date_observation"]["status"], "DATA_ABSENT")

    def test_malformed_nonfinite_and_impossible_dates_rejected(self):
        for line in ("2026 2 30 0 25 20", "2026 1 1 nan 25 20", "2026 1 1 0 20",
                     "2026 1 1 x 20 19"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                qa.parse_rows(line)

    def test_duplicate_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            qa.parse_rows("2026 10 1 0 29 20\n2026 10 1 5 29 20")

    def test_other_negative_precip_invalid_not_valid(self):
        s = qa.report_station("123", b"2026 1 1 -1 25 18\n")
        self.assertEqual(s["precipitation"]["invalid_negative_days"], 1)
        self.assertEqual(s["precipitation"]["valid_days"], 0)

    def test_temperature_reversal_flagged_no_rain_replacement(self):
        s = qa.report_station("000132", b"2014 10 10 0 21 26.5\n")
        self.assertEqual(s["temperature"]["max_below_min_dates"], ["2014-10-10"])
        self.assertEqual(s["precipitation"]["valid_days"], 1)

    def test_research_guards(self):
        self.assertEqual(qa.GUARDS["activation_gate"], "BLOCKED")
        self.assertEqual(qa.GUARDS["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(qa.GUARDS["decision_thresholds"])


if __name__ == "__main__":
    unittest.main()
