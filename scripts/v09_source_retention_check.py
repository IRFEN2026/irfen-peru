"""Source availability and retention evidence for IMERG Early v07 (NASA GES DISC via CMR) and GOES-19 ABI-L2-RRQPEF (NOAA).

Step 1 of docs/V09_CAPTURE_RECOVERY_DESIGN.md. RESEARCH_ONLY / TEST_ONLY, manual execution only.
  fetch  catalog metadata (CMR collection records, granule counts per year and per day, oldest/newest granule; S3 prefix
         listings per year/day) and official documentation pages, through an allow-list that refuses every data URL:
         nothing is downloaded. Every raw response is stored gzip-compressed and named by the SHA-256 of its bytes.
  build  derives, deterministically from those stored responses only, per-day/per-year availability at the source and the
         retention statements found in the archived documents.

An empty answer, an HTTP error or a truncated listing is UNKNOWN, never 'absent at source'. UNRECOVERABLE is never
derived here: it would need an archived official policy with an expiry period, and none is assumed.

Usage:
  python scripts/v09_source_retention_check.py fetch --out DIR
  python scripts/v09_source_retention_check.py build --responses DIR --out DIR/evidence_v0_1.json
  python scripts/v09_source_retention_check.py run --out DIR
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import importlib.util
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, build_opener
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/v09_source_retention_contract_v0_1.json"
OUT_DIR = ROOT / "data/v09/source_retention"
_spec = importlib.util.spec_from_file_location("v09_capture_ledger", ROOT / "scripts/v09_capture_ledger.py")
LEDGER = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LEDGER)
GUARDS = LEDGER.GUARDS
S3_NS = LEDGER.S3_NS
CMR = "https://cmr.earthdata.nasa.gov/search"


class _NoRedirect(HTTPRedirectHandler):
    """A redirect could lead outside the allow-list: it is recorded as an HTTP 3xx error instead of being followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


NO_REDIRECT_OPEN = build_opener(_NoRedirect).open
S3 = "https://noaa-goes19.s3.amazonaws.com/"


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    c = json.loads(path.read_text(encoding="utf-8"))
    for k, v in GUARDS.items():
        if c.get(k) != v:
            raise ValueError(f"contract guard {k} must be {v!r}")
    if c.get("execution") != "MANUAL_ONLY":
        raise ValueError("contract execution must be MANUAL_ONLY")
    return c


def guarded_output(path: Path) -> Path:
    path = path.resolve()
    if path == ROOT or ROOT in path.parents:
        if not (path == OUT_DIR or OUT_DIR in path.parents):
            raise ValueError(f"output inside the repository must be under {OUT_DIR.relative_to(ROOT)}: {path}")
    return path


def days(c: dict) -> list[date]:
    d0, d1 = LEDGER.utc(c["window_days"]["from_utc"]).date(), LEDGER.utc(c["window_days"]["to_utc"]).date()
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days)]


def t_range(d0: datetime, d1: datetime) -> str:
    return quote(f"{LEDGER.iso(d0)},{LEDGER.iso(d1)}", safe=":,")


def granules_url(c: dict, start: datetime, end: datetime, page_size: int) -> str:
    i = c["imerg"]
    return (f"{CMR}/granules.json?short_name={i['short_name']}&version={i['version']}&temporal%5B%5D={t_range(start, end)}"
            f"&page_size={page_size}&sort_key=start_date")


def s3_prefixes_url(prefix: str) -> str:
    return f"{S3}?list-type=2&prefix={prefix}&delimiter=/&max-keys=1000"


def s3_keys_url(prefix: str, token: str | None = None) -> str:
    return f"{S3}?list-type=2&prefix={prefix}&max-keys=1000" + (f"&continuation-token={quote(token, safe='')}" if token else "")


