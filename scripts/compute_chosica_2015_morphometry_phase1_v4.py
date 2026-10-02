#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.4.

Regenerates each target's exact geometry-generation DEM from the already-frozen,
outcome-blind geometry inputs and requires binary SHA256 equality with the DEM hash
recorded when that geometry was frozen. It then reuses the frozen v0.3 pour-point
routing semantics and the original morphometry formulas. No A6680 numeric reference,
observed 2015 outcome, or post-anchor predictor is read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyproj import Transformer

import compute_chosica_2015_morphometry_phase1_v3 as v3

v2 = v3.v2
base = v3.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V4 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_4.json"
BASE_IMPLEMENTATION = ROOT / "scripts/compute_chosica_2015_morphometry_phase1.py"
ALIGNMENT_IMPLEMENTATION = ROOT / "scripts/compute_chosica_2015_morphometry_phase1_v2.py"
POURPOINT_IMPLEMENTATION = ROOT / "scripts/compute_chosica_2015_morphometry_phase1_v3.py"
ORIGINAL_BUILD = base.build_exact_geometry_dem
EXACT_DEM_AUDIT: dict[str, dict] = {}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extent_from_utm_points(points: list[dict]) -> tuple[float, float, float, float]:
    tr = Transformer.from_crs(base.DST, "EPSG:4326", always_xy=True)
    ll = [tr.transform(float(p["x_m"]), float(p["y_m"])) for p in points]
    xs = [x for x, _ in ll]
    ys = [y for _, y in ll]
    return min(xs), min(ys), max(xs), max(ys)


def _quirio_base_extent() -> tuple[float, float, float, float]:
    contract = base.load_json(ROOT / "config/chosica_2015_quirio_outlet_resolution_contract_v0_1.json")
    points = contract["static_source"]["points"]
    keys = ("rimac_upstream_bridge_r4", "quirio_r8", "rimac_downstream_bridge_r9")
    tr = Transformer.from_crs(base.DST, "EPSG:4326", always_xy=True)
    ll = [
        tr.transform(float(points[k]["easting_m"]), float(points[k]["northing_m"]))
        for k in keys
    ]
    xs = [x for x, _ in ll]
    ys = [y for _, y in ll]
    return min(xs), min(ys), max(xs), max(ys)


def exact_geometry_bbox(key: str, registry: dict) -> tuple[tuple[float, float, float, float], dict]:
    frozen = registry["targets"][key]
    gfreeze = frozen["geometry_freeze"]

    if key == "cashahuacra":
        contract_path = ROOT / "config/chosica_2015_outlet_resolution_contract_v0_1.json"
        contract = base.load_json(contract_path)
        target = next(x for x in contract["targets"] if x["id"] == "cashahuacra")
        anchor = target["independent_static_anchor"]
        down_lon, down_lat = map(float, anchor["downstream_wgs84"])
        up_lon, up_lat = map(float, anchor["upstream_wgs84"])
        margin = 0.08
        bbox = (
            min(up_lon, down_lon) - margin,
            min(up_lat, down_lat) - margin,
            max(up_lon, down_lon) + margin,
            max(up_lat, down_lat) + margin,
        )
        return bbox, {
            "rule": "CASHAHUACRA_FROZEN_ANA_ANCHORS_PLUS_0_08_DEG",
            "contract_path": str(contract_path.relative_to(ROOT)),
            "contract_sha256": sha256_path(contract_path),
            "chosen_margin_degrees": margin,
        }

    margin = float(gfreeze["chosen_margin_degrees"])
    if key == "quirio":
        geometry_contract_path = ROOT / gfreeze["geometry_contract_path"]
        outlet_contract_path = ROOT / frozen["method_contract_path"]
        base_extent = _quirio_base_extent()
        bbox = (
            base_extent[0] - margin,
            base_extent[1] - margin,
            base_extent[2] + margin,
            base_extent[3] + margin,
        )
        return bbox, {
            "rule": "QUIRIO_FROZEN_MML_R4_R8_R9_BASE_EXTENT_PLUS_CHOSEN_MARGIN",
            "geometry_contract_path": str(geometry_contract_path.relative_to(ROOT)),
            "geometry_contract_sha256": sha256_path(geometry_contract_path),
            "outlet_contract_path": str(outlet_contract_path.relative_to(ROOT)),
            "outlet_contract_sha256": sha256_path(outlet_contract_path),
            "chosen_margin_degrees": margin,
        }

    geometry_contract_path = ROOT / gfreeze["geometry_contract_path"]
    contract = base.load_json(geometry_contract_path)
    base_extent = _extent_from_utm_points(contract["base_extent_points_utm18s"])
    bbox = (
        base_extent[0] - margin,
        base_extent[1] - margin,
        base_extent[2] + margin,
        base_extent[3] + margin,
    )
    return bbox, {
        "rule": "GENERIC_FROZEN_UTM18S_BASE_EXTENT_PLUS_CHOSEN_MARGIN",
        "geometry_contract_path": str(geometry_contract_path.relative_to(ROOT)),
        "geometry_contract_sha256": sha256_path(geometry_contract_path),
        "chosen_margin_degrees": margin,
    }


