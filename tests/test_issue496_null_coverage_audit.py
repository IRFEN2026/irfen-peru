import unittest
from scripts.issue496_null_coverage_audit import audit, classify

def row(**overrides):
    record = dict(department="Tumbes", area_id="TUM-01",
                  period_start_utc="2026-11-04T12:00:00Z",
                  period_end_utc="2026-11-05T12:00:00Z",
                  expected_intervals=48, valid_intervals=48,
                  coverage_fraction=1.0, rain_mm=0.0, null_reason=None)
    record.update(overrides)
    return record

class NullCoverageAuditTests(unittest.TestCase):
    def test_zero_is_observation(self):
        self.assertEqual(classify(row()), "VALID_ZERO")
    def test_positive_rain(self):
        self.assertEqual(classify(row(rain_mm=5.5)), "VALID_RAIN")
    def test_coverage_null_not_zero(self):
        self.assertEqual(classify(row(rain_mm=None, null_reason="insufficient_spatial_coverage",
                                      coverage_fraction=0.2)), "NULL_COVERAGE")
    def test_other_null(self):
        self.assertEqual(classify(row(rain_mm=None, null_reason="missing_granule",
                                      valid_intervals=47)), "NULL_OTHER")
    def test_null_requires_reason(self):
        with self.assertRaises(ValueError):
            classify(row(rain_mm=None))
    def test_reject_incomplete_positive(self):
        with self.assertRaises(ValueError):
            classify(row(rain_mm=1.0, coverage_fraction=0.5))
    def test_reject_bool(self):
        with self.assertRaises(ValueError):
            classify(row(rain_mm=True))
    def test_reject_inconsistent_time(self):
        with self.assertRaises(ValueError):
            classify(row(expected_intervals=47))
    def test_reject_noncoastal(self):
        with self.assertRaises(ValueError):
            classify(row(department="Loreto"))
    def test_reject_duplicate(self):
        with self.assertRaises(ValueError):
            audit([row(), row()])
    def test_missing_departments_reported(self):
        result = audit([row()])
        self.assertEqual(result["null_coverage"], 0)
        self.assertEqual(len(result["departments_missing"]), 10)
        self.assertEqual(result["scientific_skill"], "NO_EVALUABLE")

if __name__ == "__main__":
    unittest.main()