def parse_prefixes(body: bytes) -> dict:
    try:
        root = ElementTree.fromstring(body)
        if not root.tag.endswith("ListBucketResult"):
            raise ValueError(f"unexpected root {root.tag}")
        truncated = (root.findtext("s3:IsTruncated", namespaces=S3_NS) or "").strip().lower()
        if truncated not in ("true", "false"):
            raise ValueError("IsTruncated missing")
        prefixes = [p.findtext("s3:Prefix", namespaces=S3_NS) for p in root.findall("s3:CommonPrefixes", S3_NS)]
        return dict(prefixes=sorted(p for p in prefixes if p), is_truncated=truncated == "true", error=None)
    except Exception as exc:
        return dict(prefixes=[], is_truncated=None, error=f"MALFORMED_S3_LISTING: {type(exc).__name__}: {exc}"[:300])


# ------------------------------------------------------------------------------------------------------------ fetching
def fetch(out_dir: Path, c: dict, opener=NO_REDIRECT_OPEN, sleep=time.sleep, clock=None) -> dict:
    clock = clock or (lambda: datetime.now(timezone.utc))
    out_dir = guarded_output(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} exists: response snapshots are immutable")
    (out_dir / "raw").mkdir(parents=True)
    http_contract = {"allowed_url_patterns": c["allowed_url_patterns"], "limits": c["limits"]}
    if LEDGER.utc(c["window_days"]["to_utc"]) > clock():
        raise ValueError("window ends in the future")
    reqs: list[dict] = []

    def get(kind, url, **extra):
        rec, body = LEDGER.http_get(url, http_contract, None, opener, sleep, clock)
        rec = dict(request_id=f"R{len(reqs) + 1:04d}", kind=kind, **extra, **rec)
        if body is not None:
            (out_dir / "raw" / f"{rec['sha256']}.bin.gz").write_bytes(gzip.compress(body, mtime=0))
        reqs.append(rec)
        sleep(c["limits"]["pause_between_requests_seconds"])
        return rec, body

    started = LEDGER.iso(clock())
    i = c["imerg"]
    # --- IMERG Early v07 (CMR): collection records, oldest/newest granule, per-year and per-day counts.
    get("CMR_COLLECTION", f"{CMR}/collections.umm_json?short_name={i['short_name']}&version={i['version']}")
    get("CMR_COLLECTION_ALL_VERSIONS", f"{CMR}/collections.umm_json?short_name={i['short_name']}")
    get("CMR_OLDEST_GRANULE", f"{CMR}/granules.json?short_name={i['short_name']}&version={i['version']}&sort_key=start_date&page_size=1")
    get("CMR_NEWEST_GRANULE", f"{CMR}/granules.json?short_name={i['short_name']}&version={i['version']}&sort_key=-start_date&page_size=1")
    w_end = LEDGER.utc(c["window_days"]["to_utc"])
    for y in range(i["years"][0], i["years"][1] + 1):
        y0 = datetime(y, 1, 1, tzinfo=timezone.utc)
        y1 = min(datetime(y + 1, 1, 1, tzinfo=timezone.utc), w_end) - timedelta(seconds=1)
        get("CMR_YEAR_COUNT", granules_url(c, y0, y1, 1), year=y)
    for d in days(c):
        d0 = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        rec, _ = get("CMR_DAY_COUNT", granules_url(c, d0, d0 + timedelta(days=1) - timedelta(seconds=1), 1), day=d.isoformat())
        hits = rec["response_headers"].get("CMR-Hits") if rec["ok"] else None
        if hits is not None and hits.isdigit() and int(hits) != i["expected_per_day"]:
            get("CMR_DAY_LIST", granules_url(c, d0, d0 + timedelta(days=1) - timedelta(seconds=1), 100), day=d.isoformat())
    # --- GOES-19 RRQPEF (S3): years -> days -> oldest day's hours -> oldest hour's objects; per-day objects in window.
    g = c["goes"]
    root_prefix = f"{g['product_prefix']}/"
    _, body = get("S3_YEARS", s3_prefixes_url(root_prefix))
    years = parse_prefixes(body)["prefixes"] if body else []
    oldest_day = None
    for yp in years:
        _, b = get("S3_YEAR_DAYS", s3_prefixes_url(yp), prefix=yp)
        dp = parse_prefixes(b)["prefixes"] if b else []
        if dp and oldest_day is None:
            oldest_day = dp[0]
    if oldest_day:
        _, b = get("S3_OLDEST_DAY_HOURS", s3_prefixes_url(oldest_day), prefix=oldest_day)
        hp = parse_prefixes(b)["prefixes"] if b else []
        if hp:
            get("S3_OLDEST_HOUR_OBJECTS", s3_keys_url(hp[0]), prefix=hp[0])
    for d in days(c):
        prefix = f"{g['product_prefix']}/{d:%Y}/{d.timetuple().tm_yday:03d}/"
        token, page = None, 1
        while True:
            rec, b = get("S3_DAY_OBJECTS", s3_keys_url(prefix, token), day=d.isoformat(), page=page)
            token = None
            if b is not None:
                p = LEDGER.parse_s3(b)
                if p["error"] is None and p["is_truncated"] and p["next_token"]:
                    token, page = p["next_token"], page + 1
            if not token or page > 10:
                break
    # --- Official documentation (raw, archived).
    for doc in c["documents"]:
        get("DOCUMENT", doc["url"], document_id=doc["id"])
    manifest = dict(schema_version="0.1", manifest_id="irfen-v09-source-retention-responses:v0.1", **GUARDS,
                    tool="scripts/v09_source_retention_check.py fetch", contract_sha256=LEDGER.sha256(CONTRACT_PATH.read_bytes()),
                    fetched_started_at_utc=started, fetched_finished_at_utc=LEDGER.iso(clock()),
                    downloads_of_granules_or_scans=0, requests=reqs)
    (out_dir / "requests.json").write_bytes(LEDGER.dumps(manifest))
    return manifest


