#!/usr/bin/env python3
"""Freeze one deterministic PRIMARY6 Sentinel-1 engineering-pilot pair.

RESEARCH_ONLY / TEST_ONLY. The scientific 108-window set and compatible pairs
are already frozen. This script does not reselect a scientific window. For an
explicit track it chooses the earliest chronologically compatible frozen pair
only as an engineering pilot, freezes its exact Earth Search assets by SHA-256,
and emits a manifest consumable by the already-demonstrated R1 processor.

No rain magnitudes, SAR change values, territorial outcomes, known event dates,
or case/control roles are read for pilot selection. Transport failure remains
UNKNOWN/TRANSPORT_BLOCKED, never MISSING.
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

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
USER_AGENT = "IRFEN-IBVF/0.4 RESEARCH_ONLY TEST_ONLY"
ASSET_KEYS = ["safe-manifest", "schema-calibration-vv", "schema-noise-vv", "schema-product-vv", "vv"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True


def pair_ids(pair: dict[str, Any]) -> tuple[str, str]:
    def one(prefix: str) -> str | None:
        for key in (f"{prefix}_id", f"{prefix}_item_id", f"{prefix}_scene_id"):
            v = pair.get(key)
            if isinstance(v, str) and v:
                return v
        v = pair.get(prefix)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            for key in ("id", "item_id", "scene_id"):
                x = v.get(key)
                if isinstance(x, str) and x:
                    return x
        for key in (f"{prefix}_item", f"{prefix}_scene"):
            v = pair.get(key)
            if isinstance(v, dict):
                x = v.get("id") or v.get("item_id")
                if isinstance(x, str) and x:
                    return x
        return None
    pre, post = one("pre"), one("post")
    if not pre or not post:
        raise ValueError(f"Cannot resolve pre/post IDs from selected_pair keys={sorted(pair.keys())}")
    return pre, post


def get_item(item_id: str) -> dict[str, Any]:
    u = f"{EARTH_SEARCH}/collections/sentinel-1-grd/items/{quote(item_id, safe='')}"
    r = requests.get(u, timeout=(20, 120), headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.json()


def stream_hash(uri: str, timeout: int = 1200) -> dict[str, Any]:
    url = s3_to_https(uri)
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(url, stream=True, timeout=(30, timeout), headers={"User-Agent": USER_AGENT}) as r:
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


def freeze_item(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or {}
    assets = item.get("assets") or {}
    rec: dict[str, Any] = {
        "item_id": item.get("id"),
        "datetime": props.get("datetime"),
        "platform": props.get("platform"),
        "orbit_state": props.get("sat:orbit_state"),
        "relative_orbit": props.get("sat:relative_orbit"),
        "absolute_orbit": props.get("sat:absolute_orbit"),
        "instrument_mode": props.get("sar:instrument_mode"),
        "polarizations": props.get("sar:polarizations"),
        "assets": {},
    }
    for key in ASSET_KEYS:
        href = (assets.get(key) or {}).get("href")
        if not href:
            rec["assets"][key] = {
                "transport_status": "UNKNOWN_ASSET_REFERENCE_ABSENT",
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
            }
        else:
            rec["assets"][key] = stream_hash(href)
    return rec


def compatible_identity(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    pp, qp = pre.get("properties") or {}, post.get("properties") or {}
    vals = {
        "same_platform": pp.get("platform") == qp.get("platform"),
        "same_mode": pp.get("sar:instrument_mode") == qp.get("sar:instrument_mode"),
        "same_orbit_state": pp.get("sat:orbit_state") == qp.get("sat:orbit_state"),
        "same_relative_orbit": pp.get("sat:relative_orbit") == qp.get("sat:relative_orbit"),
        "vv_pre": "VV" in (pp.get("sar:polarizations") or []),
        "vv_post": "VV" in (qp.get("sar:polarizations") or []),
    }
    vals["compatible"] = all(vals.values())
    return vals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--a4-contract", type=Path, required=True)
    ap.add_argument("--unit", required=True, choices=["huaycoloro", "shingolay", "san_ildefonso"])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    catalog_raw = args.catalog.read_bytes()
    catalog = json.loads(catalog_raw)
    contract = json.loads(args.a4_contract.read_text(encoding="utf-8"))
    guards(catalog)
    guards(contract)
    assert catalog["case_control_assignment_performed"] is False
    assert catalog["territorial_outcome_fields_read"] is False
    assert contract["compatible_pair_count"] == 104
    assert contract["replacement_of_selected_window_for_sar_availability"] is False

    eligible = []
    for w in catalog.get("windows", []):
        if w.get("unit_id") != args.unit:
            continue
        s1 = w.get("sentinel1") or {}
        pair = s1.get("selected_pair")
        if isinstance(pair, dict):
            try:
                pre_id, post_id = pair_ids(pair)
            except ValueError:
                continue
            eligible.append((str(w.get("date_local")), int(w.get("selected_target_order", 9999)), pre_id, post_id, w, pair))
    if not eligible:
        raise ValueError(f"No compatible frozen selected_pair found for {args.unit}")
    eligible.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    date_local, target_order, pre_id, post_id, window, pair = eligible[0]

    pre_item = get_item(pre_id)
    post_item = get_item(post_id)
    identity = compatible_identity(pre_item, post_item)
    if identity["compatible"] is not True:
        raise ValueError("Frozen selected pair failed independent identity compatibility check")

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-engineering-pilot-freeze-v0.1",
        "generated_at": now(),
        "case_id": f"primary6_{args.unit}_{date_local}",
        "unit_id": args.unit,
        "date_local": date_local,
        "selected_target_order": target_order,
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "engineering_pilot_only": True,
        "engineering_pilot_selection_rule": "EARLIEST_CHRONOLOGICAL_ALREADY_FROZEN_COMPATIBLE_PAIR_WITHIN_EXPLICIT_TRACK",
        "engineering_pilot_selection_changes_scientific_window_set": False,
        "all_104_compatible_pairs_remain_required": True,
        "source_catalog_sha256": sha256_bytes(catalog_raw),
        "source_selected_window_identity_sha256": catalog.get("selected_window_identity_sha256"),
        "compatible_pair": "YES",
        "pair_rule": pair,
        "independent_pair_identity_check": identity,
        "asset_keys_frozen": ASSET_KEYS,
        "rainfall_values_read_for_pilot_selection": False,
        "sar_change_values_read_for_pilot_selection": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "pre": freeze_item(pre_item),
        "post": freeze_item(post_item),
    }
    statuses = [x.get("transport_status") for side in (report["pre"], report["post"]) for x in side["assets"].values()]
    if statuses and all(x == "SUCCESS" for x in statuses):
        report["freeze_status"] = "ALL_REQUESTED_ASSETS_SHA256_FROZEN"
    elif any(x == "TRANSPORT_BLOCKED" for x in statuses):
        report["freeze_status"] = "PARTIAL_TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING"
    else:
        report["freeze_status"] = "INCOMPLETE_ASSET_REFERENCE_UNKNOWN_NOT_MISSING"
    report["modeling_allowed"] = False
    guards(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "case_id": report["case_id"],
        "pre_id": pre_id,
        "post_id": post_id,
        "identity": identity,
        "freeze_status": report["freeze_status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
