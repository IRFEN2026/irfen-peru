#!/usr/bin/env python3
"""IBVF Cashahuacra v0.3 nearest-same-channel snap experiment.

RESEARCH_ONLY / TEST_ONLY. This is the predeclared follow-up to the v0.2
radial-snap audit. It never uses a target basin area, territorial activation
outcome, operational threshold, or EVENT/NONE label.

The four original radial maxima are retained only as independent anchors.
For each anchor, the script reconstructs a deterministic D8 main channel by
combining the highest-accumulation upstream branch with the downstream D8 path,
then selects the channel cell geodesically nearest to the ANA 0+000 seed.
The outlet is frozen only if all four anchor-derived channels select exactly
the same cell. A <=45 m cluster is diagnostic only and does not relax this gate.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import xy
from shapely.geometry import shape

import ibvf_cashahuacra_dem_snap as base


def upstream_neighbors(
    fdir: np.ndarray,
    acc: np.ndarray,
    cell: tuple[int, int],
) -> list[tuple[float, int, int]]:
    r, c = cell
    out: list[tuple[float, int, int]] = []
    for nr in range(max(0, r - 1), min(fdir.shape[0], r + 2)):
        for nc in range(max(0, c - 1), min(fdir.shape[1], c + 2)):
            if (nr, nc) == (r, c):
                continue
            try:
                code = int(fdir[nr, nc])
            except (TypeError, ValueError, OverflowError):
                continue
            off = base.D8_OFFSETS.get(code)
            if off is None or (nr + off[0], nc + off[1]) != (r, c):
                continue
            value = float(acc[nr, nc])
            if np.isfinite(value) and value > 0:
                out.append((value, nr, nc))
    return out


def trace_upstream_mainstem(
    fdir: np.ndarray,
    acc: np.ndarray,
    start: tuple[int, int],
    max_steps: int = 10000,
) -> list[tuple[int, int]]:
    current = (int(start[0]), int(start[1]))
    visited = [current]
    seen = {current}
    for _ in range(max_steps):
        candidates = upstream_neighbors(fdir, acc, current)
        if not candidates:
            break
        candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
        nxt = (int(candidates[0][1]), int(candidates[0][2]))
        if nxt in seen:
            break
        visited.append(nxt)
        seen.add(nxt)
        current = nxt
    return visited


def channel_from_anchor(
    fdir: np.ndarray,
    acc: np.ndarray,
    anchor: tuple[int, int],
) -> list[tuple[int, int]]:
    upstream = trace_upstream_mainstem(fdir, acc, anchor)
    downstream = base.trace_downstream_cells(fdir, anchor)
    cells: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for cell in reversed(upstream[1:]) + downstream:
        if cell not in seen:
            cells.append(cell)
            seen.add(cell)
    return cells


def nearest_cell(
    channel: list[tuple[int, int]],
    acc: np.ndarray,
    transform: Any,
    seed_lon: float,
    seed_lat: float,
) -> dict[str, Any]:
    best = None
    for r, c in channel:
        lon, lat = xy(transform, r, c, offset="center")
        d = base.distance_m(seed_lon, seed_lat, float(lon), float(lat))
        value = float(acc[r, c])
        candidate = (d, -value, r, c, float(lon), float(lat))
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return {"status": "NO_CHANNEL_CELL"}
    d, neg_acc, r, c, lon, lat = best
    return {
        "status": "SELECTED",
        "row": int(r),
        "col": int(c),
        "lon": lon,
        "lat": lat,
        "seed_distance_m": round(float(d), 3),
        "accumulation_cells": round(float(-neg_acc), 3),
    }


def max_cluster_m(results: list[dict[str, Any]]) -> float | None:
    good = [x for x in results if x.get("status") == "SELECTED"]
    if len(good) != len(base.SNAP_RADII_M):
        return None
    mx = 0.0
    for i, a in enumerate(good):
        for b in good[i + 1 :]:
            mx = max(mx, base.distance_m(a["lon"], a["lat"], b["lon"], b["lat"]))
    return mx


def basic_morphometry(grid: Any, fdir: Any, selected: dict[str, Any], dem: np.ndarray) -> dict[str, Any]:
    catch = grid.catchment(
        x=selected["lon"],
        y=selected["lat"],
        fdir=fdir,
        dirmap=base.DIRMAP,
        xytype="coordinate",
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

    seed_lon, seed_lat = base.seed_lonlat()
    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-cashahuacra-nearest-channel-snap-v0.3",
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
        "ana_seed": {
            **base.ANA_SEED_UTM18S,
            "lon": seed_lon,
            "lat": seed_lat,
            "role": "SNAP_SEARCH_SEED_ONLY",
        },
        "contract": {
            "anchor_radii_m": base.SNAP_RADII_M,
            "anchor_role": "CHANNEL_IDENTIFICATION_ONLY",
            "channel_definition": "HIGHEST_ACCUMULATION_UPSTREAM_MAINSTEM_PLUS_D8_DOWNSTREAM_PATH",
            "selection": "NEAREST_CHANNEL_CELL_TO_ANA_SEED",
            "freeze_gate": "EXACT_SAME_CELL_FROM_ALL_FOUR_ANCHOR_DERIVED_CHANNELS",
            "cluster_45m_is_diagnostic_only": True,
            "target_basin_area_used": False,
            "territorial_activation_evidence_used": False,
            "morphometry_before_freeze_forbidden": True,
        },
        "dem": {
            "collection": "cop-dem-glo-30",
            "item_id": base.TILE_ID,
            "url": base.TILE_URL,
        },
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_cash_nearest_") as td_raw:
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

            anchors = [
                base.select_max_acc_within_radius(acc_arr, transform, seed_lon, seed_lat, radius)
                for radius in base.SNAP_RADII_M
            ]
            topo = base.topology_audit(anchors, fdir_arr)
            report["anchor_topology"] = topo
            report["anchors"] = anchors

            results: list[dict[str, Any]] = []
            for anchor in sorted(anchors, key=lambda x: float(x.get("radius_m", 0))):
                if anchor.get("status") != "SELECTED":
                    results.append({"anchor_radius_m": anchor.get("radius_m"), "status": "ANCHOR_UNAVAILABLE"})
                    continue
                channel = channel_from_anchor(fdir_arr, acc_arr, (anchor["row"], anchor["col"]))
                snapped = nearest_cell(channel, acc_arr, transform, seed_lon, seed_lat)
                snapped.update({
                    "anchor_radius_m": anchor["radius_m"],
                    "anchor_row": anchor["row"],
                    "anchor_col": anchor["col"],
                    "channel_cell_count": len(channel),
                })
                results.append(snapped)

            good = [x for x in results if x.get("status") == "SELECTED"]
            cells = {(x["row"], x["col"]) for x in good}
            exact = len(good) == len(base.SNAP_RADII_M) and len(cells) == 1
            cluster = max_cluster_m(results)
            report["nearest_same_channel"] = {
                "anchor_results": results,
                "exact_cell_agreement": exact,
                "max_cluster_distance_m": None if cluster is None else round(cluster, 3),
            }
            report["scientific_data_status"] = "PRESENT"

            if exact:
                chosen = good[0]
                report["snap_status"] = "STABLE_EXACT_CELL_AGREEMENT"
                report["selected_outlet"] = chosen
                basin = base.delineate_if_stable(grid, fdir, transform, chosen)
                metrics = basic_morphometry(grid, fdir, chosen, dem)
                geom = shape(basin["geometry"])
                area_m2, perimeter_m = base.GEOD.geometry_area_perimeter(geom)
                metrics.update({
                    "area_km2": round(abs(float(area_m2)) / 1e6, 3),
                    "perimeter_km": round(abs(float(perimeter_m)) / 1000.0, 3),
                    "morphometry_scope": "BASIC_DEM_DERIVED_AFTER_EXACT_CELL_FREEZE_ONLY",
                })
                basin["properties"].update(metrics)
                basin["properties"]["geometry_status"] = "DELINEATED_AFTER_STABLE_NEAREST_SAME_CHANNEL_SNAP"
                report["morphometry_status"] = "BASIC_MORPHOMETRY_COMPUTED_AFTER_EXACT_CELL_FREEZE"
                report["morphometry"] = metrics
                if args.basin_output:
                    args.basin_output.parent.mkdir(parents=True, exist_ok=True)
                    args.basin_output.write_text(json.dumps(basin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            elif cluster is not None and cluster <= base.STABILITY_MAX_CLUSTER_M:
                report["snap_status"] = "NEAR_STABLE_WITHIN_45M_NOT_FROZEN_EXACT_AGREEMENT_REQUIRED"
                report["morphometry_status"] = "BLOCKED_EXACT_CELL_GATE_NOT_PASSED"
            else:
                report["snap_status"] = "UNSTABLE_NEAREST_SAME_CHANNEL_REVIEW_REQUIRED"
                report["morphometry_status"] = "BLOCKED_EXACT_CELL_GATE_NOT_PASSED"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "snap_status": report.get("snap_status"),
        "nearest_same_channel": report.get("nearest_same_channel"),
        "selected_outlet": report.get("selected_outlet"),
        "morphometry_status": report.get("morphometry_status"),
        "morphometry": report.get("morphometry"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