# ------------------------------------------------------------------------------------------------------------- building
class Store:
    def __init__(self, out_dir: Path, manifest: dict):
        self.dir, self.reqs = out_dir, manifest["requests"]
        self.problems: list[str] = []

    def body(self, rec: dict) -> bytes | None:
        if not rec["ok"]:
            return None
        data = gzip.decompress((self.dir / "raw" / f"{rec['sha256']}.bin.gz").read_bytes())
        if LEDGER.sha256(data) != rec["sha256"]:
            self.problems.append(f"{rec['request_id']}: stored bytes do not match their SHA-256")
            return None
        return data

    def of(self, kind: str, **match) -> list[dict]:
        return [r for r in self.reqs if r["kind"] == kind and all(r.get(k) == v for k, v in match.items())]


def _hits(rec: dict) -> int | None:
    h = (rec.get("response_headers") or {}).get("CMR-Hits") if rec["ok"] else None
    return int(h) if h is not None and str(h).isdigit() else None


def _text(data: bytes) -> str:
    t = data.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def _snippets(text: str, terms: list[str], width: int = 110) -> list[dict]:
    out = []
    for term in terms:
        for m in re.finditer(re.escape(term), text, re.I):
            s = text[max(0, m.start() - width):m.end() + width].strip()
            out.append(dict(term=term, offset=m.start(), context=s))
    return sorted(out, key=lambda x: (x["offset"], x["term"]))


