"""Santa 2011: SHA-256 de bytes verificados y congelador fail-closed (stdlib, offline)."""
import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "site/data/phase2/source_assessments/santa_2011_alicia_bitstream_audit_v0_1.json"
FREEZER = ROOT / "scripts/freeze_phase2_santa_2011_alicia_bitstreams.py"


def load_freezer():
    spec = importlib.util.spec_from_file_location("santa_freezer", FREEZER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Santa2011PdfIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads(AUDIT.read_text(encoding="utf-8"))

    def test_repository_digest_is_md5_not_relabelled_as_sha256(self):
        src = self.d["source"]
        self.assertEqual(src["primary_pdf_repository_digest"], "b920108b7054aa77f164b979ea618ec0MD51")
        parsed = src["primary_pdf_repository_checksum_parsed"]
        self.assertEqual(parsed["algorithm"], "MD5")
        self.assertTrue(src["primary_pdf_repository_digest"].startswith(parsed["value"]))
        self.assertNotEqual(parsed["value"], self.d["pdf_binary_integrity"]["sha256"])

    def test_sha256_is_pinned_only_with_size_and_md5_match(self):
        pin = self.d["pdf_binary_integrity"]
        self.assertRegex(pin["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(pin["size_matches_ana_repository_original"])
        self.assertTrue(pin["md5_matches_ana_repository_original"])
        self.assertEqual(pin["received_md5"], self.d["source"]["primary_pdf_repository_checksum_parsed"]["value"])
        self.assertEqual(pin["received_size_bytes"], 5981714)
        self.assertIn("MIRROR", pin["sha256_status"])
        self.assertFalse(pin["raw_bytes_committed"])
        self.assertTrue(pin["ana_repository_direct_download"].startswith("SOURCE_ACCESS_UNAVAILABLE"))

    def test_text_probe_does_not_resolve_datum_or_authorize_geometry(self):
        tp = self.d["pdf_text_probe"]
        self.assertFalse(tp["findings"]["explicit_datum_statement_found_in_extracted_text"])
        self.assertIn("not proof", tp["inference_limit"])
        use = self.d["scientific_use"]
        self.assertFalse(use["native_hydraulic_geometry_recovered"])
        self.assertFalse(use["map_publication_authorized"])
        g = self.d["guards"]
        self.assertEqual((g["deployment_status"], g["test_mode"], g["activation_gate"]), ("RESEARCH_ONLY", "TEST_ONLY", "BLOCKED"))
        self.assertIsNone(g["decision_thresholds"])
        self.assertIsNone(g["hydraulic_factors"])

    def test_no_geometry_capacity_or_threshold_fields_introduced(self):
        text = AUDIT.read_text(encoding="utf-8")
        for forbidden in ('"geometry":', '"coordinates":', '"capacity_m3s"', '"discharge_m3s"', '"threshold_mm"'):
            self.assertNotIn(forbidden, text)


class Santa2011FreezerFailClosedTests(unittest.TestCase):
    def run_freezer(self, responses):
        mod = load_freezer()

        def fake_fetch(url, timeout, attempts=3):
            data = responses.get(url)
            if data is None:
                return None, {"url": url, "access_status": "SOURCE_ACCESS_UNAVAILABLE", "error": "offline"}
            return data, {"url": url, "http_status": 200}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(mod, "fetch", fake_fetch), \
                mock.patch("sys.stdout"):
            out = Path(tmp) / "r.json"
            with mock.patch("sys.argv", ["x", "--out", str(out)]):
                rc = mod.main()
            return rc, json.loads(out.read_text(encoding="utf-8")), mod

    def test_unavailable_sources_produce_no_hash_and_no_failure(self):
        rc, r, _ = self.run_freezer({})
        self.assertEqual(rc, 0)
        for entry in r["bitstreams"].values():
            self.assertEqual(entry["freeze_status"], "SOURCE_ACCESS_UNAVAILABLE")
            self.assertIsNone(entry["sha256"])

    def test_mirror_with_wrong_md5_is_not_pinnable(self):
        mod = load_freezer()
        url = mod.MIRRORS["SIGRID_14534_PDF"]
        rc, r, _ = self.run_freezer({url: b"x" * 5981714})
        m = r["mirrors"]["SIGRID_14534_PDF"]
        self.assertFalse(m["md5_matches_ana_repository_original"])
        self.assertEqual(m["freeze_status"], "MIRROR_BYTES_DIFFER_FROM_ANA_REPOSITORY_ORIGINAL_NOT_PINNABLE")
        self.assertEqual(r["text_probe"]["probe_status"], "NOT_RUN_NO_VERIFIED_TEXT_OR_PDF_BYTES")

    def test_ana_bytes_with_wrong_md5_fail_closed(self):
        mod = load_freezer()
        rc, r, _ = self.run_freezer({mod.TARGETS["ORIGINAL_PDF"]["url"]: b"tampered"})
        self.assertEqual(rc, 1)
        pdf = r["bitstreams"]["ORIGINAL_PDF"]
        self.assertEqual(pdf["freeze_status"], "INTEGRITY_MISMATCH_NOT_PINNABLE")
        self.assertIsNone(pdf["sha256"])

    def test_text_probe_counts_absence_without_claiming_negative(self):
        mod = load_freezer()
        probe = mod.text_probe("Eje 0+000 758 969 9 007 565 UTM HEC-RAS".encode())
        self.assertEqual(probe["term_counts"]["DATUM"], 0)
        self.assertTrue(probe["axis_endpoint_digits_present"]["758969"])
        self.assertIn("not proof", probe["inference_limit"])


if __name__ == "__main__":
    unittest.main()
