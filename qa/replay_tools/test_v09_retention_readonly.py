"""Offline contract tests, not part of the scientific pytest manifest."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE = Path(__file__).with_name("v09_source_retention_readonly.py")
spec = importlib.util.spec_from_file_location("v09_retention_probe", MODULE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class RetentionContractTest(unittest.TestCase):
    def test_catalog_host_allowlist_rejects_other_hosts_without_network(self):
        with self.assertRaisesRegex(ValueError, "URL_DENIED"):
            probe.fetch_catalog("https://example.com/search/granules.json")

    def test_catalog_disallows_http_and_userinfo(self):
        for url in ("http://cmr.earthdata.nasa.gov/search/granules.json",
                    "https://attacker@cmr.earthdata.nasa.gov/search/granules.json"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                probe.fetch_catalog(url)

    def test_goes_earliest_metadata_only(self):
        xml = b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>false</IsTruncated><Contents><Key>ABI-L2-RRQPEF/2025/001/00/OR_ABI-L2-RRQPEF-M6_G19_s20250010000000_e20250010010000_c20250010012000.nc</Key></Contents></ListBucketResult>'
        with mock.patch.object(probe, "fetch_catalog", return_value=({"url": probe.NOAA, "sha256": "abc"}, xml)) as fetch:
            result = probe.goes_probe([2025])
        self.assertEqual(result["retention_status"], "NOT_VERIFIED")
        self.assertEqual(len(result["queries"]), 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn("max-keys=1", fetch.call_args.args[0])

    def test_nasa_one_metadata_collection_and_granule(self):
        vals = [
            ({"url":"metadata","sha256":"1"}, json.dumps({"feed":{"entry":[{"id":probe.COLLECTION, "time_start":"2000-01-01T00:00:00Z"}]}}).encode()),
            ({"url":"granules","sha256":"2"}, json.dumps({"feed":{"entry":[{"id":"g1","time_start":"2025-01-01T00:00:00Z"}]}}).encode())
        ]
        with mock.patch.object(probe, "fetch_catalog", side_effect=vals) as fetch:
            result = probe.nasa_probe()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result["retention_status"], "NOT_VERIFIED")

    def test_errors_never_claim_verified(self):
        with mock.patch.object(probe,"nasa_probe",side_effect=RuntimeError("timeout")), mock.patch.object(probe,"goes_probe",side_effect=ValueError("invalid")):
            result = probe.build([2025])
        self.assertEqual(result["retention_status"], "NOT_VERIFIED")
        self.assertEqual([x["status"] for x in result["results"]], ["UNKNOWN","UNKNOWN"])
        self.assertFalse(result["download_enabled"])

    def test_empty_s3_cannot_be_verified(self):
        xml = b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>false</IsTruncated></ListBucketResult>'
        with mock.patch.object(probe,"fetch_catalog",return_value=({"url":"catalog"}, xml)):
            out=probe.goes_probe([2025])
        self.assertIsNone(out["queries"][0]["observed"]["first_lexicographic_key"])
        self.assertEqual(out["retention_status"],"NOT_VERIFIED")

if __name__ == "__main__":
    unittest.main()
