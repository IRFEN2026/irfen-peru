#!/usr/bin/env python3
"""Hash-freeze IMERG Final V07 raw HDF5 bytes for Cashahuacra.

RESEARCH_ONLY / TEST_ONLY. Streams each CMR-resolved HDF5 through SHA-256 and
discards bytes immediately; raw files are never committed or retained. The
scientific presence contract comes from successful CMR inventory. Any auth or
transport failure is BLOCKED/UNKNOWN_NOT_MISSING, never scientific MISSING.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

import requests

import ibvf_imerg_inventory as inv
from ibvf_imerg_auth_probe import select_raw_hdf5_url


def stream_hash(url: str, token: str | None, attempts: int = 3) -> dict[str, Any]:
    if not token:
        return {
            "status": "AUTH_NOT_CONFIGURED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            "url": url,
        }
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "IRFEN-IBVF/0.3 RESEARCH_ONLY TEST_ONLY",
    }
    last: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            with requests.get(url, stream=True, timeout=(30, 180), headers=headers, allow_redirects=True) as r:
                if r.status_code in (401, 403):
                    return {
                        "status": "AUTH_BLOCKED",
                        "http_status": r.status_code,
                        "scientific_data_status": "UNKNOWN_NOT_MISSING",
                        "url": url,
                        "attempt": attempt,
                    }
                r.raise_for_status()
                ctype = str(r.headers.get("content-type") or "").lower()
                if "text/html" in ctype:
                    return {
                        "status": "AUTH_REDIRECT_HTML",
                        "http_status": r.status_code,
                        "scientific_data_status": "UNKNOWN_NOT_MISSING",
                        "url": url,
                        "attempt": attempt,
                    }
                h = hashlib.sha256()
                n = 0
                for chunk in r.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    h.update(chunk)
                    n += len(chunk)
                if n <= 0:
                    last = {
                        "status": "ZERO_BYTES_TRANSPORT_ANOMALY",
                        "scientific_data_status": "UNKNOWN_NOT_MISSING",
                        "url": url,
                        "attempt": attempt,
                    }
                else:
                    return {
                        "status": "SUCCESS",
                        "bytes": n,
                        "sha256": h.hexdigest(),
                        "url": url,
                        "attempt": attempt,
                        "content_type": ctype or None,
                    }
        except Exception as exc:
            last = {
                "status": "TRANSPORT_BLOCKED",
                "error": repr(exc),
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
                "url": url,
                "attempt": attempt,
            }
        if attempt < attempts:
            time.sleep(float(attempt))
    return last or {
        "status": "TRANSPORT_BLOCKED",
        "scientific_data_status": "UNKNOWN_NOT_MISSING",
        "url": url,
    }


def freeze_row(row: dict[str, Any], token: str | None) -> dict[str, Any]:
    gid = str(row.get("producer_granule_id") or "")
    links = row.get("data_links") or []
    url, selection = select_raw_hdf5_url(links)
    base = {
        "producer_granule_id": gid,
        "date": row.get("date"),
        "start_hhmmss": row.get("start_hhmmss"),
        "time_start": row.get("time_start"),
        "raw_link_selection": selection,
    }
    if not url:
        return {
            **base,
            "status": "NO_HDF5_OBJECT_URL_IN_CMR_METADATA",
            "scientific_data_status": "PRESENT_METADATA_RAW_LINK_UNRESOLVED",
        }
    if url.startswith("s3://"):
        return {
            **base,
            "url": url,
            "status": "S3_ONLY_CREDENTIAL_FLOW_NOT_IMPLEMENTED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
        }
    return {**base, **stream_hash(url, token)}


def manifest_sha256(rows: list[dict[str, Any]]) -> str | None:
    if not rows or not all(x.get("status") == "SUCCESS" for x in rows):
        return None
    canonical = "\n".join(
        f"{x['producer_granule_id']}|{x['bytes']}|{x['sha256']}"
        for x in sorted(rows, key=lambda r: r["producer_granule_id"])
    ) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--event-date", required=True, type=date.fromisoformat)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    source = json.loads(args.inventory.read_text(encoding="utf-8"))
    rows = list(source.get("granules") or [])
    token = os.environ.get("EARTHDATA_TOKEN")
    results: list[dict[str, Any]] = []

    if token and rows:
        workers = max(1, min(int(args.workers), 12))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(freeze_row, row, token): row for row in rows}
            for fut in as_completed(futs):
                try:
                    results.append(fut.result())
                except Exception as exc:
                    row = futs[fut]
                    results.append({
                        "producer_granule_id": row.get("producer_granule_id"),
                        "date": row.get("date"),
                        "start_hhmmss": row.get("start_hhmmss"),
                        "status": "WORKER_EXCEPTION",
                        "error": repr(exc),
                        "scientific_data_status": "UNKNOWN_NOT_MISSING",
                    })
    else:
        results = [freeze_row(row, token) for row in rows[:1]] if rows else []

    results.sort(key=lambda x: (str(x.get("date") or ""), str(x.get("start_hhmmss") or ""), str(x.get("producer_granule_id") or "")))
    success = [x for x in results if x.get("status") == "SUCCESS"]
    event = [x for x in results if x.get("date") == args.event_date.isoformat()]
    event_success = [x for x in event if x.get("status") == "SUCCESS"]
    failures = [x for x in results if x.get("status") != "SUCCESS"]

    expected_total = int(source.get("expected_total_slots") or len(rows))
    inventory_complete = bool(source.get("window_all_slots_verified")) and len(rows) == expected_total
    raw_complete = inventory_complete and len(results) == expected_total and len(success) == expected_total
    event_complete = len(event) == 48 and len(event_success) == 48

    report = {
        "schema_version": "irfen-ibvf-imerg-raw-hash-freeze-v0.1",
        "generated_at": inv.now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "product": {"short_name": inv.SHORT_NAME, "version": inv.VERSION},
        "source_inventory": str(args.inventory),
        "inventory_432_verified": inventory_complete,
        "event_date": args.event_date.isoformat(),
        "expected_window_granules": expected_total,
        "expected_event_granules": 48,
        "attempted_granules": len(results),
        "successful_hashes": len(success),
        "failed_or_blocked_hashes": len(failures),
        "event_successful_hashes": len(event_success),
        "event_48_raw_sha256_frozen": event_complete,
        "window_432_raw_sha256_frozen": raw_complete,
        "raw_byte_status": (
            "COMPLETE_432_SHA256_FROZEN"
            if raw_complete
            else "BLOCKED_OR_INCOMPLETE_NOT_MISSING"
        ),
        "scientific_data_status": (
            "PRESENT_RAW_BYTES_432_FROZEN"
            if raw_complete
            else "PRESENT_METADATA_RAW_BYTES_PARTIAL_OR_BLOCKED_NOT_MISSING"
        ),
        "ordered_raw_manifest_sha256": manifest_sha256(results),
        "event_ordered_raw_manifest_sha256": manifest_sha256(event),
        "total_bytes_hashed": int(sum(int(x.get("bytes") or 0) for x in success)),
        "failure_summary": {
            status: sum(1 for x in failures if x.get("status") == status)
            for status in sorted({str(x.get("status")) for x in failures})
        },
        "failures": failures,
        "granules": results,
        "raw_files_retained": False,
        "missing_data_rule": "AUTH_OR_TRANSPORT_FAILURE_IS_UNKNOWN_NOT_MISSING",
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "inventory_432": inventory_complete,
        "attempted": len(results),
        "success": len(success),
        "event48": event_complete,
        "window432": raw_complete,
        "bytes": report["total_bytes_hashed"],
        "manifest_sha256": report["ordered_raw_manifest_sha256"],
        "event_manifest_sha256": report["event_ordered_raw_manifest_sha256"],
        "failures": report["failure_summary"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
