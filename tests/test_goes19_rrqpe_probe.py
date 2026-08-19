from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "probe_goes19_rrqpe", ROOT / "scripts/probe_goes19_rrqpe.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


LISTING = b'''<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Contents>
    <Key>ABI-L2-RRQPEF/2026/231/04/OR_ABI-L2-RRQPEF-M6_G19_s20262310440203_e20262310449512_c20262310449574.nc</Key>
    <LastModified>2026-08-19T04:50:13.000Z</LastModified>
    <Size>1474286</Size>
  </Contents>
</ListBucketResult>'''


class Goes19ProbeTests(unittest.TestCase):
    def test_parses_catalog_and_fractional_goes_time(self):
        rows = MODULE.parse_listing(LISTING)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["size_bytes"], 1474286)
        self.assertEqual(rows[0]["scan_start"], "2026-08-19T04:40:20.300000+00:00")
        self.assertEqual(rows[0]["scan_end"], "2026-08-19T04:49:51.200000+00:00")

    def test_missing_source_is_unknown_and_never_low_risk(self):
        class EmptyResponse:
            status = 200
            headers = {"content-type": "application/xml", "content-length": "0"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/" />'

        probe = MODULE.run(
            datetime(2026, 8, 19, 4, 56, tzinfo=timezone.utc),
            opener=lambda request, timeout: EmptyResponse(),
        )
        self.assertFalse(probe["source_available"])
        self.assertEqual(
            probe["scientific_gate"]["missing_data_interpretation"],
            "UNKNOWN_NOT_ZERO_OR_LOW_RISK",
        )
        self.assertFalse(probe["scientific_gate"]["automatic_event_or_none_classification"])

    def test_archive_cannot_credit_closeout_or_replace_imerg(self):
        probe = MODULE.base_probe(datetime(2026, 8, 19, tzinfo=timezone.utc))
        probe["scientific_gate"]["missing_data_interpretation"] = "UNKNOWN_NOT_ZERO_OR_LOW_RISK"
        archive = MODULE.archive_result(None, probe, datetime(2026, 8, 19, tzinfo=timezone.utc))
        self.assertFalse(archive["counts_toward_v08_closeout"])
        self.assertEqual(archive["integration_mode"], "GOES_TEST_ONLY")
        self.assertFalse(archive["scientific_gate"]["replaces_imerg"])
        self.assertFalse(archive["scientific_gate"]["threshold_promotion_allowed"])
        self.assertFalse(archive["scientific_gate"]["missing_data_is_low_risk"])
        self.assertFalse(archive["retention_decision"]["technical_review_sample_complete"])
        self.assertEqual(archive["summary"]["capture_delay_p90_minutes"], None)

    def test_workflow_keeps_explicit_goes_test_only_guards(self):
        text = (ROOT / ".github/workflows/goes19-rrqpe-probe.yml").read_text(encoding="utf-8")
        self.assertIn("GOES_TEST_ONLY", text)
        self.assertIn("counts_toward_v08_closeout", text)
        self.assertIn("threshold_promotion_allowed", text)
        self.assertIn("git rebase origin/main", text)

    def test_publish_and_live_smoke_require_goes_guardrails(self):
        for workflow_name in ("publish-committed-data.yml", "live-smoke-test.yml"):
            text = (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
            self.assertIn("data/calibration/goes19_rrqpe_probe.json", text)
            self.assertIn("data/calibration/goes19_rrqpe_archive.json", text)
            self.assertIn("GOES_TEST_ONLY", text)
            self.assertIn("counts_toward_v08_closeout", text)
            self.assertIn("replaces_imerg", text)


if __name__ == "__main__":
    unittest.main()
