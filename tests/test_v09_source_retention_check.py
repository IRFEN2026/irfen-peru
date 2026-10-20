"""Source availability / retention check (IMERG Early v07, GOES-19 RRQPEF): offline tests. RESEARCH_ONLY / TEST_ONLY.

A fake opener serves synthetic CMR / S3 / documentation answers and records every URL; nothing touches the network.
"""
import copy
import gzip
import hashlib
import http.server
import importlib.util
import json
import shutil
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("v09_source_retention_check", "scripts/v09_source_retention_check.py")
T = _load("test_v09_capture_ledger_helpers", "tests/test_v09_capture_ledger.py")
UTC = timezone.utc
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
D = [date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13)]
MISSING_SLOT = datetime(2026, 10, 11, 7, 30, tzinfo=UTC)
MISSING_BIN = datetime(2026, 10, 11, 5, 40, tzinfo=UTC)
WORKFLOW = ROOT / ".github/workflows/v09-source-retention-manual.yml"


def umm(versions=("07",)):
    items = [{"meta": {"concept-id": f"C{v}-GES_DISC", "revision-date": "2026-01-01T00:00:00Z"},
              "umm": {"ShortName": "GPM_3IMERGHHE", "Version": v, "EntryTitle": f"IMERG Early V{v}", "CollectionProgress": "ACTIVE",
                      "TemporalExtents": [{"EndsAtPresentFlag": False, "RangeDateTimes": [{"BeginningDateTime": "1998-01-01T00:00:00.000Z"}]}],
                      "DataCenters": [{"ShortName": "GESDISC", "Roles": ["ARCHIVER"]}], "DOI": {"DOI": "10.5067/GPM/IMERG/3B-HH-E/07"},
                      "Abstract": "Early run. Older versions will no longer be available and have been superseded by Version 07."}}
             for v in versions]
    return json.dumps({"hits": len(items), "items": items}).encode()


def prefixes_xml(prefixes):
    cp = "".join(f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in prefixes)
    return (f'<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>noaa-goes19</Name>'
            f"<IsTruncated>false</IsTruncated>{cp}</ListBucketResult>").encode()


DOCS = {
    "https://doi.org/api/handles/10.5067/GPM/IMERG/3B-HH-E/07": b'{"values":[{"data":{"value":"https://cmr.earthdata.nasa.gov/search/concepts/C2723758340-GES_DISC"}}]}',
    "https://registry.opendata.aws/nasa-gpm3imerghhe/": b"<html><body>arn:aws:s3:::gesdisc-cumulus-prod-protected/GPM_L3/GPM_3IMERGHHE.07/</body></html>",
    "https://registry.opendata.aws/noaa-goes/": b"<html><body><p>noaa-goes19</p><p>NOAA Open Data Dissemination (NODD) Program</p></body></html>",
    "https://catalog.data.gov/api/3/action/package_show?id=noaa-goes-r-series-advanced-baseline-imager-abi-level-2-rainfall-rate-quantitative-precipi":
        b'{"result":{"organization":{"title":"National Centers for Environmental Information"},"notes":"see www.class.noaa.gov and noaa-goes19"}}',
}


