"""Capture ledger v0.1 (IMERG Early / GOES-19): states, evidence, negatives, idempotence and safety. RESEARCH_ONLY / TEST_ONLY.

All network traffic here is simulated: the fake opener serves synthetic CMR / S3 catalog answers and records every URL,
so the tests are reproducible offline and also prove that nothing but catalog URLs is ever requested.
"""
import copy
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v09_capture_ledger.py"
SPEC = importlib.util.spec_from_file_location("v09_capture_ledger", SCRIPT)
L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(L)
WORKFLOW = ROOT / ".github/workflows/v09-capture-ledger-manual.yml"
UTC = timezone.utc
T0 = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)
NO_SLEEP = lambda s: None  # noqa: E731


# ------------------------------------------------------------------------------------------------ synthetic catalogs
def imerg_title(start, version="V07C"):
    end = start + timedelta(minutes=29, seconds=59)
    minutes = start.hour * 60 + start.minute
    return f"3B-HHR-E.MS.MRG.3IMERG.{start:%Y%m%d}-S{start:%H%M%S}-E{end:%H%M%S}.{minutes:04d}.{version}.HDF5"


def cmr_body(starts, drop_field=None):
    entries = []
    for s in starts:
        e = dict(id=f"G{int(s.timestamp())}-GES_DISC", title=f"GPM_3IMERGHHE.07:{imerg_title(s)}",
                 time_start=s.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                 time_end=(s + timedelta(minutes=30) - timedelta(milliseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.999Z"),
                 updated="2026-10-10T12:00:00.000Z", collection_concept_id="C0000000000-GES_DISC",
                 links=[{"href": "https://data.gesdisc.earthdata.nasa.gov/data/should-never-be-followed.HDF5"}])
        if drop_field:
            e.pop(drop_field)
        entries.append(e)
    return json.dumps({"feed": {"id": "x", "title": "ECHO granule metadata", "entry": entries}}).encode()


def goes_key(scan_start, mode="M6"):
    j = lambda t: f"{t:%Y%j%H%M%S}{t.microsecond // 100000}"  # noqa: E731
    s = scan_start + timedelta(seconds=20)
    e = s + timedelta(minutes=9, seconds=30)
    return f"ABI-L2-RRQPEF/{s:%Y/%j/%H}/OR_ABI-L2-RRQPEF-{mode}_G19_s{j(s)}_e{j(e)}_c{j(e + timedelta(seconds=6))}.nc"


def s3_body(keys, truncated=False, token=None, key_count=None):
    contents = "".join(f"<Contents><Key>{k}</Key><LastModified>2026-10-10T00:20:00.000Z</LastModified>"
                       f"<ETag>&quot;{hashlib.md5(k.encode()).hexdigest()}&quot;</ETag><Size>3000000</Size></Contents>" for k in keys)
    kc = len(keys) if key_count is None else key_count
    nxt = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<Name>noaa-goes19</Name><KeyCount>{kc}</KeyCount><MaxKeys>1000</MaxKeys><IsTruncated>{'true' if truncated else 'false'}</IsTruncated>"
            f"{nxt}{contents}</ListBucketResult>").encode()


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = {k: v for k, v in (headers or {}).items()}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Serves CMR / S3 answers from a function of (url, request headers); records every requested URL."""

    def __init__(self, handler):
        self.handler, self.urls = handler, []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        result = self.handler(url, dict(request.header_items()))
        if isinstance(result, Exception):
            raise result
        return result


def scenario(cmr=None, s3=None):
    """Default handler: every IMERG slot and GOES bin listed; override per call."""
    def handler(url, headers):
        if url.startswith("https://cmr."):
            return cmr(url, headers) if cmr else None
        return s3(url, headers) if s3 else None
    return handler


def clock_at(t):
    return lambda: t


def all_slots(start, end, minutes):
    out, s = [], start
    while s < end:
        out.append(s)
        s += timedelta(minutes=minutes)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.contract = L.load_contract()
        self.tmp = Path(tempfile.mkdtemp(prefix="irfen-ledger-test-"))
        self.root = self.tmp / "repo"
        for arch in [a for p in self.contract["products"].values() for a in p["local_archives"]]:
            path = self.root / arch["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({arch["list"]: []}), encoding="utf-8")
        (self.root / "config").mkdir(exist_ok=True)
        shutil.copy(L.CONTRACT_PATH, self.root / "config/v09_capture_ledger_contract_v0_1.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def capture(self, imerg=(), goes=()):
        p = self.contract["products"]
        a = p["IMERG_EARLY_HH"]["local_archives"][0]
        (self.root / a["path"]).write_text(json.dumps({"granules": [
            {"time_utc": t.isoformat(), "granule": imerg_title(t), "retrieved_at_utc": (t + timedelta(hours=6)).isoformat(),
             "targets": {"x": {"rate_mm_h": 1.2}}} for t in imerg]}), encoding="utf-8")
        g = p["GOES19_RRQPEF"]["local_archives"][0]
        (self.root / g["path"]).write_text(json.dumps({"scans": [
            {"key": goes_key(t), "sampled_at_utc": (t + timedelta(minutes=12)).isoformat(),
             "targets": {"x": {"rate_mean_mm_h": 0.4}}} for t in goes]}), encoding="utf-8")

    def run_ledger(self, opener, start, end, now, contract=None):
        contract = contract or self.contract
        out = self.tmp / f"resp-{len(list(self.tmp.iterdir()))}"
        manifest = L.fetch(start, end, out, contract, opener=opener, sleep=NO_SLEEP, clock=clock_at(now))
        return manifest, L.build(out, contract, root=self.root, history=False), out

    @staticmethod
    def states(ledger, product):
        return {r["interval_start_utc"]: r["state"] for r in ledger["intervals"] if r["product"] == product}


def imerg_handler(listed, hits=None, status=200, extra_headers=None, body=None):
    def cmr(url, headers):
        b = body if body is not None else cmr_body(listed)
        h = {"CMR-Hits": str(len(listed) if hits is None else hits), "Content-Type": "application/json"}
        h.update(extra_headers or {})
        if status != 200:
            return HTTPError(url, status, "err", {}, None)
        return FakeResponse(b, 200, h)
    return cmr


def goes_handler(listed_bins, mode="M6", per_hour=None):
    def s3(url, headers):
        prefix = re.search(r"prefix=([^&]+)", url).group(1)
        hour = datetime.strptime(prefix.split("/", 1)[1].rstrip("/"), "%Y/%j/%H").replace(tzinfo=UTC)
        if per_hour and hour in per_hour:
            r = per_hour[hour]
            return r(url) if callable(r) else r
        keys = [goes_key(b, mode) for b in listed_bins if hour <= b < hour + timedelta(hours=1)]
        return FakeResponse(s3_body(keys), 200, {"Content-Type": "application/xml"})
    return s3


# ---------------------------------------------------------------------------------------------------------- positives
class States(Base):
    def test_every_state_from_its_evidence(self):
        start, end = T0, T0 + timedelta(hours=6)
        slots = all_slots(start, end, 30)
        listed = [s for s in slots if s not in (T0 + timedelta(hours=2), T0 + timedelta(hours=5, minutes=30))]
        bins = all_slots(T0, T0 + timedelta(hours=2), 10)
        g_listed = [b for b in bins if b != T0 + timedelta(minutes=40)]
        self.capture(imerg=[T0, T0 + timedelta(minutes=30)], goes=[T0 + timedelta(minutes=10)])
        opener = FakeOpener(scenario(imerg_handler(listed), goes_handler(g_listed)))
        now = T0 + timedelta(days=2)
        _, ledger, _ = self.run_ledger(opener, start, end, now)
        st = self.states(ledger, "IMERG_EARLY_HH")
        self.assertEqual(st["2026-10-10T00:00:00Z"], "CAPTURED")
        self.assertEqual(st["2026-10-10T00:30:00Z"], "CAPTURED")
        self.assertEqual(st["2026-10-10T01:00:00Z"], "MISSING_RETRYING")
        self.assertEqual(st["2026-10-10T02:00:00Z"], "ABSENT_AT_SOURCE")
        self.assertEqual(st["2026-10-10T05:30:00Z"], "UNKNOWN", "last slot is not bracketed: absence not corroborated")
        gs = self.states(ledger, "GOES19_RRQPEF")
        self.assertEqual(gs["2026-10-10T00:10:00Z"], "CAPTURED")
        self.assertEqual(gs["2026-10-10T00:40:00Z"], "ABSENT_AT_SOURCE")
        self.assertEqual(gs["2026-10-10T00:50:00Z"], "MISSING_RETRYING")
        self.assertEqual(len([s for s in gs if s < "2026-10-10T06"]), 36)  # GOES grid covers the whole window (6 h x 6)
        # Every non-catalog URL was refused before reaching the opener; only catalog URLs were requested.
        self.assertTrue(all(u.startswith(("https://cmr.earthdata.nasa.gov/search/granules.json?",
                                          "https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-RRQPEF/")) for u in opener.urls))
        self.assertEqual(ledger["downloads_of_granules_or_scans"], 0)

    def test_pending_source_latency_inside_the_horizon(self):
        start, end = T0, T0 + timedelta(hours=3)
        slots = all_slots(start, end, 30)
        listed = [s for s in slots if s != T0 + timedelta(hours=1)]
        opener = FakeOpener(scenario(imerg_handler(listed), goes_handler([])))
        now = T0 + timedelta(hours=1, minutes=30) + timedelta(hours=23)  # slot 01:00 ends 01:30; 24 h horizon not reached
        _, ledger, _ = self.run_ledger(opener, start, end, now)
        self.assertEqual(self.states(ledger, "IMERG_EARLY_HH")["2026-10-10T01:00:00Z"], "PENDING_SOURCE_LATENCY")

    def test_row_fields_and_provenance(self):
        start, end = T0, T0 + timedelta(hours=1)
        self.capture(imerg=[T0])
        opener = FakeOpener(scenario(imerg_handler(all_slots(start, end, 30)), goes_handler(all_slots(start, end, 10))))
        manifest, ledger, out = self.run_ledger(opener, start, end, T0 + timedelta(days=2))
        row = next(r for r in ledger["intervals"] if r["interval_start_utc"] == "2026-10-10T00:30:00Z" and r["product"] == "IMERG_EARLY_HH")
        for k in ("product", "product_name", "product_version", "interval_start_utc", "interval_end_utc", "state", "reason",
                  "captured", "catalog", "retry_active"):
            self.assertIn(k, row)
        self.assertEqual(row["product_version"], ["V07C"])
        self.assertEqual(row["catalog"]["queried_at_utc"], "2026-10-12T00:00:00Z")
        req = {r["request_id"]: r for r in ledger["requests"]}[row["catalog"]["request_ids"][0]]
        raw = (out / "raw" / f"{req['sha256']}.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), req["sha256"], "provenance: stored bytes match the recorded SHA-256")
        cap = next(r for r in ledger["intervals"] if r["state"] == "CAPTURED")["captured"][0]
        self.assertEqual(cap["archive"], "data/v09/rain/imerg_early_north_v0_1.json")
        self.assertEqual(cap["item"], imerg_title(T0))
        self.assertEqual(manifest["downloads_of_granules_or_scans"], 0)

    def test_cmr_paging_with_search_after_is_complete(self):
        start, end = T0, T0 + timedelta(hours=2)
        slots = all_slots(start, end, 30)
        def cmr(url, headers):
            if headers.get("Cmr-search-after"):
                return FakeResponse(cmr_body(slots[2:]), 200, {"CMR-Hits": "4"})
            return FakeResponse(cmr_body(slots[:2]), 200, {"CMR-Hits": "4", "CMR-Search-After": '["a",1]'})
        opener = FakeOpener(scenario(cmr, goes_handler([])))
        manifest, ledger, _ = self.run_ledger(opener, start, end, T0 + timedelta(days=2))
        self.assertEqual(len([r for r in manifest["requests"] if r["product"] == "IMERG_EARLY_HH"]), 2)
        self.assertEqual(set(self.states(ledger, "IMERG_EARLY_HH").values()), {"MISSING_RETRYING"})


# ---------------------------------------------------------------------------------------------------------- negatives
class EmptyOrFailedNeverMeansAbsent(Base):
    W = (T0, T0 + timedelta(hours=3))
    NOW = T0 + timedelta(days=3)

    def imerg_states(self, cmr, contract=None):
        opener = FakeOpener(scenario(cmr, goes_handler(all_slots(*self.W, 10))))
        manifest, ledger, _ = self.run_ledger(opener, *self.W, self.NOW, contract)
        return manifest, ledger, set(self.states(ledger, "IMERG_EARLY_HH").values())

    def test_http_500_is_retried_then_unknown(self):
        manifest, ledger, states = self.imerg_states(imerg_handler([], status=500))
        self.assertEqual(states, {"UNKNOWN"})
        req = [r for r in manifest["requests"] if r["product"] == "IMERG_EARLY_HH"][0]
        self.assertEqual(len(req["attempts"]), 2)
        self.assertEqual(req["error"], "HTTP_500")

    def test_http_403_is_not_retried_and_unknown(self):
        manifest, _, states = self.imerg_states(imerg_handler([], status=403))
        self.assertEqual(states, {"UNKNOWN"})
        self.assertEqual(len([r for r in manifest["requests"] if r["product"] == "IMERG_EARLY_HH"][0]["attempts"]), 1)

    def test_timeout_is_unknown(self):
        manifest, _, states = self.imerg_states(lambda u, h: URLError(TimeoutError("timed out")))
        self.assertEqual(states, {"UNKNOWN"})
        self.assertIn("URLError", [r for r in manifest["requests"] if r["product"] == "IMERG_EARLY_HH"][0]["error"])

    def test_empty_answer_is_unknown(self):
        _, ledger, states = self.imerg_states(imerg_handler([], hits=0))
        self.assertEqual(states, {"UNKNOWN"})
        self.assertIn("EMPTY_RESPONSE", ledger["intervals"][0]["reason"])

    def test_malformed_json_is_unknown(self):
        self.assertEqual(self.imerg_states(imerg_handler([T0], body=b"<html>maintenance</html>"))[2], {"UNKNOWN"})

    def test_entry_without_time_is_unknown(self):
        self.assertEqual(self.imerg_states(lambda u, h: FakeResponse(cmr_body(all_slots(*self.W, 30), drop_field="time_start"),
                                                                     200, {"CMR-Hits": "6"}))[2], {"UNKNOWN"})

    def assert_listed_exist_but_gap_unknown(self, ledger, gap):
        # A validly parsed listing proves existence (MISSING_RETRYING); an incomplete answer can never prove absence.
        st = self.states(ledger, "IMERG_EARLY_HH")
        self.assertEqual(st.pop(gap), "UNKNOWN")
        self.assertEqual(set(st.values()), {"MISSING_RETRYING"})

    def test_incomplete_paging_is_unknown(self):
        gap = T0 + timedelta(hours=1, minutes=30)
        listed = [s for s in all_slots(*self.W, 30) if s != gap]
        self.assert_listed_exist_but_gap_unknown(self.imerg_states(imerg_handler(listed, hits=9))[1], L.iso(gap))

    def test_missing_hits_header_is_unknown(self):
        gap = T0 + timedelta(hours=1, minutes=30)
        listed = [s for s in all_slots(*self.W, 30) if s != gap]
        _, ledger, _ = self.imerg_states(lambda u, h: FakeResponse(cmr_body(listed), 200, {}))
        self.assert_listed_exist_but_gap_unknown(ledger, L.iso(gap))

    def test_tampered_stored_response_is_unknown(self):
        opener = FakeOpener(scenario(imerg_handler([s for s in all_slots(*self.W, 30) if s != T0 + timedelta(hours=1)]),
                                     goes_handler(all_slots(*self.W, 10))))
        manifest, _, out = self.run_ledger(opener, *self.W, self.NOW)
        req = [r for r in manifest["requests"] if r["product"] == "IMERG_EARLY_HH"][0]
        path = out / "raw" / f"{req['sha256']}.bin"
        path.write_bytes(path.read_bytes().replace(b"V07C", b"V07X"))
        ledger = L.build(out, self.contract, root=self.root, history=False)
        self.assertEqual(set(self.states(ledger, "IMERG_EARLY_HH").values()), {"UNKNOWN"})

    def test_unrecoverable_only_with_verified_retention(self):
        listed = [s for s in all_slots(*self.W, 30) if s != T0 + timedelta(hours=1)]
        _, ledger, _ = self.imerg_states(imerg_handler(listed))
        self.assertNotIn("UNRECOVERABLE", {r["state"] for r in ledger["intervals"]})
        self.assertEqual(self.states(ledger, "IMERG_EARLY_HH")["2026-10-10T01:00:00Z"], "ABSENT_AT_SOURCE")
        c = copy.deepcopy(self.contract)
        c["products"]["IMERG_EARLY_HH"]["retention"] = {"status": "VERIFIED", "hours": 24}
        _, ledger, _ = self.imerg_states(imerg_handler(listed), contract=c)
        self.assertEqual(self.states(ledger, "IMERG_EARLY_HH")["2026-10-10T01:00:00Z"], "UNRECOVERABLE")

    def goes_states(self, per_hour, listed=None):
        listed = all_slots(*self.W, 10) if listed is None else listed
        opener = FakeOpener(scenario(imerg_handler(all_slots(*self.W, 30)), goes_handler(listed, per_hour=per_hour)))
        _, ledger, _ = self.run_ledger(opener, *self.W, self.NOW)
        return self.states(ledger, "GOES19_RRQPEF")

    def test_goes_empty_hour_is_unknown_even_when_bracketed(self):
        h1 = T0 + timedelta(hours=1)
        st = self.goes_states({h1: FakeResponse(s3_body([]), 200)})
        self.assertEqual({v for k, v in st.items() if k.startswith("2026-10-10T01")}, {"UNKNOWN"})
        self.assertEqual({v for k, v in st.items() if k.startswith("2026-10-10T00")}, {"MISSING_RETRYING"})

    def test_goes_truncated_without_token_is_unknown(self):
        h1 = T0 + timedelta(hours=1)
        keys = [goes_key(b) for b in all_slots(h1, h1 + timedelta(hours=1), 10)][:3]
        st = self.goes_states({h1: FakeResponse(s3_body(keys, truncated=True), 200)})
        self.assertEqual({v for k, v in st.items() if k.startswith("2026-10-10T01")}, {"UNKNOWN"})

    def test_goes_scan_mode_change_is_unknown(self):
        h1 = T0 + timedelta(hours=1)
        keys = [goes_key(h1, "M3"), goes_key(h1 + timedelta(minutes=15), "M3")]
        st = self.goes_states({h1: FakeResponse(s3_body(keys), 200)})
        self.assertEqual({v for k, v in st.items() if k.startswith("2026-10-10T01")}, {"UNKNOWN"})

    def test_goes_http_error_and_malformed_xml_are_unknown(self):
        h1, h2 = T0 + timedelta(hours=1), T0 + timedelta(hours=2)
        st = self.goes_states({h1: lambda u: HTTPError(u, 503, "x", {}, None), h2: FakeResponse(b"<Error>SlowDown</Error>", 200)})
        self.assertEqual({v for k, v in st.items() if k >= "2026-10-10T01"}, {"UNKNOWN"})

    def test_goes_keycount_mismatch_is_unknown(self):
        h1 = T0 + timedelta(hours=1)
        keys = [goes_key(b) for b in all_slots(h1, h1 + timedelta(hours=1), 10)]
        st = self.goes_states({h1: FakeResponse(s3_body(keys, key_count=99), 200)})
        self.assertEqual({v for k, v in st.items() if k.startswith("2026-10-10T01")}, {"UNKNOWN"})

    def test_goes_continuation_token_is_followed(self):
        h1 = T0 + timedelta(hours=1)
        keys = [goes_key(b) for b in all_slots(h1, h1 + timedelta(hours=1), 10)]
        def pages(url):
            if "continuation-token" in url:
                return FakeResponse(s3_body(keys[3:]), 200)
            return FakeResponse(s3_body(keys[:3], truncated=True, token="tok+/="), 200)
        st = self.goes_states({h1: pages})
        self.assertEqual({v for k, v in st.items() if k.startswith("2026-10-10T01")}, {"MISSING_RETRYING"})


# ------------------------------------------------------------------------------------------------- safety, idempotence
class Safety(Base):
    def test_contract_guards_and_manual_only(self):
        c = json.loads(L.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(c["execution"], "MANUAL_ONLY")
        for p in c["products"].values():
            self.assertNotEqual((p.get("retention") or {}).get("status"), "VERIFIED", "retention must be verified before enabling UNRECOVERABLE")
        bad = self.tmp / "c.json"
        c["operational_alerting_enabled"] = True
        bad.write_text(json.dumps(c), encoding="utf-8")
        with self.assertRaises(ValueError):
            L.load_contract(bad)

    def test_allow_list_refuses_every_download(self):
        for url in ["https://noaa-goes19.s3.amazonaws.com/" + goes_key(T0),
                    "https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-CMIPF/2026/283/00/&max-keys=1000",
                    "https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGHHE.07/2026/283/" + imerg_title(T0),
                    "https://cmr.earthdata.nasa.gov/search/granules.json?short_name=GPM_3IMERGHHL&version=07&temporal%5B%5D=2026-10-10T00:00:00Z,2026-10-11T00:00:00Z&page_size=2000&sort_key=start_date",
                    "http://cmr.earthdata.nasa.gov/search/granules.json"]:
            opener = FakeOpener(lambda u, h: FakeResponse(b"x"))
            with self.assertRaises(ValueError):
                L.http_get(url, self.contract, opener=opener, sleep=NO_SLEEP)
            self.assertEqual(opener.urls, [], "a refused URL must never reach the network")

    def test_window_limits(self):
        opener = FakeOpener(lambda u, h: FakeResponse(b""))
        with self.assertRaises(ValueError):
            L.fetch(T0, T0 + timedelta(hours=193), self.tmp / "a", self.contract, opener=opener, sleep=NO_SLEEP, clock=clock_at(T0 + timedelta(days=30)))
        with self.assertRaises(ValueError):
            L.fetch(T0, T0 + timedelta(hours=2), self.tmp / "b", self.contract, opener=opener, sleep=NO_SLEEP, clock=clock_at(T0))
        self.assertEqual(opener.urls, [])

    def test_outputs_never_touch_existing_scientific_files(self):
        for p in ("site/data/calibration/x.json", "data/v09/rain/x.json", "config/x.json"):
            with self.assertRaises(ValueError):
                L.guarded_output(L.ROOT / p)
        L.guarded_output(L.ROOT / "data/v09/capture_ledger/snapshots/x/ledger_v0_1.json")
        L.guarded_output(self.tmp / "elsewhere.json")

    def test_idempotent_and_immutable(self):
        start, end = T0, T0 + timedelta(hours=2)
        self.capture(imerg=[T0], goes=[T0])
        opener = FakeOpener(scenario(imerg_handler(all_slots(start, end, 30)[1:]), goes_handler(all_slots(start, end, 10)[1:])))
        _, ledger, out = self.run_ledger(opener, start, end, T0 + timedelta(days=2))
        a, b = self.tmp / "l1.json", self.tmp / "l2.json"
        L.write_ledger(ledger, a)
        L.write_ledger(L.build(out, self.contract, root=self.root, history=False), b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        L.write_ledger(ledger, a)  # same content: no-op
        changed = copy.deepcopy(ledger)
        changed["intervals"][0]["state"] = "UNKNOWN"
        with self.assertRaises(FileExistsError):
            L.write_ledger(changed, a)
        with self.assertRaises(FileExistsError):
            L.fetch(start, end, out, self.contract, opener=opener, sleep=NO_SLEEP, clock=clock_at(T0 + timedelta(days=2)))

    def test_building_does_not_modify_repository_files(self):
        watched = [p for d in ("data", "site/data", "config") for p in (ROOT / d).rglob("*") if p.is_file()]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
        start, end = T0, T0 + timedelta(hours=1)
        opener = FakeOpener(scenario(imerg_handler(all_slots(start, end, 30)), goes_handler(all_slots(start, end, 10))))
        out = self.tmp / "resp"
        L.fetch(start, end, out, self.contract, opener=opener, sleep=NO_SLEEP, clock=clock_at(T0 + timedelta(days=2)))
        L.write_ledger(L.build(out, self.contract, root=ROOT, history=False), self.tmp / "ledger.json")
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
        self.assertEqual(before, after)
        self.assertEqual({p for d in ("data", "site/data", "config") for p in (ROOT / d).rglob("*") if p.is_file()}, set(watched))

    def test_ledger_carries_no_precipitation_values(self):
        start, end = T0, T0 + timedelta(hours=1)
        self.capture(imerg=[T0], goes=[T0])  # local archives do hold rates: they must not leak into the ledger
        opener = FakeOpener(scenario(imerg_handler(all_slots(start, end, 30)), goes_handler(all_slots(start, end, 10))))
        _, ledger, _ = self.run_ledger(opener, start, end, T0 + timedelta(days=2))
        keys = set()
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    keys.add(k)
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(ledger)
        words = {"rate", "mm", "precip", "precipitation", "accum", "accumulation", "rain", "rainfall", "value", "values", "targets"}
        leaked = {k for k in keys - {"contains_precipitation_values"} if set(re.split(r"[_\W]+", k.lower())) & words}
        self.assertFalse(leaked, keys)
        for g, v in L.GUARDS.items():
            self.assertEqual(ledger[g], v)
        self.assertIs(ledger["contains_precipitation_values"], False)

    def test_capture_evidence_survives_pruning_through_git_history(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        g = lambda *a: subprocess.run(["git", "-C", str(self.root), *a], check=True, capture_output=True, text=True).stdout  # noqa: E731
        g("init", "-q")
        g("config", "user.email", "t@example.invalid")
        g("config", "user.name", "t")
        self.capture(imerg=[T0, T0 + timedelta(minutes=30)])
        g("add", "-A")
        g("commit", "-q", "-m", "first", "--date", "2026-10-10T08:00:00Z")
        first = g("rev-parse", "HEAD").strip()
        self.capture(imerg=[T0 + timedelta(minutes=30)])  # retention prunes 00:00 from the current file
        g("commit", "-q", "-am", "second", "--date", "2026-10-11T08:00:00Z")
        caps = L.captures(self.root, self.contract, "IMERG_EARLY_HH", T0, history=True)
        self.assertEqual(caps[T0][0]["git_commit"], first)
        self.assertNotIn(T0, L.captures(self.root, self.contract, "IMERG_EARLY_HH", T0, history=False))


class ManualWorkflowContract(unittest.TestCase):
    def test_workflow_is_manual_read_only_and_never_downloads(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        on = text[text.index("\non:"):text.index("\npermissions:")]
        self.assertIn("workflow_dispatch:", on)
        for trigger in ("schedule", "push", "pull_request", "workflow_run", "repository_dispatch", "cron"):
            self.assertNotIn(trigger, on)
        self.assertRegex(text, r"\npermissions:\n  contents: read\n")
        self.assertNotIn("contents: write", text)
        for forbidden in ("git push", "git commit", "earthaccess", "curl ", "wget ", "aws s3 cp", "secrets."):
            self.assertNotIn(forbidden, text)
        self.assertIn("python scripts/v09_capture_ledger.py run", text)
        self.assertIn("runs-on: ubuntu-24.04", text)


if __name__ == "__main__":
    unittest.main()