def imerg_evidence(st: Store, c: dict) -> dict:
    i = c["imerg"]
    coll = {}
    for kind in ("CMR_COLLECTION", "CMR_COLLECTION_ALL_VERSIONS"):
        rec = st.of(kind)[0] if st.of(kind) else None
        b = st.body(rec) if rec else None
        if b is None:
            coll[kind] = dict(status="UNKNOWN", request_id=rec and rec["request_id"], error=rec and rec["error"])
            continue
        try:
            items = json.loads(b)["items"]
            rows = []
            for it in items:
                u, meta = it["umm"], it["meta"]
                ranges = [r for te in u.get("TemporalExtents") or [] for r in te.get("RangeDateTimes") or []]
                rows.append(dict(concept_id=meta.get("concept-id"), revision_date=meta.get("revision-date"), short_name=u.get("ShortName"),
                                 version=u.get("Version"), entry_title=u.get("EntryTitle"), collection_progress=u.get("CollectionProgress"),
                                 beginning=[r.get("BeginningDateTime") for r in ranges], ending=[r.get("EndingDateTime") for r in ranges],
                                 ends_at_present=[te.get("EndsAtPresentFlag") for te in u.get("TemporalExtents") or []],
                                 archive_centers=[d.get("ShortName") for d in u.get("DataCenters") or [] if "ARCHIVER" in (d.get("Roles") or [])],
                                 doi=(u.get("DOI") or {}).get("DOI"),
                                 abstract_retention_statements=_snippets(re.sub(r"\s+", " ", u.get("Abstract") or ""), c["retention_terms"], 160)))
            coll[kind] = dict(status="OK", request_id=rec["request_id"], hits=_hits(rec) if _hits(rec) is not None else len(items),
                              collections=sorted(rows, key=lambda r: (r["version"] or "", r["concept_id"] or "")))
        except Exception as exc:
            coll[kind] = dict(status="UNKNOWN", request_id=rec["request_id"], error=f"MALFORMED: {type(exc).__name__}: {exc}"[:200])

    def edge(kind):
        rec = st.of(kind)[0] if st.of(kind) else None
        b = st.body(rec) if rec else None
        parsed = LEDGER.parse_cmr(b) if b is not None else None
        if not parsed or parsed["error"] or not parsed["entries"]:
            return dict(status="UNKNOWN", request_id=rec and rec["request_id"])
        e = parsed["entries"][0]
        return dict(status="OK", request_id=rec["request_id"], total_hits=_hits(rec), time_start=e["time_start"], title=e["title"], id=e["id"])

    years = []
    for rec in st.of("CMR_YEAR_COUNT"):
        y = rec["year"]
        y0 = date(y, 1, 1)
        y1 = min(date(y + 1, 1, 1), LEDGER.utc(c["window_days"]["to_utc"]).date())
        expected = (y1 - y0).days * i["expected_per_day"]
        h = _hits(rec) if st.body(rec) is not None else None
        years.append(dict(year=y, request_id=rec["request_id"], cmr_hits=h, expected=expected,
                          status="UNKNOWN" if h is None else ("UNKNOWN_EMPTY" if h == 0 else ("COMPLETE" if h == expected else "DIFFERS")),
                          difference=None if h is None else h - expected))
    per_day = []
    for rec in st.of("CMR_DAY_COUNT"):
        d = rec["day"]
        h = _hits(rec) if st.body(rec) is not None else None
        row = dict(day=d, request_id=rec["request_id"], cmr_hits=h, expected=i["expected_per_day"])
        if h is None:
            row.update(status="UNKNOWN", reason=rec.get("error") or "CMR-Hits missing")
        elif h == 0:
            row.update(status="UNKNOWN_EMPTY", reason="an empty catalog answer never confirms absence")
        elif h == i["expected_per_day"]:
            row.update(status="COMPLETE_AT_SOURCE")
        else:
            lst = st.of("CMR_DAY_LIST", day=d)
            b = st.body(lst[0]) if lst else None
            p = LEDGER.parse_cmr(b) if b is not None else None
            if not p or p["error"] or len(p["entries"]) != h:
                row.update(status="UNKNOWN", reason="per-slot listing missing, malformed or incomplete")
            else:
                d0 = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
                present = {LEDGER.floor_to(LEDGER.utc(e["time_start"]), i["interval_minutes"]) for e in p["entries"]}
                slots = [d0 + timedelta(minutes=i["interval_minutes"] * k) for k in range(i["expected_per_day"])]
                row.update(status="INCOMPLETE_AT_SOURCE" if h < i["expected_per_day"] else "MORE_THAN_EXPECTED",
                           list_request_id=lst[0]["request_id"],
                           slots_not_listed=[LEDGER.iso(s) for s in slots if s not in present])
        per_day.append(row)
    return dict(product=f"{i['short_name']} v{i['version']}", collection=coll, oldest_granule=edge("CMR_OLDEST_GRANULE"),
                newest_granule=edge("CMR_NEWEST_GRANULE"), per_year=years, per_day=per_day,
                per_day_summary={s: sum(1 for r in per_day if r["status"] == s) for s in
                                 ("COMPLETE_AT_SOURCE", "INCOMPLETE_AT_SOURCE", "MORE_THAN_EXPECTED", "UNKNOWN_EMPTY", "UNKNOWN")})


