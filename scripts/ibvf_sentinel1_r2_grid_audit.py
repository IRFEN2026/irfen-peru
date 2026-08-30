#!/usr/bin/env python3
"""Audit Cashahuacra R2 output grid geometry without reading SAR values.

This is a metadata-only diagnostic after the original R3 fail-closed grid
identity gate. It determines whether different full-scene extents nevertheless
sit on the exact same target pixel lattice. It does not read raster pixels,
compute support, or relax any gate by itself.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol


def integer_close(x: float, tol: float = 1e-9) -> bool:
    return abs(x - round(x)) <= tol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r2-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    r2 = json.loads(args.r2_report.read_text(encoding="utf-8"))
    assert r2["deployment_status"] == "RESEARCH_ONLY"
    assert r2["production_use"] is False and r2["production_ready"] is False and r2["operational_alerting_enabled"] is False
    assert r2["uses_operational_event_none_labels"] is False and r2["territorial_activation_evidence_blinded"] is True
    assert r2["r2_processing_executed"] is True and r2["poeorb_consumption_verified_both_dates"] is True
    assert r2["comparison_performed"] is False and r2["r4_difference_computed"] is False

    pre = r2["r2"]["pre"]["output"]["metadata_only"]
    post = r2["r2"]["post"]["output"]["metadata_only"]
    pt = [float(x) for x in pre["transform"]]
    qt = [float(x) for x in post["transform"]]
    # Affine sequence: a,b,c,d,e,f,(0,0,1 if present)
    same_crs = pre["crs"] == post["crs"]
    same_pixel_vectors = all(close(pt[i], qt[i]) for i in (0, 1, 3, 4))
    no_rotation = close(pt[1], 0.0) and close(pt[3], 0.0) and close(qt[1], 0.0) and close(qt[3], 0.0)
    px = abs(pt[0]); py = abs(pt[4])
    col_phase = (qt[2] - pt[2]) / px if px else math.nan
    row_phase = (qt[5] - pt[5]) / py if py else math.nan
    lattice_phase_integer = integer_close(col_phase) and integer_close(row_phase)
    same_full_transform = all(close(a, b) for a, b in zip(pt[:6], qt[:6]))
    same_shape = pre["width"] == post["width"] and pre["height"] == post["height"]
    pb = [float(x) for x in pre["bounds"]]
    qb = [float(x) for x in post["bounds"]]
    overlap = [max(pb[0], qb[0]), max(pb[1], qb[1]), min(pb[2], qb[2]), min(pb[3], qb[3])]
    overlap_nonempty = overlap[0] < overlap[2] and overlap[1] < overlap[3]
    same_lattice = same_crs and same_pixel_vectors and no_rotation and lattice_phase_integer and overlap_nonempty

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-cashahuacra-r2-grid-audit-v0.1",
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
        "diagnostic_scope": "GRID_METADATA_ONLY_NO_SAR_PIXEL_VALUES_READ",
        "r2_graph_sha256": r2["graph_sha256"],
        "pre": pre,
        "post": post,
        "same_crs": same_crs,
        "same_pixel_vectors": same_pixel_vectors,
        "no_rotation": no_rotation,
        "same_full_affine_transform": same_full_transform,
        "same_full_shape": same_shape,
        "pre_to_post_column_phase_pixels": col_phase,
        "pre_to_post_row_phase_pixels": row_phase,
        "integer_pixel_lattice_phase": lattice_phase_integer,
        "spatial_overlap_bounds": overlap,
        "spatial_overlap_nonempty": overlap_nonempty,
        "same_target_pixel_lattice": same_lattice,
        "r3_original_grid_identity_gate_pass": same_full_transform and same_shape,
        "r3_common_support_computed": False,
        "r4_difference_computed": False,
        "activation_inference_allowed": False,
        "status": "PASS_COMMON_TARGET_PIXEL_LATTICE_DIFFERENT_FULL_EXTENTS_METADATA_ONLY" if same_lattice and not (same_full_transform and same_shape) else ("PASS_EXACT_FULL_GRID_IDENTITY_METADATA_ONLY" if same_lattice else "FAIL_TARGET_PIXEL_LATTICE_MISMATCH_R3_REMAINS_BLOCKED"),
        "scientific_note": "This diagnostic does not itself authorize R3. Any protocol amendment must be explicit, versioned, signal-blind, and preserve zero-resampling exact target-pixel intersection semantics."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["status", "same_crs", "same_pixel_vectors", "pre_to_post_column_phase_pixels", "pre_to_post_row_phase_pixels", "same_target_pixel_lattice"]}, indent=2))
    return 0 if same_lattice else 2


if __name__ == "__main__":
    raise SystemExit(main())
