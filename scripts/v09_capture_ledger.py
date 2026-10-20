"""Expected-interval capture ledger for IMERG Early (30 min) and GOES-19 RRQPEF (10 min scans). RESEARCH_ONLY / TEST_ONLY.

Two separate steps:
  fetch  queries only the NASA CMR granule search and the NOAA S3 ListObjectsV2 listing (catalog metadata; an allow-list
         refuses every other URL, so no granule or scan is ever downloaded) and stores each raw response with its SHA-256
         in a new, immutable directory, together with requests.json (URL, time, HTTP status, error, attempts).
  build  turns those stored responses plus IRFEN's own archives (read through git history) into a ledger with one row per
         expected interval: product, version, UTC interval, state, evidence, query time and verifiable provenance.
         Deterministic: the same responses and the same repository HEAD give byte-identical output.

States: CAPTURED, PENDING_SOURCE_LATENCY, MISSING_RETRYING, ABSENT_AT_SOURCE, UNRECOVERABLE, UNKNOWN (see the contract).
An empty response, an HTTP error, a timeout, a malformed or truncated listing never becomes ABSENT_AT_SOURCE.
No precipitation value is read or written. Manual execution only (workflow_dispatch); nothing here is scheduled.

Usage:
  python scripts/v09_capture_ledger.py fetch --from 2026-10-13T00:00Z --to 2026-10-20T00:00Z --out DIR
  python scripts/v09_capture_ledger.py build --responses DIR --out DIR/ledger_v0_1.json [--no-history]
  python scripts/v09_capture_ledger.py run   --from ... --to ... --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/v09_capture_ledger_contract_v0_1.json"
LEDGER_DIR = ROOT / "data/v09/capture_ledger"
USER_AGENT = "IRFEN-v0.9-capture-ledger-TEST-ONLY/0.1 (+https://github.com/IRFEN2026/irfen-peru)"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
GOES_KEY = re.compile(r"OR_ABI-L2-RRQPEF-(?P<mode>M\d)_(?P<sat>G\d\d)_s(?P<s>\d{14})_e(?P<e>\d{14})_c(?P<c>\d{14})\.nc$")
IMERG_VERSION = re.compile(r"\.(V\d\d[A-Z]?)\.HDF5$")
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)
STATES = ("CAPTURED", "PENDING_SOURCE_LATENCY", "MISSING_RETRYING", "ABSENT_AT_SOURCE", "UNRECOVERABLE", "UNKNOWN")


# ----------------------------------------------------------------------------------------------------------- utilities
def utc(value) -> datetime:
    if isinstance(value, datetime):
        d = value
    else:
        d = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def iso(d: datetime | None) -> str | None:
    return None if d is None else d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def floor_to(d: datetime, minutes: int) -> datetime:
    d = d.replace(second=0, microsecond=0)
    return d - timedelta(minutes=d.minute % minutes)


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    contract = json.loads(path.read_text(encoding="utf-8"))
    for k, v in GUARDS.items():
        if contract.get(k) != v:
            raise ValueError(f"contract guard {k} must be {v!r}")
    if contract.get("execution") != "MANUAL_ONLY":
        raise ValueError("contract execution must be MANUAL_ONLY")
    return contract


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def check_url(url: str, contract: dict) -> None:
    """Only catalog searches / bucket listings are allowed: never a granule, scan or any other URL."""
    if not any(re.fullmatch(p, url) for p in contract["allowed_url_patterns"]):
        raise ValueError(f"URL not allowed by the capture-ledger contract (catalog metadata only): {url}")


def guarded_output(path: Path) -> Path:
    """Outputs go to data/v09/capture_ledger/ or outside the repository; never over existing scientific files."""
    path = path.resolve()
    if path == ROOT or ROOT in path.parents:
        if not (path == LEDGER_DIR or LEDGER_DIR in path.parents):
            raise ValueError(f"output inside the repository must be under {LEDGER_DIR.relative_to(ROOT)}: {path}")
    return path


# ------------------------------------------------------------------------------------------------------------ fetching
def http_get(url: str, contract: dict, headers: dict | None = None, opener=urlopen, sleep=time.sleep, clock=None) -> tuple[dict, bytes | None]:
    """GET with bounded attempts. Returns (record, body). Errors are recorded, never raised and never mean 'absent'."""
    check_url(url, contract)
    lim = contract["limits"]
    clock = clock or (lambda: datetime.now(timezone.utc))
    record = dict(url=url, request_headers=dict(sorted((headers or {}).items())), requested_at_utc=iso(clock()), attempts=[],
                  http_status=None, ok=False, error=None, sha256=None, bytes=None, response_headers={})
    body = None
    for attempt in range(1, lim["attempts"] + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})})
            with opener(req, timeout=lim["timeout_seconds"]) as resp:
                data = resp.read(lim["max_response_bytes"] + 1)
                status = getattr(resp, "status", None)
                rh = {k: resp.headers.get(k) for k in ("Content-Type", "CMR-Hits", "CMR-Search-After", "CMR-Request-Id")
                      if resp.headers.get(k) is not None}
            if len(data) > lim["max_response_bytes"]:
                record["attempts"].append(dict(attempt=attempt, http_status=status, error="RESPONSE_TOO_LARGE"))
                record.update(http_status=status, error="RESPONSE_TOO_LARGE")
                return record, None
            record["attempts"].append(dict(attempt=attempt, http_status=status, error=None))
            record.update(http_status=status, ok=status == 200, error=None if status == 200 else f"HTTP_{status}",
                          sha256=sha256(data), bytes=len(data), response_headers=rh)
            body = data
            return record, body
        except HTTPError as exc:
            record["attempts"].append(dict(attempt=attempt, http_status=exc.code, error=f"HTTP_{exc.code}"))
            record.update(http_status=exc.code, error=f"HTTP_{exc.code}")
            if exc.code < 500 and exc.code != 429:
                return record, None
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            record["attempts"].append(dict(attempt=attempt, http_status=None, error=f"{type(exc).__name__}: {reason}"[:300]))
            record.update(http_status=None, error=f"{type(exc).__name__}: {reason}"[:300])
        if attempt < lim["attempts"]:
            sleep(lim["backoff_seconds"] * attempt)
    return record, None


def cmr_url(start: datetime, end: datetime, contract: dict) -> str:
    p = contract["products"]["IMERG_EARLY_HH"]
    temporal = quote(f"{iso(start)},{iso(end)}", safe=":,")
    return (f"{p['catalog_endpoint']}?short_name={p['short_name']}&version={p['version']}&temporal%5B%5D={temporal}"
            f"&page_size={contract['limits']['cmr_page_size']}&sort_key=start_date")


def s3_url(hour: datetime, contract: dict, token: str | None = None) -> str:
    p = contract["products"]["GOES19_RRQPEF"]
    url = f"{p['catalog_endpoint']}?list-type=2&prefix={p['product_prefix']}/{hour:%Y/%j/%H}/&max-keys=1000"
    return url + (f"&continuation-token={quote(token, safe='')}" if token else "")


def fetch(start: datetime, end: datetime, out_dir: Path, contract: dict, opener=urlopen, sleep=time.sleep, clock=None) -> dict:
    start, end = utc(start), utc(end)
    lim = contract["limits"]
    clock = clock or (lambda: datetime.now(timezone.utc))
    if end <= start:
        raise ValueError("--to must be after --from")
    if (end - start) > timedelta(hours=lim["max_window_hours"]):
        raise ValueError(f"window longer than {lim['max_window_hours']} h")
    if end > clock() + timedelta(minutes=1):
        raise ValueError("--to is in the future")
    out_dir = guarded_output(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} exists: response snapshots are immutable")
    (out_dir / "raw").mkdir(parents=True)
    requests = []

    def keep(product, kind, record, body, **extra):
        record = dict(request_id=f"{product}-{len(requests) + 1:04d}", product=product, kind=kind, **extra, **record)
        if body is not None:
            (out_dir / "raw" / f"{record['sha256']}.bin").write_bytes(body)
        requests.append(record)
        sleep(lim["pause_between_requests_seconds"])

    started = iso(clock())
    # IMERG Early: one CMR search over the window, paged with CMR-Search-After.
    imerg = contract["products"]["IMERG_EARLY_HH"]
    q_start = floor_to(start, imerg["interval_minutes"])
    url = cmr_url(q_start, end, contract)
    after = None
    for page in range(1, lim["max_cmr_pages"] + 1):
        rec, body = http_get(url, contract, {"CMR-Search-After": after} if after else None, opener, sleep, clock)
        keep("IMERG_EARLY_HH", "CMR_GRANULE_SEARCH", rec, body, page=page)
        after = rec["response_headers"].get("CMR-Search-After") if rec["ok"] else None
        if not after:
            break
    # GOES-19: one ListObjectsV2 per hour prefix (follows continuation tokens).
    hour = floor_to(start, 60)
    while hour < end:
        token, page = None, 1
        while True:
            rec, body = http_get(s3_url(hour, contract, token), contract, None, opener, sleep, clock)
            keep("GOES19_RRQPEF", "S3_LIST_OBJECTS_V2", rec, body, hour_utc=iso(hour), page=page)
            token = None
            if rec["ok"] and body is not None:
                parsed = parse_s3(body)
                if parsed["error"] is None and parsed["is_truncated"] and parsed["next_token"]:
                    token, page = parsed["next_token"], page + 1
            if not token or page > 20:
                break
        hour += timedelta(hours=1)
    manifest = dict(schema_version="0.1", manifest_id="irfen-v09-capture-ledger-responses:v0.1", **GUARDS,
                    tool="scripts/v09_capture_ledger.py fetch", contract_sha256=sha256(CONTRACT_PATH.read_bytes()),
                    window=dict(from_utc=iso(start), to_utc=iso(end)), fetched_started_at_utc=started,
                    fetched_finished_at_utc=iso(clock()), downloads_of_granules_or_scans=0, requests=requests)
    (out_dir / "requests.json").write_bytes(dumps(manifest))
    return manifest


# ------------------------------------------------------------------------------------------------------------- parsing
def parse_cmr(body: bytes) -> dict:
    """CMR granules.json (Atom-style JSON). Any structural doubt is an error, never an empty result."""
    try:
        feed = json.loads(body.decode("utf-8"))["feed"]
        raw = feed["entry"]
        if not isinstance(raw, list):
            raise ValueError("feed.entry is not a list")
    except Exception as exc:
        return dict(entries=[], error=f"MALFORMED_CMR_RESPONSE: {type(exc).__name__}: {exc}"[:300])
    entries, bad = [], 0
    for e in raw:
        try:
            entries.append(dict(id=e["id"], title=e.get("title") or e.get("producer_granule_id"), time_start=iso(utc(e["time_start"])),
                                time_end=iso(utc(e["time_end"])) if e.get("time_end") else None, updated=e.get("updated"),
                                collection_concept_id=e.get("collection_concept_id")))
        except Exception:
            bad += 1
    return dict(entries=entries, error=f"INVALID_CMR_ENTRIES: {bad}" if bad else None)


def parse_s3(body: bytes) -> dict:
    try:
        root = ElementTree.fromstring(body)
        if not root.tag.endswith("ListBucketResult"):
            raise ValueError(f"unexpected root {root.tag}")
        truncated = (root.findtext("s3:IsTruncated", namespaces=S3_NS) or "").strip().lower()
        if truncated not in ("true", "false"):
            raise ValueError("IsTruncated missing")
        keys = []
        for item in root.findall("s3:Contents", S3_NS):
            key = item.findtext("s3:Key", namespaces=S3_NS)
            if key and key.endswith(".nc"):
                keys.append(dict(key=key, last_modified=item.findtext("s3:LastModified", namespaces=S3_NS),
                                 etag=(item.findtext("s3:ETag", namespaces=S3_NS) or "").strip('"') or None,
                                 size_bytes=int(item.findtext("s3:Size", namespaces=S3_NS) or 0)))
        kc = root.findtext("s3:KeyCount", namespaces=S3_NS)
        if kc is not None and int(kc) != len(root.findall("s3:Contents", S3_NS)):
            raise ValueError("KeyCount does not match Contents")
        return dict(keys=keys, is_truncated=truncated == "true",
                    next_token=root.findtext("s3:NextContinuationToken", namespaces=S3_NS), error=None)
    except Exception as exc:
        return dict(keys=[], is_truncated=None, next_token=None, error=f"MALFORMED_S3_LISTING: {type(exc).__name__}: {exc}"[:300])


def goes_key_info(key: str) -> dict | None:
    m = GOES_KEY.search(key)
    if not m:
        return None
    t = lambda s: datetime.strptime(s[:13], "%Y%j%H%M%S").replace(tzinfo=timezone.utc) + timedelta(seconds=int(s[13]) / 10)
    return dict(mode=m.group("mode"), satellite=m.group("sat"), scan_start=t(m.group("s")), scan_end=t(m.group("e")),
                created=t(m.group("c")))


def imerg_version(name: str | None) -> str | None:
    m = IMERG_VERSION.search(name or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------------------------------ IRFEN capture evidence (git)
def _git(root: Path, *args) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None


def archive_versions(root: Path, rel: str, since: datetime, history: bool) -> list[tuple[str | None, str | None, dict]]:
    """[(commit, committed_at, json)] oldest first; the working-tree file last (commit None if not committed)."""
    out = []
    if history:
        log = _git(root, "log", "--reverse", f"--since={iso(since)}", "--format=%H %cI", "HEAD", "--", rel) or ""
        for line in log.splitlines():
            commit, when = line.split()
            text = _git(root, "show", f"{commit}:{rel}")
            if text:
                try:
                    out.append((commit, iso(utc(when)), json.loads(text)))
                except ValueError:
                    pass
    path = root / rel
    if path.is_file():
        head = _git(root, "rev-parse", "HEAD")
        committed = _git(root, "show", f"HEAD:{rel}")
        current = path.read_text(encoding="utf-8")
        same = committed is not None and committed == current
        out.append(((head or "").strip() or None if same else None, None, json.loads(current)))
    return out


def captures(root: Path, contract: dict, product: str, window_start: datetime, history: bool = True) -> dict:
    """{interval_start: [evidence...]} from IRFEN's own archives; first appearance per archive item."""
    p = contract["products"][product]
    step = p["interval_minutes"]
    since = window_start - timedelta(days=contract["limits"]["history_lookback_days_before_window"])
    found: dict[datetime, dict[tuple, dict]] = {}
    for arch in p["local_archives"]:
        for commit, when, data in archive_versions(root, arch["path"], since, history):
            for item in data.get(arch["list"]) or []:
                if arch.get("require_true") and not item.get(arch["require_true"]):
                    continue
                if product == "IMERG_EARLY_HH":
                    if not item.get(arch["time_field"]):
                        continue
                    start, ident = utc(item[arch["time_field"]]), item.get(arch["id_field"])
                else:
                    ident = item.get(arch["key_field"])
                    info = goes_key_info(ident or "")
                    if not info:
                        continue
                    start = info["scan_start"]
                slot = floor_to(start, step)
                key = (arch["path"], ident)
                bucket = found.setdefault(slot, {})
                if key not in bucket:
                    bucket[key] = dict(archive=arch["path"], item=ident, git_commit=commit, committed_at_utc=when,
                                       retrieved_at_utc=iso(utc(item[arch["retrieved_field"]])) if arch.get("retrieved_field") and item.get(arch["retrieved_field"]) else None)
                elif bucket[key]["git_commit"] is None and commit is not None:
                    bucket[key].update(git_commit=commit, committed_at_utc=when)
    return {slot: sorted(ev.values(), key=lambda e: (e["archive"], e["item"] or "")) for slot, ev in found.items()}


