#!/usr/bin/env python3
"""Signal-blind geometry footprint audit for PRIMARY6 R3 blockers.

RESEARCH_ONLY / TEST_ONLY diagnostic. This script reads only frozen GeoJSON and
metadata already recorded in R2/R3 JSON reports. It never opens raster files,
never reads SAR pixel values, and never reads territorial activation outcomes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform as shapely_transform, unary_union

BLOCKED_STATUS = "R3_BLOCKED_FROZEN_BASIN_WINDOW_NOT_CONTAINED_IN_BOTH_R2_PRODUCTS"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def select_geometry(path: Path, selector: dict[str, Any] | None):
    doc = load(path)
    if doc.get("type") == "Feature":
        features = [doc]
    elif doc.get("type") == "FeatureCollection":
        features = doc.get("features") or []
    else:
        raise ValueError("basin file must be GeoJSON Feature or FeatureCollection")
    if selector is not None:
        prop, value = selector["property"], selector["value"]
        features = [f for f in features if (f.get("properties") or {}).get(prop) == value]
    geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:
        raise ValueError("frozen basin selector returned no geometry")
    merged = unary_union(geoms)
    if not merged.is_valid:
        merged = merged.buffer(0)
    if merged.is_empty or not merged.is_valid:
        raise ValueError("frozen basin geometry invalid after deterministic repair")
    return merged


def find_r3(case_dir: Path) -> Path | None:
    candidates = [case_dir / "r3" / "r3-v02.json", case_dir / "r3-v02.json"]
    return next((p for p in candidates if p.is_file()), None)


def pct(x: float) -> float:
    return round(100.0 * x, 8)


def audit_case(case_dir: Path, contract: dict[str, Any], repo_root: Path) -> dict[str, Any] | None:
    r3_path = find_r3(case_dir)
    r2_path = case_dir / "r2-v02.json"
    if r3_path is None or not r2_path.is_file():
        return None
    r3 = load(r3_path)
    if r3.get("status") != BLOCKED_STATUS:
        return None
    r2 = load(r2_path)
    unit_id = r2["unit_id"]
    if r3.get("case_id") != r2.get("case_id") or r3.get("unit_id") != unit_id:
        raise ValueError(f"R2/R3 identity mismatch in {case_dir}")
    for d in (r2, r3):
        if d.get("deployment_status") != "RESEARCH_ONLY" or d.get("test_only") is not True:
            raise ValueError("research/test guard mismatch")
        if d.get("production_use") is not False or d.get("production_ready") is not False:
            raise ValueError("production guard mismatch")
        if d.get("operational_alerting_enabled") is not False:
            raise ValueError("operational alerting guard mismatch")
        if d.get("territorial_activation_evidence_blinded") is not True:
            raise ValueError("territorial activation evidence is not blinded")
        if d.get("territorial_outcomes_read") is not False:
            raise ValueError("territorial outcomes were read")

    unit = contract["unit_geometry_and_projection"][unit_id]
    geometry_path = repo_root / unit["geometry_path"]
    geom_wgs84 = select_geometry(geometry_path, unit.get("geometry_selector"))

    pre_meta = r2["pre"]["output"]["metadata_only"]
    post_meta = r2["post"]["output"]["metadata_only"]
    if pre_meta["crs"] != post_meta["crs"]:
        raise ValueError("PRE/POST CRS differs; geometry-only footprint audit not comparable")
    target_crs = pre_meta["crs"]
    transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    geom = shapely_transform(transformer.transform, geom_wgs84)
    if geom.is_empty or geom.area <= 0:
        raise ValueError("projected basin geometry has zero area")

    pre_fp = box(*[float(x) for x in pre_meta["bounds"]])
    post_fp = box(*[float(x) for x in post_meta["bounds"]])
    pre_fraction = float(geom.intersection(pre_fp).area / geom.area)
    post_fraction = float(geom.intersection(post_fp).area / geom.area)
    joint_fraction = float(geom.intersection(pre_fp).intersection(post_fp).area / geom.area)
    threshold = float(contract["r3_rule"]["minimum_common_support_fraction"])

    return {
        "schema_version": "irfen-ibvf-primary6-geometry-footprint-audit-v0.1",
        "generated_at": now(),
        "case_id": r2["case_id"],
        "unit_id": unit_id,
        "season_id": r2.get("season_id"),
        "date_local": r2.get("date_local"),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "territorial_activation_evidence_blinded": True,
        "source_r3_status": BLOCKED_STATUS,
        "audit_scope": "FROZEN_BASIN_POLYGON_INTERSECTION_WITH_R2_METADATA_FOOTPRINTS_ONLY",
        "geometry_path": unit["geometry_path"],
        "geometry_selector": unit.get("geometry_selector"),
        "target_crs": target_crs,
        "basin_projected_area_km2": round(float(geom.area) / 1_000_000.0, 9),
        "pre_r2_metadata_bounds": [float(x) for x in pre_meta["bounds"]],
        "post_r2_metadata_bounds": [float(x) for x in post_meta["bounds"]],
        "pre_geometry_footprint_coverage_fraction": pre_fraction,
        "post_geometry_footprint_coverage_fraction": post_fraction,
        "joint_geometry_footprint_coverage_fraction": joint_fraction,
        "pre_geometry_footprint_coverage_pct": pct(pre_fraction),
        "post_geometry_footprint_coverage_pct": pct(post_fraction),
        "joint_geometry_footprint_coverage_pct": pct(joint_fraction),
        "joint_missing_geometry_area_km2": round(float(geom.area * (1.0 - joint_fraction)) / 1_000_000.0, 9),
        "frozen_r3_minimum_common_support_fraction_reference_only": threshold,
        "joint_geometry_footprint_coverage_ge_frozen_r3_reference": joint_fraction >= threshold,
        "important_interpretation_guard": "GEOMETRY_FOOTPRINT_COVERAGE_IS_NOT_R3_COMMON_VALID_PIXEL_SUPPORT_AND_DOES_NOT_AUTHORIZE_R4",
        "raster_files_opened": False,
        "raster_pixels_read": False,
        "radiometric_values_read": False,
        "radiometric_statistics_computed": False,
        "r4_values_read": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "status": "PASS_SIGNAL_BLIND_GEOMETRY_FOOTPRINT_DIAGNOSTIC_ONLY",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", type=Path, required=True)
    ap.add_argument("--global-contract", type=Path, required=True)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    contract = load(args.global_contract)
    if contract.get("deployment_status") != "RESEARCH_ONLY" or contract.get("test_only") is not True:
        raise SystemExit("global contract research/test guards are not frozen")
    if contract.get("production_use") is not False or contract.get("production_ready") is not False:
        raise SystemExit("global contract production guards are not frozen")
    if contract.get("operational_alerting_enabled") is not False:
        raise SystemExit("global contract operational alerting guard is not frozen")

    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r2_path in sorted(args.artifact_root.rglob("r2-v02.json")):
        case_dir = r2_path.parent
        if case_dir.name in seen:
            continue
        result = audit_case(case_dir, contract, args.repo_root)
        if result is not None:
            seen.add(case_dir.name)
            cases.append(result)

    summary = {
        "schema_version": "irfen-ibvf-primary6-geometry-footprint-audit-summary-v0.1",
        "generated_at": now(),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "territorial_activation_evidence_blinded": True,
        "blocked_cases_audited": len(cases),
        "all_joint_geometry_footprint_coverage_ge_frozen_r3_reference": bool(cases) and all(c["joint_geometry_footprint_coverage_ge_frozen_r3_reference"] for c in cases),
        "raster_files_opened": False,
        "raster_pixels_read": False,
        "radiometric_values_read": False,
        "r4_values_read": False,
        "territorial_outcomes_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "cases": cases,
        "status": "PASS_SIGNAL_BLIND_GEOMETRY_FOOTPRINT_AUDIT" if cases else "NO_R3_WINDOW_BLOCKERS_FOUND",
    }
    write(args.output, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if cases else 3


if __name__ == "__main__":
    raise SystemExit(main())
