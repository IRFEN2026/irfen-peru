#!/usr/bin/env python3
"""CMR inventory for GPM IMERG Final V07 half-hourly granules.

RESEARCH_ONLY / TEST_ONLY. Verifies temporal slot existence independently from
raw-byte transport. Missing authentication or transport is never interpreted as
missing scientific data. Raw HDF5 acquisition can be enabled with an
EARTHDATA_TOKEN environment variable; without it, the report explicitly records
AUTH_NOT_CONFIGURED rather than MISSING.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
COLLECTION_CONCEPT_ID = "C2723754847-GES_DISC"
SHORT_NAME = "GPM_3IMERGHH"
VERSION = "07"
SLOT_RE = re.compile(r"3IMERG\.(\d{8})-S(\d{6})-E(\d{6})\.(\d{4})\.V07B\.HDF5$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def days_inclusive(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def expected_slot_codes() -> list[str]:
    out=[]
    for minute in range(0, 24 * 60, 30):
        hh, mm = divmod(minute, 60)
        out.append(f"{hh:02d}{mm:02d}00")
    return out


def fetch_cmr(start: date, end: date) -> tuple[dict[str, Any], bytes, str]:
    start_iso=f"{start.isoformat()}T00:00:00Z"
    end_exclusive=end + timedelta(days=1)
    end_iso=f"{end_exclusive.isoformat()}T00:00:00Z"
    params={
        "collection_concept_id": COLLECTION_CONCEPT_ID,
        "temporal": f"{start_iso},{end_iso}",
        "page_size": 500,
        "sort_key[]": "start_date",
    }
    r=requests.get(CMR,params=params,timeout=90,headers={"User-Agent":"IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"})
    r.raise_for_status()
    raw=r.content
    return r.json(), raw, r.url


def data_links(entry: dict[str, Any]) -> list[str]:
    links=[]
    for link in entry.get("links") or []:
        href=link.get("href")
        if not href: continue
        title=str(link.get("title") or "").lower()
        rel=str(link.get("rel") or "").lower()
        if href.lower().endswith((".hdf5", ".h5")) or "download" in title or "data#" in rel:
            links.append(href)
    return sorted(set(links))


def acquire_one(url: str, out: Path, token: str | None) -> dict[str, Any]:
    if not token:
        return {"status":"AUTH_NOT_CONFIGURED","scientific_data_status":"UNKNOWN_NOT_MISSING","url":url}
    headers={"Authorization":f"Bearer {token}","User-Agent":"IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"}
    try:
        with requests.get(url,stream=True,timeout=180,headers=headers,allow_redirects=True) as r:
            if r.status_code in (401,403):
                return {"status":"AUTH_BLOCKED","http_status":r.status_code,"scientific_data_status":"UNKNOWN_NOT_MISSING","url":url}
            r.raise_for_status()
            ctype=str(r.headers.get("content-type") or "").lower()
            if "text/html" in ctype:
                return {"status":"AUTH_REDIRECT_HTML","http_status":r.status_code,"scientific_data_status":"UNKNOWN_NOT_MISSING","url":url}
            out.parent.mkdir(parents=True,exist_ok=True)
            with out.open("wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk: f.write(chunk)
        return {"status":"SUCCESS","bytes":out.stat().st_size,"sha256":sha256_file(out),"url":url}
    except Exception as exc:
        if out.exists(): out.unlink()
        return {"status":"TRANSPORT_BLOCKED","error":repr(exc),"scientific_data_status":"UNKNOWN_NOT_MISSING","url":url}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True,type=date.fromisoformat)
    ap.add_argument("--end",required=True,type=date.fromisoformat)
    ap.add_argument("--event-date",required=True,type=date.fromisoformat)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--raw-metadata-output",type=Path)
    ap.add_argument("--download-dir",type=Path)
    ap.add_argument("--download-all",action="store_true")
    args=ap.parse_args()
    if args.end < args.start or not (args.start <= args.event_date <= args.end):
        ap.error("invalid date range/event date")

    payload, raw, resolved_url=fetch_cmr(args.start,args.end)
    entries=(payload.get("feed") or {}).get("entry") or []
    rows=[]
    malformed=[]
    for e in entries:
        gid=e.get("producer_granule_id") or e.get("title")
        m=SLOT_RE.search(str(gid or ""))
        if not m:
            malformed.append(gid); continue
        daycode,startcode,endcode,minute_index=m.groups()
        rows.append({
            "producer_granule_id":gid,
            "date":f"{daycode[:4]}-{daycode[4:6]}-{daycode[6:]}",
            "start_hhmmss":startcode,
            "end_hhmmss":endcode,
            "minute_index":minute_index,
            "time_start":e.get("time_start"),
            "time_end":e.get("time_end"),
            "data_links":data_links(e),
        })

    expected_days=days_inclusive(args.start,args.end)
    expected_codes=set(expected_slot_codes())
    by_day={d.isoformat():[] for d in expected_days}
    for r in rows:
        by_day.setdefault(r["date"],[]).append(r)
    day_checks={}
    for d in expected_days:
        key=d.isoformat(); got=by_day.get(key,[]); codes={r["start_hhmmss"] for r in got}
        day_checks[key]={
            "count":len(got),
            "unique_start_slots":len(codes),
            "missing_start_slots":sorted(expected_codes-codes),
            "duplicate_start_slots":sorted(k for k,v in Counter(r["start_hhmmss"] for r in got).items() if v>1),
            "complete_48":len(got)==48 and codes==expected_codes,
        }

    expected_total=len(expected_days)*48
    temporal_complete=len(rows)==expected_total and all(x["complete_48"] for x in day_checks.values()) and not malformed
    event_check=day_checks[args.event_date.isoformat()]

    token=os.environ.get("EARTHDATA_TOKEN")
    acquisition=[]
    if args.download_all:
        if not args.download_dir: ap.error("--download-dir required with --download-all")
        for r in rows:
            links=r["data_links"]
            if not links:
                acquisition.append({"producer_granule_id":r["producer_granule_id"],"status":"NO_DATA_LINK_IN_CMR_METADATA","scientific_data_status":"PRESENT_METADATA_RAW_LINK_UNRESOLVED"})
                continue
            dest=args.download_dir / Path(links[0].split("?",1)[0]).name
            acq=acquire_one(links[0],dest,token)
            acquisition.append({"producer_granule_id":r["producer_granule_id"],**acq})
            if acq["status"] != "SUCCESS" and not token:
                # Avoid repeating 432 known-auth-blocked requests.
                break

    report={
        "schema_version":"irfen-ibvf-imerg-inventory-v0.1",
        "generated_at":now(),
        "case_id":"cashahuacra_2015-03-23",
        "deployment_status":"RESEARCH_ONLY",
        "test_only":True,
        "production_use":False,
        "production_ready":False,
        "operational_alerting_enabled":False,
        "uses_operational_event_none_labels":False,
        "territorial_activation_evidence_blinded":True,
        "source":{"cmr":CMR,"resolved_query_url":resolved_url,"collection_concept_id":COLLECTION_CONCEPT_ID,"short_name":SHORT_NAME,"version":VERSION,"cmr_response_sha256":sha256_bytes(raw)},
        "window":{"start":args.start.isoformat(),"end_inclusive":args.end.isoformat(),"event_date":args.event_date.isoformat()},
        "expected_total_slots":expected_total,
        "resolved_granule_count":len(rows),
        "malformed_granule_ids":malformed,
        "day_checks":day_checks,
        "event_day_48_slots_verified":bool(event_check["complete_48"]),
        "window_all_slots_verified":temporal_complete,
        "metadata_scientific_data_status":"PRESENT" if rows else "NO_GRANULES_AFTER_SUCCESSFUL_CMR_QUERY",
        "raw_byte_acquisition":acquisition,
        "raw_byte_acquisition_status":"NOT_REQUESTED" if not args.download_all else ("COMPLETE" if len(acquisition)==len(rows) and all(x.get("status")=="SUCCESS" for x in acquisition) else "BLOCKED_OR_INCOMPLETE_NOT_MISSING"),
        "granules":rows,
        "serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
    }
    if args.raw_metadata_output:
        args.raw_metadata_output.parent.mkdir(parents=True,exist_ok=True); args.raw_metadata_output.write_bytes(raw)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"resolved":len(rows),"expected":expected_total,"event48":report["event_day_48_slots_verified"],"window_complete":temporal_complete,"raw_bytes":report["raw_byte_acquisition_status"]},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
