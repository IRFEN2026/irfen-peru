#!/usr/bin/env python3
"""Reproducible Earth Search STAC inventory for IRFEN independent basin validation.

RESEARCH_ONLY / TEST_ONLY. Preserves transport failures separately from
scientifically missing data. Does not assign operational EVENT/NONE labels,
risk classes, priorities, thresholds or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTIONS = ("sentinel-1-grd", "landsat-c2-l2", "cop-dem-glo-30")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_bbox(value: str) -> list[float]:
    bbox = [float(v.strip()) for v in value.split(",")]
    if len(bbox) != 4 or not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise argparse.ArgumentTypeError("bbox must be minLon,minLat,maxLon,maxLat")
    return bbox


def search_url(collection: str, bbox: list[float], start: str | None, end: str | None, limit: int) -> str:
    if collection not in COLLECTIONS:
        raise ValueError(collection)
    params: dict[str, str | int] = {
        "collections": collection,
        "bbox": ",".join(f"{v:.8f}".rstrip("0").rstrip(".") for v in bbox),
        "limit": limit,
    }
    if collection != "cop-dem-glo-30" and start and end:
        params["datetime"] = f"{start}/{end}"
    return f"{EARTH_SEARCH}/search?{urlencode(params)}"


def fetch_json(url: str, timeout: int = 45) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return {
                "transport_status": "SUCCESS",
                "http_status": getattr(response, "status", 200),
                "raw_sha256": sha256_bytes(raw),
                "payload": json.loads(raw),
            }
    except HTTPError as exc:
        return {"transport_status": "HTTP_ERROR", "http_status": exc.code, "error": str(exc)}
    except (URLError, socket.gaierror, TimeoutError, OSError) as exc:
        return {"transport_status": "TRANSPORT_BLOCKED", "http_status": None, "error": repr(exc)}


def assets(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"href": a.get("href"), "type": a.get("type"), "roles": a.get("roles"), "title": a.get("title")}
        for key, a in sorted(value.items())
    }


def summarize(item: dict[str, Any]) -> dict[str, Any]:
    p = item.get("properties") or {}
    collection = item.get("collection")
    out: dict[str, Any] = {
        "id": item.get("id"),
        "collection": collection,
        "datetime": p.get("datetime") or p.get("start_datetime"),
        "bbox": item.get("bbox"),
        "geometry": item.get("geometry"),
        "platform": p.get("platform"),
        "assets": assets(item.get("assets") or {}),
    }
    if collection == "sentinel-1-grd":
        out.update({
            "absolute_orbit": p.get("sat:absolute_orbit"),
            "relative_orbit": p.get("sat:relative_orbit"),
            "orbit_state": p.get("sat:orbit_state"),
            "instrument_mode": p.get("sar:instrument_mode"),
            "polarizations": p.get("sar:polarizations"),
            "product_type": p.get("sar:product_type"),
        })
    if collection == "landsat-c2-l2":
        asset_keys = set(item.get("assets") or {})
        out.update({
            "wrs_path": p.get("landsat:wrs_path"),
            "wrs_row": p.get("landsat:wrs_row"),
            "scene_id": p.get("landsat:scene_id"),
            "cloud_cover_global_pct": p.get("eo:cloud_cover"),
            "qa_assets_present": sorted(asset_keys.intersection({"qa_pixel", "qa_radsat", "qa_aerosol"})),
            "qa_asset_product_names": {"qa_pixel": "QA_PIXEL", "qa_radsat": "QA_RADSAT", "qa_aerosol": "SR_QA_AEROSOL"},
            "qa_acceptance_note": "Global cloud cover is metadata only; AOI-level QA is required before acceptance.",
        })
    return out


def parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def sentinel_pair(items: list[dict[str, Any]], event_date: str | None) -> dict[str, Any]:
    if not event_date:
        return {"compatible_pair": "UNKNOWN", "reason": "EVENT_DATE_NOT_SUPPLIED", "candidate_pairs": []}
    event = datetime.fromisoformat(event_date).replace(tzinfo=timezone.utc)
    before = [i for i in items if parse_dt(i.get("datetime")) and parse_dt(i.get("datetime")) < event]
    after = [i for i in items if parse_dt(i.get("datetime")) and parse_dt(i.get("datetime")) > event]
    pairs = []
    for pre in before:
        for post in after:
            checks = {
                "relative_orbit": pre.get("relative_orbit") is not None and pre.get("relative_orbit") == post.get("relative_orbit"),
                "orbit_state": pre.get("orbit_state") is not None and pre.get("orbit_state") == post.get("orbit_state"),
                "instrument_mode": pre.get("instrument_mode") is not None and pre.get("instrument_mode") == post.get("instrument_mode"),
                "polarizations": bool(pre.get("polarizations")) and set(pre.get("polarizations") or []) == set(post.get("polarizations") or []),
            }
            pairs.append({"pre_id": pre.get("id"), "post_id": post.get("id"), "checks": checks, "compatible": all(checks.values())})
    compatible = [p for p in pairs if p["compatible"]]
    if compatible:
        return {"compatible_pair": "YES", "reason": "MATCHING_ORBIT_MODE_POLARIZATION_PRE_POST_PAIR", "candidate_pairs": compatible}
    if pairs:
        return {"compatible_pair": "NO", "reason": "PRE_POST_ITEMS_EXIST_BUT_NO_COMPATIBLE_PAIR", "candidate_pairs": pairs}
    return {"compatible_pair": "UNKNOWN", "reason": "INSUFFICIENT_PRE_POST_ITEMS", "candidate_pairs": []}


def inventory(collection: str, bbox: list[float], start: str | None, end: str | None, event_date: str | None, limit: int, dry_run: bool) -> dict[str, Any]:
    url = search_url(collection, bbox, start, end, limit)
    base = {"collection": collection, "query_url": url, "query_bbox": bbox}
    if dry_run:
        return {**base, "transport_status": "NOT_EXECUTED_DRY_RUN", "scientific_data_status": "UNKNOWN"}
    fetched = fetch_json(url)
    result = {**base, **{k: v for k, v in fetched.items() if k != "payload"}}
    if fetched["transport_status"] != "SUCCESS":
        result["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
        return result
    items = [summarize(i) for i in ((fetched.get("payload") or {}).get("features") or [])]
    result["item_count"] = len(items)
    result["items"] = items
    result["scientific_data_status"] = "PRESENT" if items else "NO_ITEMS_RETURNED_AFTER_SUCCESSFUL_QUERY"
    if collection == "sentinel-1-grd":
        result["pair_assessment"] = sentinel_pair(items, event_date)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--bbox", required=True, type=parse_bbox)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--event-date")
    ap.add_argument("--collection", action="append", choices=COLLECTIONS)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    selected = args.collection or list(COLLECTIONS)
    if any(c != "cop-dem-glo-30" for c in selected) and (not args.start or not args.end):
        ap.error("--start and --end are required for Sentinel-1/Landsat")
    report = {
        "schema_version": "irfen-ibvf-stac-inventory-v0.1",
        "generated_at": utc_now(),
        "case_id": args.case_id,
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "source": EARTH_SEARCH,
        "collections": [inventory(c, args.bbox, args.start, args.end, args.event_date, args.limit, args.dry_run) for c in selected],
    }
    report["manifest_sha256"] = sha256_bytes(canonical_bytes(report))
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
