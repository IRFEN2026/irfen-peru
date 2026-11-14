"""Synthetic tests only: no claim of real station pairs."""
import hashlib
import unittest

from scripts.issue496_observation_provenance_gate import evaluate

RAW = b"synthetic instrument record"
BASE = {
    "station_id": "TEST-001",
    "observed_mm": 25.0,
    "period_start_utc": "2026-11-04T12:00:00Z",
    "period_end_utc": "2026-11-05T12:00:00Z",
    "observed_at_utc": "2026-11-05T12:00:00Z",
    "available_at_utc": "2026-11-05T13:00:00Z",
    "source_kind": "instrumental_original",
    "source_sha256": hashlib.sha256(RAW).hexdigest(),
    "latitude": -3.5,
    "longitude": -80.5,
    "datum": "WGS84",
    "unit": "mm",
    "instrument_qc": "PASS",
    "product_version": "instrument-1",
}


class ProvenanceGateTest(unittest.TestCase):
    def test_valid_synthetic(self):
        self.assertEqual(evaluate(BASE, RAW)[0], "PAIR_CANDIDATE")

    def test_documentary_coen_not_instrumental(self):
        row = dict(BASE, source_kind="institutional_document")
        self.assertIn("not_instrumental_original", evaluate(row, RAW)[1])

    def test_no_original_bytes(self):
        self.assertIn("original_bytes_not_verified", evaluate(BASE)[1])

    def test_wrong_hash(self):
        self.assertIn("original_sha256_mismatch", evaluate(BASE, b"other")[1])

    def test_no_utc_timezone(self):
        row = dict(BASE, period_start_utc="2026-11-04T12:00:00")
        self.assertIn("invalid_timestamps", evaluate(row, RAW)[1])

    def test_future_data_leakage(self):
        self.assertIn("future_data_leakage",
            evaluate(BASE, RAW, "2026-11-05T12:30:00Z")[1])

    def test_missing_available_time(self):
        row = dict(BASE, available_at_utc=None)
        self.assertEqual(evaluate(row, RAW)[0], "NO_EVALUABLE")

    def test_missing_datum(self):
        row = dict(BASE, datum=None)
        self.assertIn("datum_unverified", evaluate(row, RAW)[1])

    def test_nan_rejected(self):
        row = dict(BASE, observed_mm=float("nan"))
        self.assertIn("invalid_rainfall", evaluate(row, RAW)[1])
        self.assertIn("invalid_rainfall", evaluate(dict(BASE, observed_mm=True), RAW)[1])

    def test_zero_is_valid(self):
        row = dict(BASE, observed_mm=0)
        self.assertEqual(evaluate(row, RAW)[0], "PAIR_CANDIDATE")
        premature = dict(BASE, available_at_utc="2026-11-05T11:59:59Z")
        self.assertIn("available_before_period_end", evaluate(premature, RAW)[1])
        bad_coord = dict(BASE, latitude=True)
        self.assertIn("invalid_coordinates", evaluate(bad_coord, RAW)[1])


if __name__ == "__main__":
    unittest.main()