def handler(overrides=None):
    o = overrides or {}

    def h(url, headers):
        if url in o:
            r = o[url]
            return r(url) if callable(r) else r
        if url in DOCS:
            return T.FakeResponse(DOCS[url], 200, {"Content-Type": "text/html"})
        if "collections.umm_json" in url:
            return T.FakeResponse(umm(), 200, {"CMR-Hits": "1"})
        if "sort_key=start_date&page_size=1" in url and "temporal" not in url:
            return T.FakeResponse(T.cmr_body([datetime(1998, 1, 1, tzinfo=UTC)]), 200, {"CMR-Hits": "400000"})
        if "sort_key=-start_date" in url:
            return T.FakeResponse(T.cmr_body([datetime(2026, 10, 20, 6, 0, tzinfo=UTC)]), 200, {"CMR-Hits": "400000"})
        if "granules.json" in url:
            t = url.split("temporal%5B%5D=")[1].split("&")[0]
            a, b = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in t.split(","))
            n = round((b - a).total_seconds() / 1800)
            if a.date() == MISSING_SLOT.date() and n == 48:
                listed = [a + timedelta(minutes=30 * k) for k in range(48) if a + timedelta(minutes=30 * k) != MISSING_SLOT]
                return T.FakeResponse(T.cmr_body(listed if "page_size=100" in url else listed[:1]), 200, {"CMR-Hits": "47"})
            if a.date() == D[2] and n == 48:
                return T.FakeResponse(T.cmr_body([]), 200, {"CMR-Hits": "0"})
            if a.date() == D[3] and n == 48:
                return HTTPError(url, 500, "x", {}, None)
            return T.FakeResponse(T.cmr_body([a]), 200, {"CMR-Hits": str(n)})
        if "delimiter=/" in url:
            prefix = url.split("prefix=")[1].split("&")[0]
            depth = prefix.count("/")
            if depth == 1:
                return T.FakeResponse(prefixes_xml(["ABI-L2-RRQPEF/2025/", "ABI-L2-RRQPEF/2026/"]), 200)
            if depth == 2:
                doys = [100, 101, 103] if "2025" in prefix else list(range(1, 294))
                return T.FakeResponse(prefixes_xml([f"{prefix}{d:03d}/" for d in doys]), 200)
            return T.FakeResponse(prefixes_xml([f"{prefix}{h:02d}/" for h in (12, 13)]), 200)
        prefix = url.split("prefix=")[1].split("&")[0]
        parts = prefix.rstrip("/").split("/")
        day = datetime.strptime(f"{parts[1]}{parts[2]}", "%Y%j").replace(tzinfo=UTC)
        if len(parts) == 4:  # oldest hour
            h0 = day + timedelta(hours=int(parts[3]))
            return T.FakeResponse(T.s3_body([T.goes_key(h0 + timedelta(minutes=10 * k)) for k in range(6)]), 200)
        bins = [day + timedelta(minutes=10 * k) for k in range(144)]
        if day.date() == D[1]:
            return T.FakeResponse(T.s3_body([T.goes_key(b) for b in bins if b != MISSING_BIN]), 200)
        if day.date() == D[2]:
            return T.FakeResponse(T.s3_body([]), 200)
        if day.date() == D[3]:
            return T.FakeResponse(T.s3_body([T.goes_key(day + timedelta(minutes=15 * k), "M3") for k in range(96)]), 200)
        return T.FakeResponse(T.s3_body([T.goes_key(b) for b in bins]), 200)
    return h


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irfen-retention-test-"))
        self.c = R.load_contract()
        self.c["window_days"] = {"from_utc": "2026-10-10T00:00:00Z", "to_utc": "2026-10-14T00:00:00Z"}
        self.c["imerg"]["years"] = [2025, 2026]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, overrides=None, contract=None):
        c = contract or self.c
        opener = T.FakeOpener(handler(overrides))
        out = self.tmp / f"r{len(list(self.tmp.iterdir()))}"
        m = R.fetch(out, c, opener=opener, sleep=lambda s: None, clock=lambda: NOW)
        return m, R.build(out, c), out, opener