# ------------------------------------------------------------------------------------------------------- classification
def _bracketed(slot: datetime, listed: list[datetime]) -> bool:
    return any(t < slot for t in listed) and any(t > slot for t in listed)


def classify_imerg(manifest: dict, raw_dir: Path, contract: dict, caps: dict, w0: datetime, w1: datetime) -> list[dict]:
    p = contract["products"]["IMERG_EARLY_HH"]
    step = timedelta(minutes=p["interval_minutes"])
    reqs = [r for r in manifest["requests"] if r["product"] == "IMERG_EARLY_HH"]
    problems, entries = [], []
    for r in reqs:
        if not r["ok"]:
            problems.append(f"{r['request_id']}: {r['error'] or 'not ok'}")
            continue
        body = (raw_dir / f"{r['sha256']}.bin").read_bytes()
        if sha256(body) != r["sha256"]:
            problems.append(f"{r['request_id']}: stored response does not match its SHA-256")
            continue
        parsed = parse_cmr(body)
        if parsed["error"]:
            problems.append(f"{r['request_id']}: {parsed['error']}")
        entries += [dict(e, request_id=r["request_id"]) for e in parsed["entries"]]
    hits = None
    if reqs and reqs[0]["ok"]:
        try:
            hits = int(reqs[0]["response_headers"].get("CMR-Hits"))
        except (TypeError, ValueError):
            problems.append("CMR-Hits header missing or not an integer")
    if not reqs:
        problems.append("catalog not queried")
    elif hits is not None and hits != len(entries):
        problems.append(f"incomplete paging: CMR-Hits={hits}, entries received={len(entries)}")
    if reqs and not problems and not entries:
        problems.append("EMPTY_RESPONSE: an empty catalog answer never confirms absence")
    complete = not problems
    as_of = max((utc(r["requested_at_utc"]) for r in reqs), default=None)
    by_slot: dict[datetime, list] = {}
    for e in entries:
        by_slot.setdefault(floor_to(utc(e["time_start"]), p["interval_minutes"]), []).append(e)
    listed = sorted(by_slot)
    rows, slot = [], floor_to(w0, p["interval_minutes"])
    while slot < w1:
        listed_here = sorted(by_slot.get(slot, []), key=lambda e: e["id"])
        local = caps.get(slot, [])
        versions = sorted({v for v in [imerg_version(e["title"]) for e in listed_here] + [imerg_version(c["item"]) for c in local] if v})
        state, reason = _decide(slot, slot + step, local, bool(listed_here), complete, problems, listed, as_of, p)
        rows.append(dict(product="IMERG_EARLY_HH", product_name=f"{p['short_name']} v{p['version']}", product_version=versions or [f"V{p['version']}"],
                         interval_start_utc=iso(slot), interval_end_utc=iso(slot + step), state=state, reason=reason,
                         captured=local, retry_active=False,
                         catalog=dict(queried_at_utc=iso(as_of), request_ids=[r["request_id"] for r in reqs], response_complete=complete,
                                      listed=[{k: e[k] for k in ("id", "title", "time_start", "time_end", "updated", "collection_concept_id", "request_id")} for e in listed_here])))
        slot += step
    return rows