def goes_evidence(st: Store, c: dict) -> dict:
    g = c["goes"]

    def prefixes(rec):
        b = st.body(rec) if rec else None
        p = parse_prefixes(b) if b is not None else None
        if not p or p["error"] or p["is_truncated"]:
            return None
        return p["prefixes"]

    yrec = st.of("S3_YEARS")
    years = prefixes(yrec[0]) if yrec else None
    per_year = []
    for rec in st.of("S3_YEAR_DAYS"):
        dp = prefixes(rec)
        if dp is None or not dp:
            per_year.append(dict(prefix=rec["prefix"], request_id=rec["request_id"], status="UNKNOWN"))
            continue
        doys = sorted(int(p.rstrip("/").rsplit("/", 1)[1]) for p in dp)
        per_year.append(dict(prefix=rec["prefix"], request_id=rec["request_id"], status="OK", day_prefixes=len(doys),
                             first_doy=doys[0], last_doy=doys[-1],
                             doys_missing_between_first_and_last=[d for d in range(doys[0], doys[-1] + 1) if d not in doys]))
    oldest = None
    orec = st.of("S3_OLDEST_HOUR_OBJECTS")
    if orec:
        b = st.body(orec[0])
        p = LEDGER.parse_s3(b) if b is not None else None
        if p and not p["error"] and p["keys"]:
            info = [LEDGER.goes_key_info(k["key"]) for k in p["keys"]]
            first = min((x for x in info if x), key=lambda x: x["scan_start"], default=None)
            oldest = dict(status="OK", request_id=orec[0]["request_id"], prefix=orec[0]["prefix"],
                          oldest_scan_start=LEDGER.iso(first["scan_start"]) if first else None, objects_in_hour=len(p["keys"]))
    per_day = []
    for d in days(c):
        recs = st.of("S3_DAY_OBJECTS", day=d.isoformat())
        keys, problems = [], []
        for rec in recs:
            b = st.body(rec)
            p = LEDGER.parse_s3(b) if b is not None else None
            if p is None:
                problems.append(f"{rec['request_id']}: {rec.get('error') or 'no body'}")
            elif p["error"]:
                problems.append(f"{rec['request_id']}: {p['error']}")
            else:
                keys += p["keys"]
                if p["is_truncated"] and rec is recs[-1]:
                    problems.append("listing truncated and not fully followed")
        info = [LEDGER.goes_key_info(k["key"]) for k in keys]
        modes = {}
        for x in info:
            if x:
                modes[x["mode"]] = modes.get(x["mode"], 0) + 1
        row = dict(day=d.isoformat(), request_ids=[r["request_id"] for r in recs], objects=len(keys), by_mode=dict(sorted(modes.items())),
                   expected_m6=g["expected_per_day_m6"], bytes_listed=sum(k["size_bytes"] for k in keys))
        if not recs or problems:
            row.update(status="UNKNOWN", reason="; ".join(problems) or "not queried")
        elif not keys:
            row.update(status="UNKNOWN_EMPTY", reason="an empty listing never confirms absence")
        elif any(x is None for x in info) or set(modes) != {g["expected_scan_mode"]}:
            row.update(status="UNKNOWN_MODE", reason=f"scan modes {sorted(modes)}: 10-min grid not applicable")
        else:
            d0 = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            present = {LEDGER.floor_to(x["scan_start"], g["interval_minutes"]) for x in info}
            bins = [d0 + timedelta(minutes=g["interval_minutes"] * k) for k in range(g["expected_per_day_m6"])]
            missing = [LEDGER.iso(b) for b in bins if b not in present]
            row.update(status="COMPLETE_AT_SOURCE" if not missing else "INCOMPLETE_AT_SOURCE", bins_not_listed=missing)
        per_day.append(row)
    return dict(product=f"{g['bucket']}/{g['product_prefix']}", years_listed=years, per_year=per_year, oldest_object=oldest or dict(status="UNKNOWN"),
                per_day=per_day, per_day_summary={s: sum(1 for r in per_day if r["status"] == s) for s in
                                                  ("COMPLETE_AT_SOURCE", "INCOMPLETE_AT_SOURCE", "UNKNOWN_MODE", "UNKNOWN_EMPTY", "UNKNOWN")})