def build_exact_frozen_geometry_dem(td: Path, cache: Path, diagnostic_bbox, expected):
    target_id = v2.CURRENT_TARGET
    if target_id is None:
        raise RuntimeError("FAIL_CLOSED_EXACT_DEM_TARGET_CONTEXT")
    registry = base.load_json(base.REGISTRY)
    exact_bbox, provenance_rule = exact_geometry_bbox(target_id, registry)
    dem_path, source_tiles = ORIGINAL_BUILD(td, cache, exact_bbox, expected)
    actual_sha = sha256_path(dem_path)
    expected_sha = registry["targets"][target_id]["geometry_freeze"]["dem_utm_sha256"]
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"FAIL_CLOSED_EXACT_GEOMETRY_DEM_HASH_MISMATCH {target_id} "
            f"expected={expected_sha} actual={actual_sha}"
        )
    EXACT_DEM_AUDIT[target_id] = {
        **provenance_rule,
        "exact_bbox_wgs84": [float(v) for v in exact_bbox],
        "diagnostic_bbox_wgs84_rounded": [float(v) for v in diagnostic_bbox],
        "regenerated_dem_geotiff_sha256": actual_sha,
        "frozen_geometry_dem_geotiff_sha256": expected_sha,
        "exact_binary_hash_match": True,
        "source_tile_count": len(source_tiles),
        "geometry_or_outlet_modified": False,
    }
    return dem_path, source_tiles


def annotate_report(report_path: Path) -> None:
    if not report_path.exists():
        return
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    doc["execution_revision"] = "0.4_EXACT_FROZEN_GEOMETRY_DEM_REGENERATION"
    doc["base_implementation_sha256"] = sha256_path(BASE_IMPLEMENTATION)
    doc["alignment_implementation_sha256"] = sha256_path(ALIGNMENT_IMPLEMENTATION)
    doc["pourpoint_implementation_sha256"] = sha256_path(POURPOINT_IMPLEMENTATION)
    doc["exact_geometry_dem_audit"] = EXACT_DEM_AUDIT
    doc["pourpoint_semantics_audit"] = v3.POURPOINT_AUDIT
    doc["revision_guards"] = {
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "selection_or_tuning_from_metric_values": False,
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
    }
    report_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    base.EXECUTION = EXECUTION_V4
    base.build_exact_geometry_dem = build_exact_frozen_geometry_dem
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = v3.d8_metrics_with_frozen_pourpoint
    base.__file__ = str(Path(__file__).resolve())

    import sys
    report_path = None
    for idx, arg in enumerate(sys.argv[:-1]):
        if arg == "--report":
            report_path = Path(sys.argv[idx + 1])
            break

    rc = base.main()
    if report_path is not None:
        annotate_report(report_path)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
