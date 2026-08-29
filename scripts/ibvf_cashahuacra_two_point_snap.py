#!/usr/bin/env python3
"""Cashahuacra ANA two-point channel-identity snap for IRFEN IBVF.

RESEARCH_ONLY / TEST_ONLY.

This method is predeclared after the v0.3 nearest-channel experiment proved
numerically repeatable but failed a separate static geometry identity audit.
It uses only the two ANA RD 1634-2015 Cashahuacra faja-marginal progressive
coordinates to identify the tributary: 2+180 is an upstream channel anchor and
0+000 is the downstream snap seed. No target basin area, published catchment
length, territorial activation outcome, operational threshold, or EVENT/NONE
label is used for selection.

For four fixed radii around ANA 2+180, the maximum D8-accumulation cell is used
as an upstream anchor. Each anchor is traced downstream through the conditioned
GLO-30 D8 network. The selected outlet is the traced cell nearest ANA 0+000.
Freeze requires all four independently anchored paths to choose the exact same
outlet cell and that cell to lie within two GLO-30 pixels (60 m) of ANA 0+000.
Morphometry is computed only after those gates pass. Published historical area
may be compared later as a post-hoc identity diagnostic, never as a selector.
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

ANA_UPSTREAM_UTM18S = {
    "easting_m": 317437.0,
    "northing_m": 8683757.0,
    "epsg": 32718,
    "progressive": "2+180",
}
UPSTREAM_ANCHOR_RADII_M = [60.0, 120.0, 240.0, 360.0]
DOWNSTREAM_SEED_MAX_DISTANCE_M = 60.0


def utm_to_lonlat(p: dict[str, Any]) -> tuple[float, float]:
    tr = Transformer.from_crs(int(p["epsg"]), 4326, always_xy=True)
    return tr.transform(float(p["easting_m"]), float(p["northing_m"]))


def nearest_on_path(
    path: list[tuple[int, int]],
    acc: np.ndarray,
    transform: Any,
    seed_lon: float,
    seed_lat: float,
) -> dict[str, Any]:
    best = None
    for r, c in path:
        lon, lat = xy(transform, r, c, offset="center")
        d = base.distance_m(seed_lon, seed_lat, float(lon), float(lat))
        value = float(acc[r, c])
        candidate = (d, -value, int(r), int(c), float(lon), float(lat))
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return {"status": "NO_DOWNSTREAM_PATH_CELL"}
    d, neg_acc, r, c, lon, lat = best
    return {
        "status": "SELECTED",
        "row": r,
        "col": c,
        "lon": lon,
        "lat": lat,
        "distance_to_ana_0plus000_m": round(float(d), 3),
        "accumulation_cells": round(float(-neg_acc), 3),
    }


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
        "schema_version": "irfen-ibvf-cashahuacra-ana-two-point-snap-v0.1",
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
            "downstream_0plus000": {**base.ANA_SEED_UTM18S, "lon": down_lon, "lat": down_lat, "role": "DOWNSTREAM_SNAP_SEED_ONLY"},
            "upstream_2plus180": {**ANA_UPSTREAM_UTM18S, "lon": up_lon, "lat": up_lat, "role": "UPSTREAM_CHANNEL_IDENTITY_ANCHOR_ONLY"},
        },
        "contract": {
            "upstream_anchor_radii_m": UPSTREAM_ANCHOR_RADII_M,
            "upstream_selection": "MAXIMUM_D8_FLOW_ACCUMULATION_WITHIN_RADIUS_AROUND_ANA_2PLUS180",
            "downstream_selection": "NEAREST_CELL_TO_ANA_0PLUS000_ALONG_D8_PATH_FROM_UPSTREAM_ANCHOR",
            "freeze_gate_exact_same_downstream_cell_all_anchor_radii": True,
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
                selected = nearest_on_path(path, acc_arr, transform, down_lon, down_lat)
                selected.update({
                    "anchor_radius_m": radius,
                    "upstream_anchor_row": anchor["row"],
                    "upstream_anchor_col": anchor["col"],
                    "upstream_anchor_distance_m": anchor["seed_distance_m"],
                    "upstream_anchor_accumulation_cells": anchor["accumulation_cells"],
                    "downstream_path_cell_count": len(path),
                })
                results.append(selected)

            good = [x for x in results if x.get("status") == "SELECTED"]
            cells = {(x["row"], x["col"]) for x in good}
            exact = len(good) == len(UPSTREAM_ANCHOR_RADII_M) and len(cells) == 1
            within_seed = exact and all(float(x["distance_to_ana_0plus000_m"]) <= DOWNSTREAM_SEED_MAX_DISTANCE_M for x in good)
            report["upstream_anchors"] = anchors
            report["downstream_from_upstream_anchor"] = {
                "results": results,
                "exact_cell_agreement": exact,
                "all_within_downstream_seed_gate": within_seed,
            }
            report["scientific_data_status"] = "PRESENT"

            if exact and within_seed:
                chosen = good[0]
                report["snap_status"] = "STABLE_TWO_POINT_CHANNEL_IDENTITY_GATE_PASSED"
                report["selected_outlet"] = chosen
                basin = base.delineate_if_stable(grid, fdir, transform, chosen)
                metrics = basic_morphometry(grid, fdir, chosen, dem)
                geom = shape(basin["geometry"])
                area_m2, perimeter_m = base.GEOD.geometry_area_perimeter(geom)
                metrics.update({
                    "area_km2": round(abs(float(area_m2)) / 1e6, 3),
                    "perimeter_km": round(abs(float(perimeter_m)) / 1000.0, 3),
                    "morphometry_scope": "BASIC_DEM_DERIVED_AFTER_TWO_POINT_IDENTITY_FREEZE_ONLY",
                })
                basin["properties"].update(metrics)
                basin["properties"]["geometry_status"] = "DELINEATED_AFTER_ANA_TWO_POINT_CHANNEL_IDENTITY_SNAP"
                report["morphometry_status"] = "BASIC_MORPHOMETRY_COMPUTED_AFTER_TWO_POINT_FREEZE"
                report["morphometry"] = metrics
                if args.basin_output:
                    args.basin_output.parent.mkdir(parents=True, exist_ok=True)
                    args.basin_output.write_text(json.dumps(basin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            elif exact:
                report["snap_status"] = "EXACT_CELL_BUT_TOO_FAR_FROM_ANA_0PLUS000_NOT_FROZEN"
                report["morphometry_status"] = "BLOCKED_DOWNSTREAM_SEED_GATE"
            else:
                report["snap_status"] = "UNSTABLE_TWO_POINT_CHANNEL_IDENTITY_REVIEW_REQUIRED"
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