class Evidence(Base):
    def test_imerg_per_day_and_per_year(self):
        _, ev, _, _ = self.run_check()
        st = {r["day"]: r for r in ev["imerg"]["per_day"]}
        self.assertEqual(st["2026-10-10"]["status"], "COMPLETE_AT_SOURCE")
        self.assertEqual(st["2026-10-11"]["status"], "INCOMPLETE_AT_SOURCE")
        self.assertEqual(st["2026-10-11"]["slots_not_listed"], ["2026-10-11T07:30:00Z"])
        self.assertEqual(st["2026-10-12"]["status"], "UNKNOWN_EMPTY", "an empty answer never confirms absence")
        self.assertEqual(st["2026-10-13"]["status"], "UNKNOWN", "HTTP 500 is UNKNOWN")
        years = {y["year"]: y for y in ev["imerg"]["per_year"]}
        self.assertEqual(years[2025]["expected"], 365 * 48)
        self.assertEqual(years[2025]["status"], "COMPLETE")
        self.assertEqual(years[2026]["expected"], (date(2026, 10, 14) - date(2026, 1, 1)).days * 48)
        self.assertEqual(ev["imerg"]["oldest_granule"]["time_start"], "1998-01-01T00:00:00Z")
        col = ev["imerg"]["collection"]["CMR_COLLECTION"]["collections"][0]
        self.assertEqual((col["collection_progress"], col["beginning"], col["archive_centers"]), ("ACTIVE", ["1998-01-01T00:00:00.000Z"], ["GESDISC"]))
        self.assertTrue(any("no longer be available" in s["context"] for s in col["abstract_retention_statements"]))

    def test_goes_per_day_years_and_oldest(self):
        _, ev, _, _ = self.run_check()
        st = {r["day"]: r for r in ev["goes"]["per_day"]}
        self.assertEqual(st["2026-10-10"]["status"], "COMPLETE_AT_SOURCE")
        self.assertEqual(st["2026-10-10"]["objects"], 144)
        self.assertEqual(st["2026-10-11"]["status"], "INCOMPLETE_AT_SOURCE")
        self.assertEqual(st["2026-10-11"]["bins_not_listed"], ["2026-10-11T05:40:00Z"])
        self.assertEqual(st["2026-10-12"]["status"], "UNKNOWN_EMPTY")
        self.assertEqual(st["2026-10-13"]["status"], "UNKNOWN_MODE", "a mode change makes the 10-min grid inapplicable")
        y = {r["prefix"]: r for r in ev["goes"]["per_year"]}
        self.assertEqual(y["ABI-L2-RRQPEF/2025/"]["doys_missing_between_first_and_last"], [102])
        self.assertEqual(ev["goes"]["oldest_object"]["oldest_scan_start"], "2025-04-10T12:00:20Z")

    def test_documents_quotes_and_retention_snippets_need_human_review(self):
        url = "https://registry.opendata.aws/noaa-goes/"
        doc = b"<html><p>noaa-goes19</p><p>NOAA Open Data Dissemination</p><p>Objects are deleted after 90 days.</p></html>"
        _, ev, _, _ = self.run_check({url: T.FakeResponse(doc, 200)})
        d = {x["id"]: x for x in ev["documents"]}["AWS_REGISTRY_NOAA_GOES"]
        self.assertEqual(d["expected_quotes"], {"noaa-goes19": True, "NOAA Open Data Dissemination": True})
        self.assertTrue(any("deleted after 90 days" in s["context"] for s in d["retention_statements"]))
        # A statement found mechanically never enables UNRECOVERABLE by itself: it requires human review and a contract PR.
        self.assertIs(ev["assessment"]["unrecoverable_assignable"], False)

    def test_document_errors_and_redirects_are_unknown(self):
        url = "https://registry.opendata.aws/noaa-goes/"
        _, ev, _, _ = self.run_check({url: lambda u: HTTPError(u, 302, "Found", {"Location": "https://example.com/"}, None)})
        d = {x["id"]: x for x in ev["documents"]}["AWS_REGISTRY_NOAA_GOES"]
        self.assertEqual((d["status"], d["error"]), ("UNKNOWN", "HTTP_302"))

    def test_collection_versions_are_listed(self):
        url = "https://cmr.earthdata.nasa.gov/search/collections.umm_json?short_name=GPM_3IMERGHHE"
        _, ev, _, _ = self.run_check({url: T.FakeResponse(umm(("06", "07")), 200, {"CMR-Hits": "2"})})
        cols = ev["imerg"]["collection"]["CMR_COLLECTION_ALL_VERSIONS"]["collections"]
        self.assertEqual([c["version"] for c in cols], ["06", "07"])