def classify_goes(manifest: dict, raw_dir: Path, contract: dict, caps: dict, w0: datetime, w1: datetime) -> list[dict]:
    p = contract["products"]["GOES19_RRQPEF"]
    step = timedelta(minutes=p["interval_minutes"])
    reqs = [r for r in manifest["requests"] if r["product"] == "GOES19_RRQPEF"]
    hours: dict[str, dict] = {}
    for r in reqs:
        h = hours.setdefault(r["hour_utc"], dict(requests=[], keys=[], problems=[], truncated_unresolved=False))
        h["requests"].append(r)
        if not r["ok"]:
            h["problems"].append(f"{r['request_id']}: {r['error'] or 'not ok'}")
            continue
        body = (raw_dir / f"{r['sha256']}.bin").read_bytes()
        if sha256(body) != r["sha256"]:
            h["problems"].append(f"{r['request_id']}: stored response does not match its SHA-256")
            continue
        parsed = parse_s3(body)
        if parsed["error"]:
            h["problems"].append(f"{r['request_id']}: {parsed['error']}")
            continue
        h["keys"] += [dict(k, request_id=r["request_id"]) for k in parsed["keys"]]
        h["truncated_unresolved"] = bool(parsed["is_truncated"])
    for hk, h in hours.items():
        if h["truncated_unresolved"]:
            h["problems"].append("listing truncated and not fully followed")
        if not h["problems"] and not h["keys"]:
            h["problems"].append("EMPTY_RESPONSE: an empty listing never confirms absence")
        modes = {(goes_key_info(k["key"]) or {}).get("mode") for k in h["keys"]}
        unparsable = [k["key"] for k in h["keys"] if not goes_key_info(k["key"])]
        if unparsable:
            h["problems"].append(f"{len(unparsable)} keys with unexpected names")
        if modes - {p["expected_scan_mode"]}:
            h["problems"].append(f"scan mode(s) {sorted(m for m in modes if m)} besides {p['expected_scan_mode']}: 10-min grid not applicable")
    by_slot: dict[datetime, list] = {}
    for h in hours.values():
        if h["problems"]:
            continue
        for k in h["keys"]:
            info = goes_key_info(k["key"])
            by_slot.setdefault(floor_to(info["scan_start"], p["interval_minutes"]), []).append(dict(k, mode=info["mode"], satellite=info["satellite"]))
    listed = sorted(by_slot)
    rows, slot = [], floor_to(w0, p["interval_minutes"])
    while slot < w1:
        h = hours.get(iso(floor_to(slot, 60)))
        problems = ["catalog not queried for this hour"] if h is None else h["problems"]
        complete = not problems
        listed_here = sorted(by_slot.get(slot, []), key=lambda k: k["key"])
        local = caps.get(slot, [])
        as_of = utc(h["requests"][-1]["requested_at_utc"]) if h else None  # when this hour was listed
        state, reason = _decide(slot, slot + step, local, bool(listed_here), complete, problems, listed, as_of, p)
        modes = sorted({k["mode"] for k in listed_here} | {(goes_key_info(c["item"] or "") or {}).get("mode") for c in local} - {None})
        rows.append(dict(product="GOES19_RRQPEF", product_name=f"{p['product_prefix']} (noaa-goes19)", product_version=[f"{m}/G19" for m in modes] or [f"{p['expected_scan_mode']}/G19 (esperado)"],
                         interval_start_utc=iso(slot), interval_end_utc=iso(slot + step), state=state, reason=reason,
                         captured=local, retry_active=False,
                         catalog=dict(queried_at_utc=iso(as_of),
                                      request_ids=[r["request_id"] for r in h["requests"]] if h else [], response_complete=complete,
                                      listed=[{k: x[k] for k in ("key", "last_modified", "etag", "size_bytes", "request_id")} for x in listed_here])))
        slot += step
    return rows


