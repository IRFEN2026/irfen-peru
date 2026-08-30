#!/usr/bin/env python3
"""Compute preregistered Cashahuacra Sentinel-1 R4 blind change metrics.

RESEARCH_ONLY / TEST_ONLY. Reads only the frozen, lossless R3 pre/post Gamma0
crops and the frozen R3 common-support mask after verifying their SHA-256
identities. Computes exactly the R4 metrics preregistered before any radiometric
difference was inspected. It never reads territorial outcomes, assigns a
case/control role, or emits an activation/risk/alert classification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def raster_identity(a: rasterio.DatasetReader, b: rasterio.DatasetReader) -> bool:
    return (
        a.crs == b.crs
        and a.width == b.width
        and a.height == b.height
        and tuple(a.transform) == tuple(b.transform)
    )


def largest_cluster(mask: np.ndarray) -> tuple[int, int]:
    """Return largest 8-connected true component size and component count."""
    if mask.ndim != 2:
        raise ValueError("cluster mask must be 2-D")
    h, w = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    largest = 0
    n_components = 0
    offsets = ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1))
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        n_components += 1
        seen[y0, x0] = True
        q: deque[tuple[int,int]] = deque([(y0, x0)])
        size = 0
        while q:
            y, x = q.pop()
            size += 1
            for dy, dx in offsets:
                yy, xx = y + dy, x + dx
                if yy < 0 or yy >= h or xx < 0 or xx >= w:
                    continue
                if mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    q.append((yy, xx))
        largest = max(largest, size)
    return largest, n_components


def write_delta(src: rasterio.DatasetReader, delta: np.ndarray, common: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.full(delta.shape, np.nan, dtype="float32")
    out[common] = delta[common].astype("float32")
    profile = src.profile.copy()
    profile.update(driver="GTiff", dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(out, 1)
            dst.write_mask((common.astype("uint8") * 255))


def write_factor2(src: rasterio.DatasetReader, changed: np.ndarray, common: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.full(changed.shape, 255, dtype="uint8")
    out[common] = changed[common].astype("uint8")
    profile = src.profile.copy()
    profile.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(out, 1)
            dst.write_mask((common.astype("uint8") * 255))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--r3-report", type=Path, required=True)
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--common-mask", type=Path, required=True)
    ap.add_argument("--delta-output", type=Path, required=True)
    ap.add_argument("--factor2-mask-output", type=Path, required=True)
    ap.add_argument("--report-output", type=Path, required=True)
    args = ap.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    r3 = json.loads(args.r3_report.read_text(encoding="utf-8"))
    assert_guards(contract)
    assert_guards(r3)

    if contract["execution_status"] != "PREREGISTERED_NOT_EXECUTED_NO_RADIOMETRIC_DIFFERENCE_READ":
        raise SystemExit("R4 contract is not in preregistered/unexecuted state")
    if r3["status"] != "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY":
        raise SystemExit("R4 blocked: R3 spatial support gate has not passed")
    if not r3["r3_common_support_built"] or not r3["common_support_gate_pass"]:
        raise SystemExit("R4 blocked: R3 common-support evidence incomplete")
    if float(r3["common_support_fraction"]) < 0.95:
        raise SystemExit("R4 blocked: common support below frozen 0.95 gate")
    assert r3["radiometric_difference_statistics_computed"] is False
    assert r3["comparison_performed"] is False
    assert r3["r4_difference_computed"] is False
    assert r3["case_control_role_assigned"] is False
    assert r3["activation_inference_allowed"] is False

    frozen = contract["frozen_inputs"]
    identities = {
        "r3_report_sha256": sha256_file(args.r3_report),
        "pre_lossless_crop_sha256": sha256_file(args.pre),
        "post_lossless_crop_sha256": sha256_file(args.post),
        "common_support_mask_sha256": sha256_file(args.common_mask),
    }
    for key, actual in identities.items():
        expected = frozen[key]
        if actual != expected:
            raise SystemExit(f"R4 blocked: frozen input hash mismatch {key}: {actual} != {expected}")

    with rasterio.open(args.pre) as pre_ds, rasterio.open(args.post) as post_ds, rasterio.open(args.common_mask) as mask_ds:
        if not raster_identity(pre_ds, post_ds) or not raster_identity(pre_ds, mask_ds):
            raise SystemExit("R4 blocked: R3 crops/mask do not share exact grid identity")
        if str(pre_ds.crs) != frozen["crs"]:
            raise SystemExit("R4 blocked: CRS differs from preregistered input")
        if abs(float(pre_ds.transform.a) - float(frozen["pixel_size_m"])) > 1e-9 or abs(float(pre_ds.transform.e) + float(frozen["pixel_size_m"])) > 1e-9:
            raise SystemExit("R4 blocked: pixel size differs from preregistered input")

        pre = pre_ds.read(1, masked=False).astype("float64")
        post = post_ds.read(1, masked=False).astype("float64")
        mask_raw = mask_ds.read(1, masked=False)
        common = mask_raw == 1
        common_count = int(common.sum())
        if common_count != int(frozen["common_support_pixel_count"]):
            raise SystemExit(f"R4 blocked: common support count changed {common_count}")
        if not np.all(np.isfinite(pre[common])) or not np.all(np.isfinite(post[common])):
            raise SystemExit("R4 blocked: non-finite Gamma0 inside frozen common support")
        if not np.all(pre[common] > 0) or not np.all(post[common] > 0):
            raise SystemExit("R4 blocked: non-positive Gamma0 inside frozen common support")

        delta = np.full(pre.shape, np.nan, dtype="float64")
        delta[common] = 10.0 * np.log10(post[common] / pre[common])
        values = delta[common]
        if values.size != common_count or not np.all(np.isfinite(values)):
            raise SystemExit("R4 blocked: invalid delta values on frozen support")

        qs = np.quantile(values, [0.05,0.10,0.25,0.50,0.75,0.90,0.95], method="linear")
        p05,p10,p25,p50,p75,p90,p95 = [float(x) for x in qs]
        threshold = float(contract["factor_two_threshold"]["absolute_db"])
        decreased = common & (delta <= -threshold)
        increased = common & (delta >= threshold)
        factor2 = common & (np.abs(delta) >= threshold)
        dec_count = int(decreased.sum())
        inc_count = int(increased.sum())
        factor_count = int(factor2.sum())
        largest, component_count = largest_cluster(factor2)

        metrics = {
            "MEDIAN_DELTA_DB": p50,
            "IQR_DELTA_DB": p75 - p25,
            "DECREASE_FACTOR2_FRACTION": dec_count / common_count,
            "INCREASE_FACTOR2_FRACTION": inc_count / common_count,
            "LARGEST_FACTOR2_CLUSTER_FRACTION": largest / common_count,
        }
        diagnostics = {
            "P05_DELTA_DB": p05,
            "P10_DELTA_DB": p10,
            "P25_DELTA_DB": p25,
            "P50_DELTA_DB": p50,
            "P75_DELTA_DB": p75,
            "P90_DELTA_DB": p90,
            "P95_DELTA_DB": p95,
            "ABS_FACTOR2_FRACTION": factor_count / common_count,
            "LARGEST_FACTOR2_CLUSTER_PIXEL_COUNT": largest,
            "NUMBER_OF_FACTOR2_CLUSTERS": component_count,
        }

        write_delta(pre_ds, delta, common, args.delta_output)
        write_factor2(pre_ds, factor2, common, args.factor2_mask_output)

    report = {
        "schema_version": "irfen-ibvf-cashahuacra-sentinel1-r4-v0.1",
        "generated_at": now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "contract_path": str(args.contract),
        "contract_sha256": sha256_file(args.contract),
        "input_identities": identities,
        "r3_status": r3["status"],
        "common_support_fraction": float(r3["common_support_fraction"]),
        "common_support_pixel_count": common_count,
        "delta_definition": contract["pixelwise_change_definition"]["formula"],
        "factor_two_threshold_db": threshold,
        "quantile_method": "numpy_quantile_linear",
        "primary_r4_feature_vector": metrics,
        "fixed_diagnostics": diagnostics,
        "delta_db_geotiff": {
            "path": str(args.delta_output),
            "bytes": args.delta_output.stat().st_size,
            "sha256": sha256_file(args.delta_output),
            "masked_outside_common_support": True,
        },
        "factor2_binary_mask": {
            "path": str(args.factor2_mask_output),
            "bytes": args.factor2_mask_output.stat().st_size,
            "sha256": sha256_file(args.factor2_mask_output),
            "masked_outside_common_support": True,
            "connectivity_for_cluster_metric": 8,
            "morphological_cleanup_performed": False,
        },
        "clipping_performed": False,
        "smoothing_performed": False,
        "additional_resampling_performed": False,
        "posthoc_terrain_or_landcover_masking_performed": False,
        "r4_difference_computed": True,
        "r4_is_observational_not_decisional": True,
        "r4_feature_magnitude_pass_fail_threshold": None,
        "case_control_role_assigned": False,
        "territorial_outcome_fields_read": False,
        "activation_inference_allowed": False,
        "risk_classification_computed": False,
        "alert_value_computed": False,
        "status": "PASS_R4_BLIND_SAR_FEATURE_VECTOR_FROZEN_NO_INFERENCE",
        "next_gate": "A5_FREEZE_CASHAHUACRA_BLIND_FEATURE_VECTOR_WITH_GEOMETRY_IMERG_LANDSAT_AND_R4_WITHOUT_TERRITORIAL_UNBLIND; SERIOUS_MODELING_REMAINS_BLOCKED_PENDING_PARALLEL_CONTROLS",
    }
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "common_support_pixel_count": common_count,
        "primary_r4_feature_vector": metrics,
        "activation_inference_allowed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