def documents(st: Store, c: dict) -> list[dict]:
    out = []
    for doc in c["documents"]:
        recs = st.of("DOCUMENT", document_id=doc["id"])
        b = st.body(recs[0]) if recs else None
        if b is None:
            out.append(dict(id=doc["id"], url=doc["url"], publisher=doc["publisher"], status="UNKNOWN",
                            error=recs[0]["error"] if recs else "not queried"))
            continue
        text = _text(b)
        out.append(dict(id=doc["id"], url=doc["url"], publisher=doc["publisher"], status="OK", request_id=recs[0]["request_id"],
                        sha256=recs[0]["sha256"], retrieved_at_utc=recs[0]["requested_at_utc"],
                        expected_quotes={q: q in text or q in b.decode("utf-8", "replace") for q in doc["quotes"]},
                        retention_statements=_snippets(text, c["retention_terms"])))
    return out


def assess(imerg: dict, goes: dict, docs: list[dict]) -> dict:
    """Mechanical facts only; the reading of the snippets is human and lives in docs/V09_SOURCE_RETENTION.md."""
    snippets = [s for d in docs for s in d.get("retention_statements", [])]
    abstract = [s for v in imerg["collection"].values() for col in v.get("collections", []) for s in col["abstract_retention_statements"]]
    return dict(
        unrecoverable_assignable=False,
        unrecoverable_reason="No archived official document states a retention or deletion period for either source; UNRECOVERABLE stays disabled.",
        documents_ok=sum(1 for d in docs if d["status"] == "OK"), documents_total=len(docs),
        retention_statement_snippets=len(snippets) + len(abstract),
        imerg_observed=dict(oldest=imerg["oldest_granule"].get("time_start"), newest=imerg["newest_granule"].get("time_start"),
                            window=imerg["per_day_summary"]),
        goes_observed=dict(oldest=(goes["oldest_object"] or {}).get("oldest_scan_start"), window=goes["per_day_summary"]),
        meaning="Observed availability is what the catalogs list at query time; it is not a guarantee of future availability.",
    )


def build(out_dir: Path, c: dict) -> dict:
    manifest = json.loads((out_dir / "requests.json").read_text(encoding="utf-8"))
    for k, v in GUARDS.items():
        if manifest.get(k) != v:
            raise ValueError(f"responses manifest guard {k} must be {v!r}")
    st = Store(out_dir, manifest)
    imerg, goes, docs = imerg_evidence(st, c), goes_evidence(st, c), documents(st, c)
    return dict(schema_version="0.1", evidence_id="irfen-v09-source-retention-evidence:v0.1", **GUARDS, execution="MANUAL_ONLY",
                downloads_of_granules_or_scans=0, contains_precipitation_values=False,
                contract_sha256=LEDGER.sha256(CONTRACT_PATH.read_bytes()),
                responses_manifest_sha256=LEDGER.sha256((out_dir / "requests.json").read_bytes()),
                queried_from_utc=manifest["fetched_started_at_utc"], queried_to_utc=manifest["fetched_finished_at_utc"],
                window_days=c["window_days"], integrity_problems=sorted(set(st.problems)),
                requests=[{k: r.get(k) for k in ("request_id", "kind", "url", "requested_at_utc", "http_status", "ok", "error", "sha256", "bytes")}
                          for r in manifest["requests"]],
                imerg=imerg, goes=goes, documents=docs, assessment=assess(imerg, goes, docs))


def write(evidence: dict, out: Path) -> Path:
    out = guarded_output(out)
    data = LEDGER.dumps(evidence)
    if out.exists() and out.read_bytes() != data:
        raise FileExistsError(f"{out} exists with different content")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        out.write_bytes(data)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "run"):
        sub.add_parser(name).add_argument("--out", required=True, type=Path)
    b = sub.add_parser("build")
    b.add_argument("--responses", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    c = load_contract()
    if args.cmd in ("fetch", "run"):
        m = fetch(args.out, c)
        print(f"requests={len(m['requests'])} not_ok={sum(1 for r in m['requests'] if not r['ok'])}")
        if args.cmd == "fetch":
            return 0
        args.responses, args.out = args.out, args.out / "evidence_v0_1.json"
    ev = build(args.responses, c)
    write(ev, args.out)
    print(json.dumps(ev["assessment"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
