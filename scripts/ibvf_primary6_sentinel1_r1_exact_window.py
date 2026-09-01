#!/usr/bin/env python3
"""Execute one preassigned PRIMARY6 Sentinel-1 R1 window with one download.

RESEARCH_ONLY / TEST_ONLY. The scientific window and compatible pre/post pair
must already exist in the frozen PRIMARY6 execution partition and selected A1
catalog. This script cannot select a replacement window or pair. It downloads
each frozen-required Sentinel-1 asset once, hashes the exact bytes, preserves a
freeze manifest, and feeds those same cached bytes to the unchanged R1 native
radiometric processor.

No rainfall magnitude, SAR response, territorial outcome, known event date, or
case/control role is used to choose the window. No pre/post comparison, terrain
correction, common-support inference, activation inference, or modeling occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import ibvf_primary6_sentinel1_freeze_selected as frozen_util
import ibvf_sentinel1_r1_radiometric as r1

ALL_ASSET_KEYS = ["safe-manifest", "schema-calibration-vv", "schema-noise-vv", "schema-product-vv", "vv"]
USER_AGENT = "IRFEN-IBVF/0.5 RESEARCH_ONLY TEST_ONLY"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True


def download_once(uri: str, target: Path, timeout: int = 1200) -> dict[str, Any]:
    url = frozen_util.s3_to_https(uri)
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(url, stream=True, timeout=(30, timeout), headers={"User-Agent": USER_AGENT}) as resp:
            resp.raise_for_status()
            with target.open("wb") as fh:
                for chunk in resp.iter_content(4 * 1024 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
            return {
                "transport_status": "SUCCESS",
                "source_uri": uri,
                "resolved_url": url,
                "bytes": n,
                "sha256": h.hexdigest(),
                "http_status": resp.status_code,
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "download_count": 1,
                "cache_reused_for_r1": True,
            }
    except Exception as exc:
        return {
            "transport_status": "TRANSPORT_BLOCKED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            "source_uri": uri,
            "resolved_url": url,
            "bytes_received_before_failure": n,
            "error": repr(exc),
            "download_count": 1,
        }


def exact_window(partition: dict[str, Any], unit: str, date_local: str) -> tuple[dict[str, Any], dict[str, Any]]:
    hits: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for shard in partition.get("shards", []):
        if shard.get("unit_id") != unit:
            continue
        for w in shard.get("windows", []):
            if w.get("date_local") == date_local:
                hits.append((shard, w))
    if len(hits) != 1:
        raise ValueError(f"execution partition requires exactly one {unit}/{date_local} window; got {len(hits)}")
    return hits[0]


def exact_catalog_window(catalog: dict[str, Any], unit: str, date_local: str) -> dict[str, Any]:
    hits = [w for w in catalog.get("windows", []) if w.get("unit_id") == unit and w.get("date_local") == date_local]
    if len(hits) != 1:
        raise ValueError(f"selected A1 catalog requires exactly one {unit}/{date_local} window; got {len(hits)}")
    return hits[0]


def materialize_item(side: str, item: dict[str, Any], cache: Path) -> tuple[dict[str, Any], dict[str, Path]]:
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
    paths: dict[str, Path] = {}
    for key in ALL_ASSET_KEYS:
        href = (assets.get(key) or {}).get("href")
        if not href:
            rec["assets"][key] = {
                "transport_status": "UNKNOWN_ASSET_REFERENCE_ABSENT",
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
            }
            continue
        suffix = ".tif" if key == "vv" else (".safe" if key == "safe-manifest" else ".xml")
        path = cache / f"{side}-{key}{suffix}"
        result = download_once(href, path)
        rec["assets"][key] = result
        if result.get("transport_status") == "SUCCESS":
            paths[key] = path
    return rec, paths


def r1_side(side: str, frozen_side: dict[str, Any], paths: dict[str, Path], bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    for key in r1.ASSET_KEYS:
        if key not in paths:
            return {
                "side": side,
                "item_id": frozen_side.get("item_id"),
                "status": "TRANSPORT_BLOCKED",
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
                "missing_cached_asset": key,
            }
    diagnostics = r1.process_native(
        paths["vv"],
        paths["schema-calibration-vv"],
        paths["schema-noise-vv"],
        paths["schema-product-vv"],
        bbox,
    )
    verified = {}
    for key in r1.ASSET_KEYS:
        src = frozen_side["assets"][key]
        verified[key] = {
            "transport_status": src["transport_status"],
            "bytes": src["bytes"],
            "sha256": src["sha256"],
            "resolved_url": src["resolved_url"],
            "download_count": 1,
            "cache_reused_for_r1": True,
        }
    return {
        "side": side,
        "item_id": frozen_side.get("item_id"),
        "datetime": frozen_side.get("datetime"),
        "platform": frozen_side.get("platform"),
        "relative_orbit": frozen_side.get("relative_orbit"),
        "orbit_state": frozen_side.get("orbit_state"),
        "instrument_mode": frozen_side.get("instrument_mode"),
        "polarizations": frozen_side.get("polarizations"),
        "status": "R1_NATIVE_RADIOMETRIC_COMPLETE",
        "assets_verified": verified,
        "diagnostics": diagnostics,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--partition", required=True, type=Path)
    ap.add_argument("--a4-contract", required=True, type=Path)
    ap.add_argument("--unit", required=True, choices=["huaycoloro", "shingolay", "san_ildefonso"])
    ap.add_argument("--date-local", required=True)
    ap.add_argument("--basin", required=True, type=Path)
    ap.add_argument("--output-freeze", required=True, type=Path)
    ap.add_argument("--output-r1", required=True, type=Path)
    args = ap.parse_args()

    catalog_raw = args.catalog.read_bytes()
    partition_raw = args.partition.read_bytes()
    contract_raw = args.a4_contract.read_bytes()
    catalog = json.loads(catalog_raw)
    partition = json.loads(partition_raw)
    contract = json.loads(contract_raw)
    for obj in (catalog, partition, contract):
        guards(obj)
    assert catalog["case_control_assignment_performed"] is False
    assert catalog["territorial_outcome_fields_read"] is False
    assert partition["case_control_assignment_performed"] is False
    assert partition["territorial_outcomes_read"] is False
    assert partition["known_event_dates_read"] is False
    assert partition["selected_window_replacement_allowed"] is False
    assert partition["compatible_pair_reselection_allowed"] is False
    assert partition["missing_pair_imputation_allowed"] is False
    assert contract["compatible_pair_count"] == 104
    assert contract["replacement_of_selected_window_for_sar_availability"] is False

    shard, pw = exact_window(partition, args.unit, args.date_local)
    cw = exact_catalog_window(catalog, args.unit, args.date_local)
    assert pw.get("case_control_role") == "UNASSIGNED"
    if pw.get("sar_execution_status") != "COMPATIBLE_PAIR_FROZEN_PENDING_R1_R4":
        raise ValueError(f"requested exact window is not R1-executable: {pw.get('sar_execution_status')}")
    pair = (cw.get("sentinel1") or {}).get("selected_pair")
    if not isinstance(pair, dict):
        raise ValueError("selected A1 window lacks frozen Sentinel-1 selected_pair")
    pre_id, post_id = frozen_util.pair_ids(pair)
    assert pre_id == pw.get("pre_item_id")
    assert post_id == pw.get("post_item_id")

    pre_item = frozen_util.get_item(pre_id)
    post_item = frozen_util.get_item(post_id)
    identity = frozen_util.compatible_identity(pre_item, post_item)
    if identity.get("compatible") is not True:
        raise ValueError("preassigned compatible pair failed independent identity check")
    pident = pw.get("pair_identity")
    pp = pre_item.get("properties") or {}
    partition_pair_identity_metadata_present = isinstance(pident, dict) and bool(pident)
    if partition_pair_identity_metadata_present:
        assert pident.get("platform") == pp.get("platform")
        assert pident.get("instrument_mode") == pp.get("sar:instrument_mode")
        assert pident.get("orbit_state") == pp.get("sat:orbit_state")
        assert pident.get("relative_orbit") == pp.get("sat:relative_orbit")

    bbox = r1.basin_bbox(args.basin)
    case_id = f"primary6_{args.unit}_{args.date_local}"
    with tempfile.TemporaryDirectory(prefix=f"irfen-ibvf-s1-r1-{args.unit}-") as td:
        cache = Path(td)
        pre_freeze, pre_paths = materialize_item("pre", pre_item, cache)
        post_freeze, post_paths = materialize_item("post", post_item, cache)
        statuses = [x.get("transport_status") for side in (pre_freeze, post_freeze) for x in side["assets"].values()]
        freeze_status = "ALL_REQUESTED_ASSETS_SHA256_FROZEN" if statuses and all(x == "SUCCESS" for x in statuses) else "PARTIAL_TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING"
        freeze_report: dict[str, Any] = {
            "schema_version": "irfen-ibvf-primary6-sentinel1-exact-window-freeze-v0.1",
            "generated_at": now(),
            "case_id": case_id,
            "unit_id": args.unit,
            "season_id": shard.get("season_id"),
            "date_local": args.date_local,
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "uses_operational_event_none_labels": False,
            "territorial_activation_evidence_blinded": True,
            "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
            "execution_mode": "EXACT_PREASSIGNED_PRIMARY6_WINDOW_SINGLE_DOWNLOAD_SHA256_CACHE",
            "engineering_pilot_only": False,
            "source_catalog_sha256": sha256_bytes(catalog_raw),
            "source_partition_sha256": sha256_bytes(partition_raw),
            "source_partition_identity_sha256": partition.get("partition_identity_sha256"),
            "source_window_execution_identity_sha256": pw.get("window_execution_identity_sha256"),
            "source_a4_contract_sha256": sha256_bytes(contract_raw),
            "selected_target_order": cw.get("selected_target_order"),
            "pair_rule": pair,
            "independent_pair_identity_check": identity,
            "partition_pair_identity_metadata_present": partition_pair_identity_metadata_present,
            "pair_identity_validation_basis": "EXACT_PRE_POST_ITEM_IDS_PLUS_SELECTED_A1_PAIR_RULE_PLUS_INDEPENDENT_STAC_COMPATIBILITY; PARTITION_METADATA_CHECKED_IF_PRESENT",
            "asset_keys_frozen": ALL_ASSET_KEYS,
            "all_assets_downloaded_at_most_once": True,
            "cached_bytes_reused_for_r1": True,
            "selected_window_changed": False,
            "compatible_pair_changed": False,
            "replacement_window_allowed": False,
            "pair_reselection_allowed": False,
            "rainfall_values_read_for_execution_choice": False,
            "sar_change_values_read_for_execution_choice": False,
            "territorial_outcomes_read": False,
            "known_event_dates_read": False,
            "case_control_role_assigned": False,
            "activation_inference_allowed": False,
            "modeling_allowed": False,
            "pre": pre_freeze,
            "post": post_freeze,
            "freeze_status": freeze_status,
        }
        guards(freeze_report)
        args.output_freeze.parent.mkdir(parents=True, exist_ok=True)
        args.output_freeze.write_text(json.dumps(freeze_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if freeze_status != "ALL_REQUESTED_ASSETS_SHA256_FROZEN":
            raise RuntimeError(f"exact-window asset freeze incomplete: {freeze_status}")

        pre_r1 = r1_side("pre", pre_freeze, pre_paths, bbox)
        post_r1 = r1_side("post", post_freeze, post_paths, bbox)
        r1_report: dict[str, Any] = {
            "schema_version": "irfen-ibvf-sentinel1-a4-r1-v0.1",
            "generated_at": now(),
            "case_id": case_id,
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "uses_operational_event_none_labels": False,
            "territorial_activation_evidence_blinded": True,
            "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
            "stage": "A4_R1_NATIVE_RADIOMETRIC",
            "source_freeze_sha256": hashlib.sha256(args.output_freeze.read_bytes()).hexdigest(),
            "source_partition_identity_sha256": partition.get("partition_identity_sha256"),
            "source_window_execution_identity_sha256": pw.get("window_execution_identity_sha256"),
            "basin_geometry_sha256": hashlib.sha256(args.basin.read_bytes()).hexdigest(),
            "basin_bbox_lonlat": list(bbox),
            "radiometric_equation": "sigma0_linear=(DN^2-noise_range_lut)/(sigmaNought_calibration_lut^2)",
            "invalid_signal_rule": "DN^2-noise<=0 -> INVALID_NAN_NEVER_ZERO",
            "single_download_cache_mode": True,
            "comparison_performed": False,
            "terrain_correction_performed": False,
            "common_support_established": False,
            "interpretation_forbidden": True,
            "pre": pre_r1,
            "post": post_r1,
        }
        statuses_r1 = [pre_r1.get("status"), post_r1.get("status")]
        if statuses_r1 == ["R1_NATIVE_RADIOMETRIC_COMPLETE", "R1_NATIVE_RADIOMETRIC_COMPLETE"]:
            r1_report["r1_status"] = "COMPLETE_BOTH_DATES_NO_COMPARISON"
            r1_report["next_stage"] = "A4_R2_TERRAIN_GEOMETRIC_CORRECTION_COMMON_GRID_PREREGISTERED_BEFORE_DIFFERENCES"
        else:
            r1_report["r1_status"] = "INCOMPLETE_UNKNOWN_NOT_MISSING"
            r1_report["next_stage"] = "RETRY_IDENTICAL_EXACT_WINDOW_R1_WITHOUT_RESELECTION"
        r1_report["territorial_outcomes_read"] = False
        r1_report["known_event_dates_read"] = False
        r1_report["case_control_assignment_performed"] = False
        r1_report["activation_inference_allowed"] = False
        r1_report["modeling_allowed"] = False
        guards(r1_report)
        args.output_r1.parent.mkdir(parents=True, exist_ok=True)
        args.output_r1.write_text(json.dumps(r1_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if r1_report["r1_status"] != "COMPLETE_BOTH_DATES_NO_COMPARISON":
            raise RuntimeError(f"exact-window R1 incomplete: {r1_report['r1_status']}")

    print(json.dumps({
        "case_id": case_id,
        "season_id": shard.get("season_id"),
        "pre_item_id": pre_id,
        "post_item_id": post_id,
        "freeze_status": freeze_report["freeze_status"],
        "r1_status": r1_report["r1_status"],
        "single_download_cache_mode": True,
        "selected_window_changed": False,
        "compatible_pair_changed": False,
        "comparison_performed": False,
        "territorial_outcomes_read": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