def _decide(start, end, local, listed_here, complete, problems, listed, as_of, p):
    if local:
        return "CAPTURED", "IRFEN archive contains this interval"
    if listed_here:
        return "MISSING_RETRYING", "listed by the source catalog but not captured by IRFEN (no retry is active in v0.1)"
    if not complete:
        return "UNKNOWN", "; ".join(problems)[:500]
    if as_of is None:
        return "UNKNOWN", "no catalog query time"
    if end + timedelta(hours=p["pending_horizon_hours"]) > as_of:
        return "PENDING_SOURCE_LATENCY", f"not listed yet; within the {p['pending_horizon_hours']} h source-latency horizon at {iso(as_of)}"
    ret = p.get("retention") or {}
    if ret.get("status") == "VERIFIED" and ret.get("hours") and end < as_of - timedelta(hours=ret["hours"]):
        return "UNRECOVERABLE", f"older than the verified source retention of {ret['hours']} h"
    if not _bracketed(start, listed):
        return "UNKNOWN", "not listed and not bracketed by listed intervals on both sides: absence not corroborated"
    return "ABSENT_AT_SOURCE", f"complete, non-empty catalog answer lists intervals before and after but not this one (as of {iso(as_of)})"


# ----------------------------------------------------------------------------------------------------------- the ledger
def frozen_captures_from(ledger: dict) -> dict:
    """{product: {interval_start: evidence}} taken from an existing ledger, to re-derive its classification exactly."""
    out: dict = {}
    for r in ledger["intervals"]:
        if r["captured"]:
            out.setdefault(r["product"], {})[utc(r["interval_start_utc"])] = r["captured"]
    return out


