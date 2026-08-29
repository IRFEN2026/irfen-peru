#!/usr/bin/env python3
"""Freeze exact Sentinel-1 GRD assets for an IBVF compatible pair by SHA-256.

RESEARCH_ONLY / TEST_ONLY. Earth Search STAC remains the identity catalog. This
script only verifies byte transport and hashes the exact assets already resolved
by the inventory; it does not infer activation, risk, or any operational label.
A transport failure is UNKNOWN/TRANSPORT_BLOCKED, never MISSING.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def stream_hash(uri: str, timeout: int = 300) -> dict[str, Any]:
    url = s3_to_https(uri)
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(30, timeout),
            headers={"User-Agent": "IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"},
        ) as r:
            r.raise_for_status()
            for chunk in r.iter_content(4 * 1024 * 1024):
                if not chunk:
                    continue
                h.update(chunk)
                n += len(chunk)
            return {
                "transport_status": "SUCCESS",
                "source_uri": uri,
                "resolved_url": url,
                "bytes": n,
                "sha256": h.hexdigest(),
                "http_status": r.status_code,
                "etag": r.headers.get("ETag"),
                "last_modified": r.headers.get("Last-Modified"),
            }
    except Exception as exc:
        return {
            "transport_status": "TRANSPORT_BLOCKED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            "source_uri": uri,
            "resolved_url": url,
            "bytes_received_before_failure": n,
            "error": repr(exc),
        }


def find_collection(inventory: dict[str, Any]) -> dict[str, Any]:
    coll = next((c for c in inventory.get("collections", []) if c.get("collection") == "sentinel-1-grd"), None)
    if not coll or coll.get("transport_status") != "SUCCESS":
        raise RuntimeError("Sentinel-1 Earth Search inventory is not transport-successful")
    return coll


def item_by_id(coll: dict[str, Any], item_id: str) -> dict[str, Any]:
    matches = [i for i in coll.get("items", []) if i.get("id") == item_id]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Sentinel-1 item {item_id}; got {len(matches)}")
    return matches[0]


def freeze_item(item: dict[str, Any], asset_keys: list[str]) -> dict[str, Any]:
    assets = item.get("assets") or {}
    frozen: dict[str, Any] = {}
    for key in asset_keys:
        href = (assets.get(key) or {}).get("href")
        if not href:
            frozen[key] = {"transport_status": "UNKNOWN_ASSET_REFERENCE_ABSENT", "scientific_data_status": "UNKNOWN_NOT_MISSING"}
            continue
        frozen[key] = stream_hash(href)
    return {
        "item_id": item.get("id"),
        "datetime": item.get("datetime"),
        "platform": item.get("platform"),
        "orbit_state": item.get("orbit_state"),
        "relative_orbit": item.get("relative_orbit"),
        "absolute_orbit": item.get("absolute_orbit"),
        "instrument_mode": item.get("instrument_mode"),
        "polarizations": item.get("polarizations"),
        "assets": frozen,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--pre-id", required=True)
    ap.add_argument("--post-id", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    coll = find_collection(inventory)
    pair = coll.get("pair_assessment") or {}
    candidates = pair.get("candidate_pairs") or []
    exact = [p for p in candidates if p.get("pre_id") == args.pre_id and p.get("post_id") == args.post_id]
    if len(exact) != 1 or exact[0].get("compatible") is not True:
        raise ValueError("Requested pair is not a compatible Earth Search pair in the supplied inventory")

    pre = item_by_id(coll, args.pre_id)
    post = item_by_id(coll, args.post_id)
    asset_keys = ["safe-manifest", "schema-calibration-vv", "schema-noise-vv", "schema-product-vv", "vv"]
    report = {
        "schema_version": "irfen-ibvf-sentinel1-freeze-v0.1",
        "generated_at": now(),
        "case_id": inventory.get("case_id"),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "identity_catalog": "EARTH_SEARCH_STAC",
        "source_inventory_manifest_sha256": inventory.get("manifest_sha256"),
        "compatible_pair": "YES",
        "pair_rule": exact[0],
        "asset_keys_frozen": asset_keys,
        "pre": freeze_item(pre, asset_keys),
        "post": freeze_item(post, asset_keys),
    }
    statuses = [x.get("transport_status") for side in (report["pre"], report["post"]) for x in side["assets"].values()]
    if statuses and all(s == "SUCCESS" for s in statuses):
        report["freeze_status"] = "ALL_REQUESTED_ASSETS_SHA256_FROZEN"
    elif any(s == "TRANSPORT_BLOCKED" for s in statuses):
        report["freeze_status"] = "PARTIAL_TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING"
    else:
        report["freeze_status"] = "INCOMPLETE_ASSET_REFERENCE_UNKNOWN_NOT_MISSING"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "freeze_status": report["freeze_status"],
        "pre_vv": report["pre"]["assets"]["vv"],
        "post_vv": report["post"]["assets"]["vv"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
