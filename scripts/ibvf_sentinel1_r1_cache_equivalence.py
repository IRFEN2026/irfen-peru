#!/usr/bin/env python3
"""Verify a single-download cache path is scientifically equivalent to frozen R1.

RESEARCH_ONLY / TEST_ONLY. This audit does not change selected windows, pair
identity, radiometric equations, basin geometry, or any scientific threshold.
It reuses the exact SHA-256-frozen Sentinel-1 assets from an already frozen
engineering pilot, downloads each R1-required asset exactly once, and invokes
the unchanged R1 native-radiometric computation on the cached bytes.

The audit compares only science diagnostics/identity against the previously
frozen R1 result. It performs no pre/post comparison, terrain correction,
common-support inference, activation inference, case/control assignment, or
territorial-outcome read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ibvf_sentinel1_r1_radiometric as r1


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True


def materialize_side(side: str, frozen: dict[str, Any], bbox: tuple[float, float, float, float], cache: Path) -> dict[str, Any]:
    paths: dict[str, Path] = {}
    verified: dict[str, Any] = {}
    for key in r1.ASSET_KEYS:
        expected = (frozen.get("assets") or {}).get(key) or {}
        uri = expected.get("source_uri") or expected.get("resolved_url")
        sha = expected.get("sha256")
        nbytes = expected.get("bytes")
        if not uri or not sha:
            raise ValueError(f"{side}:{key} lacks frozen URI/SHA256")
        suffix = ".tif" if key == "vv" else ".xml"
        target = cache / f"{side}-{key}{suffix}"
        result = r1.download_verified(uri, sha, nbytes, target)
        if result.get("transport_status") != "SUCCESS":
            raise RuntimeError(f"single-download materialization failed for {side}:{key}: {result}")
        result["verification_mode"] = "SINGLE_DOWNLOAD_SHA256_CACHE"
        result["download_count_for_audit"] = 1
        verified[key] = result
        paths[key] = target

    diagnostics = r1.process_native(
        paths["vv"],
        paths["schema-calibration-vv"],
        paths["schema-noise-vv"],
        paths["schema-product-vv"],
        bbox,
    )
    return {
        "side": side,
        "item_id": frozen.get("item_id"),
        "datetime": frozen.get("datetime"),
        "platform": frozen.get("platform"),
        "relative_orbit": frozen.get("relative_orbit"),
        "orbit_state": frozen.get("orbit_state"),
        "instrument_mode": frozen.get("instrument_mode"),
        "polarizations": frozen.get("polarizations"),
        "status": "R1_NATIVE_RADIOMETRIC_COMPLETE",
        "assets_verified": verified,
        "diagnostics": diagnostics,
    }


def scientific_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": report.get("case_id"),
        "basin_bbox_lonlat": report.get("basin_bbox_lonlat"),
        "radiometric_equation": report.get("radiometric_equation"),
        "invalid_signal_rule": report.get("invalid_signal_rule"),
        "pre": {
            "item_id": (report.get("pre") or {}).get("item_id"),
            "datetime": (report.get("pre") or {}).get("datetime"),
            "platform": (report.get("pre") or {}).get("platform"),
            "relative_orbit": (report.get("pre") or {}).get("relative_orbit"),
            "orbit_state": (report.get("pre") or {}).get("orbit_state"),
            "instrument_mode": (report.get("pre") or {}).get("instrument_mode"),
            "polarizations": (report.get("pre") or {}).get("polarizations"),
            "status": (report.get("pre") or {}).get("status"),
            "diagnostics": (report.get("pre") or {}).get("diagnostics"),
        },
        "post": {
            "item_id": (report.get("post") or {}).get("item_id"),
            "datetime": (report.get("post") or {}).get("datetime"),
            "platform": (report.get("post") or {}).get("platform"),
            "relative_orbit": (report.get("post") or {}).get("relative_orbit"),
            "orbit_state": (report.get("post") or {}).get("orbit_state"),
            "instrument_mode": (report.get("post") or {}).get("instrument_mode"),
            "polarizations": (report.get("post") or {}).get("polarizations"),
            "status": (report.get("post") or {}).get("status"),
            "diagnostics": (report.get("post") or {}).get("diagnostics"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", required=True, type=Path)
    ap.add_argument("--basin", required=True, type=Path)
    ap.add_argument("--reference-r1", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--cache-dir", type=Path)
    args = ap.parse_args()

    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    reference = json.loads(args.reference_r1.read_text(encoding="utf-8"))
    guards(freeze)
    guards(reference)
    assert freeze["freeze_status"] == "ALL_REQUESTED_ASSETS_SHA256_FROZEN"
    assert reference["r1_status"] == "COMPLETE_BOTH_DATES_NO_COMPARISON"
    assert reference["comparison_performed"] is False
    assert reference["terrain_correction_performed"] is False
    assert reference["common_support_established"] is False
    assert reference["interpretation_forbidden"] is True

    bbox = r1.basin_bbox(args.basin)
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_ctx = None
        cache = args.cache_dir
    else:
        cache_ctx = tempfile.TemporaryDirectory(prefix="irfen-ibvf-s1-cache-equivalence-")
        cache = Path(cache_ctx.name)

    try:
        candidate: dict[str, Any] = {
            "case_id": freeze.get("case_id"),
            "basin_bbox_lonlat": list(bbox),
            "radiometric_equation": "sigma0_linear=(DN^2-noise_range_lut)/(sigmaNought_calibration_lut^2)",
            "invalid_signal_rule": "DN^2-noise<=0 -> INVALID_NAN_NEVER_ZERO",
        }
        candidate["pre"] = materialize_side("pre", freeze["pre"], bbox, cache)
        candidate["post"] = materialize_side("post", freeze["post"], bbox, cache)
    finally:
        if cache_ctx is not None:
            cache_ctx.cleanup()

    ref_view = scientific_view(reference)
    new_view = scientific_view(candidate)
    ref_sha = canonical_sha(ref_view)
    new_sha = canonical_sha(new_view)
    equivalent = ref_view == new_view and ref_sha == new_sha
    if not equivalent:
        raise AssertionError(f"cached R1 science diagnostics differ: reference={ref_sha} candidate={new_sha}")

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-sentinel1-r1-cache-equivalence-v0.1",
        "generated_at": now(),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "case_id": freeze.get("case_id"),
        "audit_purpose": "PROVE_SINGLE_DOWNLOAD_SHA256_CACHE_REPRODUCES_FROZEN_R1_SCIENCE_DIAGNOSTICS",
        "source_freeze_sha256": hashlib.sha256(args.freeze.read_bytes()).hexdigest(),
        "source_reference_r1_sha256": hashlib.sha256(args.reference_r1.read_bytes()).hexdigest(),
        "source_basin_geometry_sha256": hashlib.sha256(args.basin.read_bytes()).hexdigest(),
        "unchanged_science_processor": "scripts/ibvf_sentinel1_r1_radiometric.py::process_native",
        "assets_downloaded_once_per_side_and_key": True,
        "stac_reselection_performed": False,
        "selected_window_changed": False,
        "compatible_pair_changed": False,
        "radiometric_equation_changed": False,
        "geometry_changed": False,
        "comparison_performed": False,
        "terrain_correction_performed": False,
        "common_support_established": False,
        "rainfall_values_read": False,
        "sar_change_values_used_for_selection": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_assignment_performed": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "reference_scientific_view_sha256": ref_sha,
        "cached_scientific_view_sha256": new_sha,
        "scientific_views_exactly_equal": True,
        "equivalence_status": "PASS_SINGLE_DOWNLOAD_CACHE_SCIENTIFICALLY_IDENTICAL_R1",
        "pre_assets": candidate["pre"]["assets_verified"],
        "post_assets": candidate["post"]["assets_verified"],
    }
    guards(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "equivalence_status": report["equivalence_status"],
        "case_id": report["case_id"],
        "scientific_view_sha256": new_sha,
        "assets_downloaded_once_per_side_and_key": True,
        "comparison_performed": False,
        "territorial_outcomes_read": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
