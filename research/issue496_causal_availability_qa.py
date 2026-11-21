"""Offline causal-availability QA for research forecasts. No network or production imports."""
from datetime import datetime, timezone
import unittest

UTC = timezone.utc
LEADS_HOURS = (1, 3, 6, 12, 24)

def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("explicit UTC offset required")
    return result.astimezone(UTC)

def assess_forecast(record):
    """Return NO_EVALUABLE instead of silently using future or unavailable evidence."""
    try:
        issue = parse_utc(record["issued_at_utc"])
        received = parse_utc(record["received_at_utc"])
        target_start = parse_utc(record["target_start_utc"])
        target_end = parse_utc(record["target_end_utc"])
        lead = record["lead_hours"]
        if type(lead) is not int or lead not in LEADS_HOURS:
            raise ValueError("unsupported lead")
        if received < issue or target_start < issue or target_end <= target_start:
            raise ValueError("invalid forecast chronology")
        if (target_start - issue).total_seconds() != lead * 3600:
            raise ValueError("lead does not match target start")
        if received > target_start:
            raise ValueError("forecast arrived after target began")
        inputs = record["inputs"]
        if not isinstance(inputs, list) or not inputs:
            raise ValueError("no inputs")
        for item in inputs:
            observed_end = parse_utc(item["observed_end_utc"])
            available = parse_utc(item["available_at_utc"])
            if available < observed_end:
                raise ValueError("availability before observation end")
            if observed_end > issue or available > issue:
                raise ValueError("future or unavailable input")
            if not item.get("source") or not item.get("sha256"):
                raise ValueError("missing provenance")
        return "ELIGIBLE_FOR_EVALUATION"
    except (ValueError, KeyError, TypeError, AttributeError):
        return "NO_EVALUABLE"

class CausalAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.record = dict(
            issued_at_utc="2026-11-05T12:00:00Z",
            received_at_utc="2026-11-05T12:01:00Z",
            target_start_utc="2026-11-05T15:00:00Z",
            target_end_utc="2026-11-05T16:00:00Z",
            lead_hours=3,
            inputs=[dict(source="IMERG_EARLY", sha256="abc",
                         observed_end_utc="2026-11-05T11:30:00Z",
                         available_at_utc="2026-11-05T11:55:00Z")])
    def test_valid_causal_record(self):
        self.assertEqual(assess_forecast(self.record), "ELIGIBLE_FOR_EVALUATION")
    def test_future_observation(self):
        self.record["inputs"][0]["observed_end_utc"] = "2026-11-05T12:30:00Z"
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")
    def test_late_availability(self):
        self.record["inputs"][0]["available_at_utc"] = "2026-11-05T12:10:00Z"
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")
    def test_late_receipt(self):
        self.record["received_at_utc"] = "2026-11-05T15:01:00Z"
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")
    def test_naive_timestamp(self):
        self.record["issued_at_utc"] = "2026-11-05T12:00:00"
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")
    def test_wrong_lead(self):
        self.record["lead_hours"] = 6
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")
    def test_missing_provenance(self):
        self.record["inputs"][0]["sha256"] = ""
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")
    def test_availability_before_end(self):
        self.record["inputs"][0]["available_at_utc"] = "2026-11-05T11:00:00Z"
        self.assertEqual(assess_forecast(self.record), "NO_EVALUABLE")

if __name__ == "__main__":
    unittest.main()