def build(responses_dir: Path, contract: dict, root: Path = ROOT, history: bool = True, frozen_captures: dict | None = None) -> dict:
    """frozen_captures replaces the git-history scan (used to re-derive a committed snapshot independently of later commits)."""
    manifest = json.loads((responses_dir / "requests.json").read_text(encoding="utf-8"))
    for k, v in GUARDS.items():
        if manifest.get(k) != v:
            raise ValueError(f"responses manifest guard {k} must be {v!r}")
    raw_dir = responses_dir / "raw"
    w0, w1 = utc(manifest["window"]["from_utc"]), utc(manifest["window"]["to_utc"])
    rows = []
    caps = (lambda prod: frozen_captures.get(prod, {})) if frozen_captures is not None else (lambda prod: captures(root, contract, prod, w0, history))
    rows += classify_imerg(manifest, raw_dir, contract, caps("IMERG_EARLY_HH"), w0, w1)
    rows += classify_goes(manifest, raw_dir, contract, caps("GOES19_RRQPEF"), w0, w1)
    summary = {}
    for prod in contract["products"]:
        sel = [r for r in rows if r["product"] == prod]
        summary[prod] = dict(intervals=len(sel), by_state={s: sum(1 for r in sel if r["state"] == s) for s in STATES})
    head = (_git(root, "rev-parse", "HEAD") or "").strip() or None
    return dict(schema_version="0.1", ledger_id="irfen-v09-capture-ledger:v0.1", **GUARDS, execution="MANUAL_ONLY",
                contains_precipitation_values=False, downloads_of_granules_or_scans=0,
                contract_sha256=sha256((root / "config/v09_capture_ledger_contract_v0_1.json").read_bytes()) if (root / "config/v09_capture_ledger_contract_v0_1.json").is_file() else None,
                built_from_commit=head if history and frozen_captures is None else None,
                capture_evidence_mode="FROZEN_FROM_LEDGER" if frozen_captures is not None else ("GIT_HISTORY" if history else "WORKING_TREE_ONLY"),
                window=manifest["window"], responses_manifest_sha256=sha256((responses_dir / "requests.json").read_bytes()),
                requests=[{k: r.get(k) for k in ("request_id", "product", "kind", "url", "requested_at_utc", "http_status", "ok", "error",
                                                 "sha256", "bytes", "page", "hour_utc")} for r in manifest["requests"]],
                states=contract["states"], summary=summary, intervals=rows)


def write_ledger(ledger: dict, out: Path) -> Path:
    out = guarded_output(out)
    data = dumps(ledger)
    if out.exists() and out.read_bytes() != data:
        raise FileExistsError(f"{out} exists with different content; ledgers are not overwritten")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        out.write_bytes(data)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "run"):
        s = sub.add_parser(name)
        s.add_argument("--from", dest="start", required=True)
        s.add_argument("--to", dest="end", required=True)
        s.add_argument("--out", required=True, type=Path)
    b = sub.add_parser("build")
    b.add_argument("--responses", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--no-history", action="store_true")
    args = ap.parse_args(argv)
    contract = load_contract()
    if args.cmd in ("fetch", "run"):
        manifest = fetch(utc(args.start), utc(args.end), args.out, contract)
        bad = [r for r in manifest["requests"] if not r["ok"]]
        print(f"requests={len(manifest['requests'])} not_ok={len(bad)} (recorded; affected intervals stay UNKNOWN)")
        if args.cmd == "fetch":
            return 0
        args.responses, args.no_history = args.out, False
        args.out = args.out / "ledger_v0_1.json"
    ledger = build(args.responses, contract, ROOT, history=not args.no_history)
    write_ledger(ledger, args.out)
    print(json.dumps(ledger["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