class Safety(Base):
    def test_only_allowed_catalog_and_document_urls(self):
        m, ev, _, opener = self.run_check()
        hc = {"allowed_url_patterns": self.c["allowed_url_patterns"], "limits": self.c["limits"]}
        for u in opener.urls:
            R.LEDGER.check_url(u, hc)
        self.assertFalse([u for u in opener.urls if u.endswith((".nc", ".HDF5", ".h5"))])
        self.assertEqual((m["downloads_of_granules_or_scans"], ev["downloads_of_granules_or_scans"]), (0, 0))
        for bad in ["https://noaa-goes19.s3.amazonaws.com/" + T.goes_key(NOW),
                    "https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGHHE.07/2026/283/" + T.imerg_title(NOW),
                    "https://registry.opendata.aws/anything-else/"]:
            with self.assertRaises(ValueError):
                R.LEDGER.check_url(bad, hc)

    def test_redirects_are_not_followed(self):
        hits = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(HTTPError) as ctx:
                R.NO_REDIRECT_OPEN(f"http://127.0.0.1:{srv.server_address[1]}/start", timeout=5)
            self.assertEqual(ctx.exception.code, 302)
            self.assertEqual(hits, ["/start"], "the redirect target must never be requested")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_idempotent_immutable_and_guarded(self):
        _, ev, out, _ = self.run_check()
        a, b = self.tmp / "e1.json", self.tmp / "e2.json"
        R.write(ev, a)
        R.write(R.build(out, self.c), b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        changed = copy.deepcopy(ev)
        changed["imerg"]["per_day"][0]["status"] = "UNKNOWN"
        with self.assertRaises(FileExistsError):
            R.write(changed, a)
        with self.assertRaises(FileExistsError):
            R.fetch(out, self.c, opener=T.FakeOpener(handler()), sleep=lambda s: None, clock=lambda: NOW)
        for p in ("data/v09/rain/x.json", "config/x.json", "data/v09/capture_ledger/x.json"):
            with self.assertRaises(ValueError):
                R.guarded_output(ROOT / p)
        R.guarded_output(ROOT / "data/v09/source_retention/snapshots/x/evidence_v0_1.json")

    def test_tampered_response_is_unknown_and_reported(self):
        m, _, out, _ = self.run_check()
        rec = next(r for r in m["requests"] if r["kind"] == "CMR_DAY_COUNT" and r["day"] == "2026-10-10")
        path = out / "raw" / f"{rec['sha256']}.bin.gz"
        path.write_bytes(gzip.compress(b'{"feed":{"entry":[]}}', mtime=0))
        ev = R.build(out, self.c)
        self.assertEqual({r["day"]: r["status"] for r in ev["imerg"]["per_day"]}["2026-10-10"], "UNKNOWN")
        self.assertTrue(any(rec["request_id"] in p for p in ev["integrity_problems"]))

    def test_future_window_refused_without_requests(self):
        c = copy.deepcopy(self.c)
        c["window_days"]["to_utc"] = "2026-10-21T00:00:00Z"
        opener = T.FakeOpener(handler())
        with self.assertRaises(ValueError):
            R.fetch(self.tmp / "f", c, opener=opener, sleep=lambda s: None, clock=lambda: NOW)
        self.assertEqual(opener.urls, [])

    def test_repository_files_untouched(self):
        watched = [p for d in ("data", "site/data", "config") for p in (ROOT / d).rglob("*") if p.is_file()]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
        _, ev, _, _ = self.run_check()
        R.write(ev, self.tmp / "evidence.json")
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched})

    def test_guards_and_no_precipitation(self):
        _, ev, _, _ = self.run_check()
        for k, v in R.GUARDS.items():
            self.assertEqual(ev[k], v)
        text = json.dumps(ev)
        for token in ("rate_mm", "precipitation\":", "accum_mm"):
            self.assertNotIn(token, text)
        self.assertIs(ev["contains_precipitation_values"], False)


class ManualWorkflowContract(unittest.TestCase):
    def test_manual_read_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        on = text[text.index("\non:"):text.index("\npermissions:")]
        self.assertIn("workflow_dispatch:", on)
        for trigger in ("schedule", "push", "pull_request", "workflow_run", "repository_dispatch", "cron"):
            self.assertNotIn(trigger, on)
        self.assertRegex(text, r"\npermissions:\n  contents: read\n")
        for forbidden in ("contents: write", "git push", "git commit", "earthaccess", "curl ", "wget ", "secrets."):
            self.assertNotIn(forbidden, text)
        self.assertIn("runs-on: ubuntu-24.04", text)

    def test_capture_ledger_contract_keeps_unrecoverable_disabled(self):
        c = json.loads((ROOT / "config/v09_capture_ledger_contract_v0_1.json").read_text(encoding="utf-8"))
        for p in c["products"].values():
            self.assertEqual(p["retention"]["status"], "NOT_VERIFIED")
            self.assertIsNone(p["retention"]["hours"])


if __name__ == "__main__":
    unittest.main()
