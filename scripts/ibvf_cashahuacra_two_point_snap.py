#!/usr/bin/env python3
"""Cashahuacra ANA two-point / pre-confluence snap for IRFEN IBVF.

RESEARCH_ONLY / TEST_ONLY.

The v0.1 two-point experiment still reached the same 69.423 km² downstream
cell because the Cashahuacra D8 path had already merged into a larger drainage
before reaching ANA 0+000. Version 0.2 therefore keeps the same upstream ANA
2+180 anchor sensitivity, but defines the tributary outlet topologically as the
last tracked Cashahuacra cell immediately before the first downstream
confluence where a competing upstream branch has greater D8 accumulation than
the tracked branch. This is a channel-network rule, not an area-fitting rule.

No target basin area, published catchment length, territorial activation
outcome, operational threshold, or EVENT/NONE label is used for selection.
Freeze requires all four independently anchored paths to identify exactly the
same pre-confluence cell and that cell to remain within the predeclared 360 m
search neighborhood of ANA 0+000. Morphometry is computed only after freeze.
Published historical geometry is reserved for post-hoc identity diagnostics.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import xy
from shapely.geometry import shape

import ibvf_cashahuacra_dem_snap as base
import ibvf_cashahuacra_nearest_channel_snap as nearest

ANA_UPSTREAM_UTM18S = {
    "easting_m": 317437.0,
    "northing_m": 8683757.0,
    "epsg": 32718,
    "progressive": "2+180",
}
UPSTREAM_ANCHOR_RADII_M = [60.0, 120.0, 240.0, 360.0]
DOWNSTREAM_SEED_MAX_DISTANCE_M = 360.0


def utm_to_lonlat(p: dict[str, Any]) -> tuple[float, float]:
    tr = Transformer.from_crs(int(p["epsg"]), 4326, always_xy=True)
    return tr.transform(float(p["easting_m"]), float(p["northing_m"]))


def pre_larger_branch_confluence(
    path: list[tuple[int, int]],
    fdir: np.ndarray,
    acc: np.ndarray,
    transform: Any,
    seed_lon: float,
    seed_lat: float,
) -> dict[str, Any]:
    """Return last tracked cell before joining a larger competing branch."""
    for idx in range(len(path) - 1):
        current = path[idx]
        nxt = path[idx + 1]
        current_acc = float(acc[current[0], current[1]])
        competitors = [x for x in nearest.upstream_neighbors(fdir, acc, nxt) if (x[1], x[2]) != current]
        larger = [x for x in competitors if float(x[0]) > current_acc]
        if not larger:
            continue
        larger.sort(key=lambda x: (-x[0], x[1], x[2]))
        comp_acc, comp_r, comp_c = larger[0]
        lon, lat = xy(transform, current[0], current[1], offset="center")
        next_lon, next_lat = xy(transform, nxt[0], nxt[1], offset="center")
        return {
            "status": "SELECTED_PRE_LARGER_BRANCH_CONFLUENCE",
            "row": int(current[0]),
            "col": int(current[1]),
            "lon": float(lon),
            "lat": float(lat),
            "distance_to_ana_0plus000_m": round(base.distance_m(seed_lon, seed_lat, float(lon), float(lat)), 3),
            "accumulation_cells": round(current_acc, 3),
            "confluence_next_row": int(nxt[0]),
            "confluence_next_col": int(nxt[1]),
            "confluence_next_lon": float(next_lon),
            "confluence_next_lat": float(next_lat),
            "competing_branch_row": int(comp_r),
            "competing_branch_col": int(comp_c),
            "competing_branch_accumulation_cells": round(float(comp_acc), 3),
            "tracked_to_competing_accumulation_ratio": round(current_acc / float(comp_acc), 6),
            "path_index": idx,
        }
    return {"status": "NO_LARGER_BRANCH_CONFLUENCE_FOUND"}


def basic_morphometry(grid: Any, fdir: Any, selected: dict[str, Any], dem: np.ndarray) -> dict[str, Any]:
    catch = grid.catchment(
        x=selected["lon"], y=selected["lat"], fdir=fdir,
        dirmap=base.DIRMAP, xytype="coordinate",
    )
    mask = np.asarray(catch).astype(bool)
    vals = dem[mask & np.isfinite(dem) & (dem > -9000)].astype(float)
    if not vals.size:
        raise RuntimeError("No valid DEM values inside frozen catchment")
    return {
        "catchment_cells": int(mask.sum()),
        "elevation_min_m": round(float(np.min(vals)), 2),
        "elevation_max_m": round(float(np.max(vals)), 2),
        "elevation_mean_m": round(float(np.mean(vals)), 2),
        "elevation_median_m": round(float(np.median(vals)), 2),
        "relief_m": round(float(np.max(vals) - np.min(vals)), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--basin-output", type=Path)
    args = ap.parse_args()

    down_lon, down_lat = base.seed_lonlat()
    up_lon, up_lat = utm_to_lonlat(ANA_UPSTREAM_UTM18S)
    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-cashahuacra-ana-two-point-preconfluence-snap-v0.2",
        "generated_at": base.now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "ana_geometry": {
            "downstream_0plus000": {**base.ANA_SEED_UTM18S, "lon": down_lon, "lat": down_lat, "role": "DOWNSTREAM_SPATIAL_SANITY_SEED_ONLY"},
            "upstream_2plus180": {**ANA_UPSTREAM_UTM18S, "lon": up_lon, "lat": up_lat, "role": "UPSTREAM_CHANNEL_IDENTITY_ANCHOR_ONLY"},
        },
        "contract": {
            "upstream_anchor_radii_m": UPSTREAM_ANCHOR_RADII_M,
            "upstream_selection": "MAXIMUM_D8_FLOW_ACCUMULATION_WITHIN_RADIUS_AROUND_ANA_2PLUS180",
            "outlet_selection": "LAST_TRACKED_CELL_BEFORE_FIRST_CONFLUENCE_WITH_A_LARGER_COMPETING_UPSTREAM_BRANCH",
            "freeze_gate_exact_same_preconfluence_cell_all_anchor_radii": True,
            "freeze_gate_downstream_seed_max_distance_m": DOWNSTREAM_SEED_MAX_DISTANCE_M,
            "target_basin_area_used": False,
            "published_basin_length_used": False,
            "territorial_activation_evidence_used": False,
            "operational_threshold_used": False,
            "morphometry_before_freeze_forbidden": True,
        },
        "dem": {"collection": "cop-dem-glo-30", "item_id": base.TILE_ID, "url": base.TILE_URL},
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_cash_two_point_") as td_raw:
        td = Path(td_raw)
        raw = td / f"{base.TILE_ID}.tif"
        frozen = base.download(base.TILE_URL, raw)
        report["dem"]["acquisition"] = frozen
        if frozen.get("transport_status") != "SUCCESS":
            report["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
            report["snap_status"] = "NOT_RUN_TRANSPORT_BLOCKED"
            report["morphometry_status"] = "NOT_RUN_TRANSPORT_BLOCKED"
        else:
            cropped = td / "cashahuacra_dem_crop.tif"
            base.crop_tile(raw, cropped)
            report["dem"]["crop_sha256"] = base.sha256_file(cropped)

            grid = base.Grid.from_raster(str(cropped))
            z = grid.read_raster(str(cropped))
            dem = np.asarray(z).astype(float)
            conditioned = grid.fill_pits(z)
            conditioned = grid.fill_depressions(conditioned)
            conditioned = grid.resolve_flats(conditioned)
            fdir = grid.flowdir(conditioned, dirmap=base.DIRMAP)
            acc = grid.accumulation(fdir, dirmap=base.DIRMAP)
            fdir_arr, acc_arr = np.asarray(fdir), np.asarray(acc)
            with rasterio.open(cropped) as src:
                transform = src.transform

            results: list[dict[str, Any]] = []
            anchors: list[dict[str, Any]] = []
            for radius in UPSTREAM_ANCHOR_RADII_M:
                anchor = base.select_max_acc_within_radius(acc_arr, transform, up_lon, up_lat, radius)
                anchors.append(anchor)
                if anchor.get("status") != "SELECTED":
                    results.append({"anchor_radius_m": radius, "status": "UPSTREAM_ANCHOR_UNAVAILABLE"})
                    continue
                path = base.trace_downstream_cells(fdir_arr, (anchor["row"], anchor["col"]))
                selected = pre_larger_branch_confluence(path, fdir_arr, acc_arr, transform, down_lon, down_lat)
                selected.update({
                    "anchor_radius_m": radius,
                    "upstream_anchor_row": anchor["row"],
                    "upstream_anchor_col": anchor["col"],
                    "upstream_anchor_distance_m": anchor["seed_distance_m"],
                    "upstream_anchor_accumulation_cells": anchor["accumulation_cells"],
                    "downstream_path_cell_count": len(path),
                })
                results.append(selected)

            good = [x for x in results if x.get("status") == "SELECTED_PRE_LARGER_BRANCH_CONFLUENCE"]
            cells = {(x["row"], x["col"]) for x in good}
            exact = len(good) == len(UPSTREAM_ANCHOR_RADII_M) and len(cells) == 1
            within_seed = exact and all(float(x["distance_to_ana_0plus000_m"]) <= DOWNSTREAM_SEED_MAX_DISTANCE_M for x in good)
            report["upstream_anchors"] = anchors
            report["preconfluence_results"] = {
                "results": results,
                "exact_cell_agreement": exact,
                "all_within_downstream_seed_gate": within_seed,
            }
            report["scientific_data_status"] = "PRESENT"

            if exact and within_seed:
                chosen = good[0]
                report["snap_status"] = "STABLE_PRE_LARGER_BRANCH_CONFLUENCE_GATE_PASSED"
                report["selected_outlet"] = chosen
                basin = base.delineate_if_stable(grid, fdir, transform, chosen)
                metrics = basic_morphometry(grid, fdir, chosen, dem)
                geom = shape(basin["geometry"])
                area_m2, perimeter_m = base.GEOD.geometry_area_perimeter(geom)
                metrics.update({
                    "area_km2": round(abs(float(area_m2)) / 1e6, 3),
                    "perimeter_km": round(abs(float(perimeter_m)) / 1000.0, 3),
                    "morphometry_scope": "BASIC_DEM_DERIVED_AFTER_PRECONFLUENCE_IDENTITY_FREEZE_ONLY",
                })
                basin["properties"].update(metrics)
                basin["properties"]["geometry_status"] = "DELINEATED_AFTER_ANA_TWO_POINT_PRECONFLUENCE_SNAP"
                report["morphometry_status"] = "BASIC_MORPHOMETRY_COMPUTED_AFTER_PRECONFLUENCE_FREEZE"
                report["morphometry"] = metrics
                if args.basin_output:
                    args.basin_output.parent.mkdir(parents=True, exist_ok=True)
                    args.basin_output.write_text(json.dumps(basin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            elif exact:
                report["snap_status"] = "EXACT_PRECONFLUENCE_CELL_BUT_TOO_FAR_FROM_ANA_0PLUS000_NOT_FROZEN"
                report["morphometry_status"] = "BLOCKED_DOWNSTREAM_SEED_GATE"
            else:
                report["snap_status"] = "UNSTABLE_PRECONFLUENCE_CHANNEL_IDENTITY_REVIEW_REQUIRED"
                report["morphometry_status"] = "BLOCKED_EXACT_CELL_GATE_NOT_PASSED"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "snap_status": report.get("snap_status"),
        "selected_outlet": report.get("selected_outlet"),
        "morphometry_status": report.get("morphometry_status"),
        "morphometry": report.get("morphometry"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
