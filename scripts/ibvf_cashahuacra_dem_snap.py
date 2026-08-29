#!/usr/bin/env python3
"""Cashahuacra GLO-30 freeze + hydrologic snap sensitivity for IRFEN IBVF.

RESEARCH_ONLY / TEST_ONLY. The ANA RD 1634-2015 0+000 coordinate is used only
as a spatial seed. No historical activation evidence, target basin area, risk
threshold, or operational EVENT/NONE label is used to choose the outlet.

The script freezes the exact Copernicus DEM GLO-30 tile by SHA-256, derives a
conditioned D8 flow field, and independently selects the maximum-flow-
accumulation cell inside four predeclared metric radii around the ANA seed.

Version 0.2 adds a topology audit. A nested-radius maximum-accumulation search
has an inherent downstream bias: as radius grows, the maximum can move farther
down the same channel even when the channel itself is unambiguous. Therefore
cluster distance remains a conservative freeze gate, but D8 connectivity is
reported separately so radial objective drift is not misreported as evidence
of multiple competing channels. Basin delineation remains blocked unless the
predeclared cluster gate passes; the topology audit does not relax that gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
from pyproj import Geod, Transformer
from pysheds.grid import Grid
from rasterio.features import shapes
from rasterio.mask import mask as rio_mask
from rasterio.transform import rowcol, xy
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

TILE_ID = "Copernicus_DSM_COG_10_S12_00_W077_00_DEM"
TILE_URL = f"https://copernicus-dem-30m.s3.amazonaws.com/{TILE_ID}/{TILE_ID}.tif"
ANA_SEED_UTM18S = {"easting_m": 318847.0, "northing_m": 8682257.0, "epsg": 32718}
SNAP_RADII_M = [60.0, 120.0, 240.0, 360.0]
STABILITY_MAX_CLUSTER_M = 45.0
PROCESS_BOUNDS_WGS84 = [-76.72, -11.94, -76.62, -11.82]
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
D8_OFFSETS = {
    64: (-1, 0),
    128: (-1, 1),
    1: (0, 1),
    2: (1, 1),
    4: (1, 0),
    8: (1, -1),
    16: (0, -1),
    32: (-1, -1),
}
GEOD = Geod(ellps="WGS84")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def download(url: str, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=180, headers={"User-Agent": "IRFEN-IBVF/0.2 RESEARCH_ONLY TEST_ONLY"}) as r:
            r.raise_for_status()
            with path.open("wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return {"transport_status": "SUCCESS", "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    except Exception as exc:
        if path.exists():
            path.unlink()
        return {"transport_status": "TRANSPORT_BLOCKED", "error": repr(exc)}


def seed_lonlat() -> tuple[float, float]:
    tr = Transformer.from_crs(ANA_SEED_UTM18S["epsg"], 4326, always_xy=True)
    return tr.transform(ANA_SEED_UTM18S["easting_m"], ANA_SEED_UTM18S["northing_m"])


def crop_tile(src_path: Path, out_path: Path) -> None:
    with rasterio.open(src_path) as src:
        geom = mapping(box(*PROCESS_BOUNDS_WGS84))
        data, transform = rio_mask(src, [geom], crop=True, filled=True, nodata=-9999)
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            height=data.shape[1],
            width=data.shape[2],
            transform=transform,
            count=1,
            dtype="float32",
            nodata=-9999,
            compress="deflate",
        )
        arr = data[0].astype("float32")
        arr[~np.isfinite(arr)] = -9999
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(arr, 1)


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    _, _, d = GEOD.inv(lon1, lat1, lon2, lat2)
    return abs(float(d))


def select_max_acc_within_radius(acc: np.ndarray, transform: Any, seed_lon: float, seed_lat: float, radius_m: float) -> dict[str, Any]:
    rr, cc = rowcol(transform, seed_lon, seed_lat)
    pixel_radius = max(3, int(math.ceil(radius_m / 20.0)) + 2)
    best = None
    for r in range(max(0, rr - pixel_radius), min(acc.shape[0], rr + pixel_radius + 1)):
        for c in range(max(0, cc - pixel_radius), min(acc.shape[1], cc + pixel_radius + 1)):
            value = float(acc[r, c])
            if not np.isfinite(value) or value <= 0:
                continue
            lon, lat = xy(transform, r, c, offset="center")
            d = distance_m(seed_lon, seed_lat, lon, lat)
            if d > radius_m:
                continue
            candidate = (value, -d, r, c, float(lon), float(lat), d)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return {"radius_m": radius_m, "status": "NO_VALID_ACCUMULATION_CELL"}
    value, _, r, c, lon, lat, d = best
    return {
        "radius_m": radius_m,
        "status": "SELECTED",
        "row": int(r),
        "col": int(c),
        "lon": lon,
        "lat": lat,
        "seed_distance_m": round(d, 3),
        "accumulation_cells": round(value, 3),
    }


def cluster_max_distance(selections: list[dict[str, Any]]) -> float | None:
    good = [s for s in selections if s.get("status") == "SELECTED"]
    if len(good) != len(SNAP_RADII_M):
        return None
    mx = 0.0
    for i, a in enumerate(good):
        for b in good[i + 1:]:
            mx = max(mx, distance_m(a["lon"], a["lat"], b["lon"], b["lat"]))
    return mx


def trace_downstream_cells(fdir: np.ndarray, start: tuple[int, int], max_steps: int = 10000) -> list[tuple[int, int]]:
    r, c = start
    visited: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for _ in range(max_steps):
        cell = (int(r), int(c))
        if cell in seen:
            break
        if not (0 <= r < fdir.shape[0] and 0 <= c < fdir.shape[1]):
            break
        visited.append(cell)
        seen.add(cell)
        try:
            code = int(fdir[r, c])
        except (TypeError, ValueError, OverflowError):
            break
        offset = D8_OFFSETS.get(code)
        if offset is None:
            break
        r += offset[0]
        c += offset[1]
    return visited


def topology_audit(selections: list[dict[str, Any]], fdir: np.ndarray) -> dict[str, Any]:
    good = [s for s in selections if s.get("status") == "SELECTED"]
    if len(good) != len(SNAP_RADII_M):
        return {
            "status": "UNKNOWN_INCOMPLETE_SELECTIONS",
            "same_d8_channel_downstream_order": None,
            "accumulation_monotonic_non_decreasing": None,
        }

    ordered = sorted(good, key=lambda x: float(x["radius_m"]))
    pair_checks = []
    all_downstream = True
    for a, b in zip(ordered, ordered[1:]):
        path = set(trace_downstream_cells(fdir, (a["row"], a["col"])))
        b_cell = (b["row"], b["col"])
        is_downstream = b_cell in path
        all_downstream = all_downstream and is_downstream
        pair_checks.append({
            "from_radius_m": a["radius_m"],
            "to_radius_m": b["radius_m"],
            "to_cell_is_on_downstream_d8_path": is_downstream,
        })

    acc_values = [float(s["accumulation_cells"]) for s in ordered]
    monotonic = all(b >= a for a, b in zip(acc_values, acc_values[1:]))
    if all_downstream and monotonic:
        status = "SAME_D8_CHANNEL_DOWNSTREAM_RADIAL_DRIFT"
    elif all_downstream:
        status = "SAME_D8_CHANNEL_NONMONOTONIC_ACCUMULATION_REVIEW_REQUIRED"
    else:
        status = "MULTICHANNEL_OR_TOPOLOGY_AMBIGUITY_REVIEW_REQUIRED"
    return {
        "status": status,
        "same_d8_channel_downstream_order": all_downstream,
        "accumulation_monotonic_non_decreasing": monotonic,
        "pair_checks": pair_checks,
        "interpretation": (
            "Nested-radius maximum accumulation can drift downstream by construction; topology is reported separately and does not relax the coordinate-cluster freeze gate."
        ),
    }


def geodesic_area_km2(geom: Any) -> float:
    area, _ = GEOD.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def delineate_if_stable(grid: Grid, fdir: Any, transform: Any, selected: dict[str, Any]) -> dict[str, Any]:
    catch = grid.catchment(x=selected["lon"], y=selected["lat"], fdir=fdir, dirmap=DIRMAP, xytype="coordinate")
    arr = np.asarray(catch).astype(bool)
    parts = [shape(g) for g, v in shapes(arr.astype("uint8"), mask=arr, transform=transform) if int(v) == 1]
    if not parts:
        raise RuntimeError("Stable outlet produced empty catchment")
    geom = unary_union(parts).buffer(0)
    return {
        "type": "Feature",
        "properties": {
            "unit_id": "cashahuacra",
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "geometry_status": "DELINEATED_AFTER_STABLE_SNAP",
            "outlet_lon": selected["lon"],
            "outlet_lat": selected["lat"],
            "delineated_area_km2": round(geodesic_area_km2(geom), 3),
            "area_role": "POST_STABILITY_GEOMETRY_DIAGNOSTIC_NOT_OPERATIONAL_THRESHOLD",
        },
        "geometry": mapping(geom),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--basin-output", type=Path)
    args = ap.parse_args()

    seed_lon, seed_lat = seed_lonlat()
    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-cashahuacra-dem-snap-v0.2",
        "generated_at": now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "dem": {"collection": "cop-dem-glo-30", "item_id": TILE_ID, "url": TILE_URL},
        "ana_seed": {**ANA_SEED_UTM18S, "lon": seed_lon, "lat": seed_lat, "role": "SNAP_SEARCH_SEED_ONLY"},
        "process_bounds_wgs84": PROCESS_BOUNDS_WGS84,
        "snap_contract": {
            "radii_m": SNAP_RADII_M,
            "selection": "MAXIMUM_D8_FLOW_ACCUMULATION_WITHIN_RADIUS_NO_TARGET_AREA_USED",
            "stable_if_all_four_selected_cells_cluster_within_m": STABILITY_MAX_CLUSTER_M,
            "topology_audit_relaxes_cluster_gate": False,
            "morphometry_before_stable_snap_forbidden": True,
        },
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_cash_dem_") as td:
        td = Path(td)
        raw = td / f"{TILE_ID}.tif"
        frozen = download(TILE_URL, raw)
        report["dem"]["acquisition"] = frozen
        if frozen.get("transport_status") != "SUCCESS":
            report["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
            report["snap_status"] = "NOT_RUN_TRANSPORT_BLOCKED"
        else:
            cropped = td / "cashahuacra_dem_crop.tif"
            crop_tile(raw, cropped)
            report["dem"]["crop_sha256"] = sha256_file(cropped)

            grid = Grid.from_raster(str(cropped))
            z = grid.read_raster(str(cropped))
            conditioned = grid.fill_pits(z)
            conditioned = grid.fill_depressions(conditioned)
            conditioned = grid.resolve_flats(conditioned)
            fdir = grid.flowdir(conditioned, dirmap=DIRMAP)
            acc = grid.accumulation(fdir, dirmap=DIRMAP)
            fdir_arr = np.asarray(fdir)
            with rasterio.open(cropped) as src:
                transform = src.transform

            selections = [select_max_acc_within_radius(np.asarray(acc), transform, seed_lon, seed_lat, r) for r in SNAP_RADII_M]
            max_cluster = cluster_max_distance(selections)
            stable = max_cluster is not None and max_cluster <= STABILITY_MAX_CLUSTER_M
            topo = topology_audit(selections, fdir_arr)
            report["snap_sensitivity"] = selections
            report["max_selected_outlet_cluster_distance_m"] = None if max_cluster is None else round(max_cluster, 3)
            report["topology_audit"] = topo
            if stable:
                report["snap_status"] = "STABLE_CLUSTER"
            elif topo.get("status") == "SAME_D8_CHANNEL_DOWNSTREAM_RADIAL_DRIFT":
                report["snap_status"] = "UNSTABLE_CLUSTER_SAME_CHANNEL_RADIAL_OBJECTIVE_DRIFT"
            else:
                report["snap_status"] = "UNSTABLE_REVIEW_REQUIRED"
            report["scientific_data_status"] = "PRESENT"

            if stable:
                chosen = selections[0]
                report["selected_outlet"] = chosen
                basin = delineate_if_stable(grid, fdir, transform, chosen)
                report["post_stability_geometry"] = {
                    "delineated": True,
                    "area_km2": basin["properties"]["delineated_area_km2"],
                    "morphometry_status": "AREA_ONLY_GEOMETRY_DIAGNOSTIC_OTHER_MORPHOMETRY_PENDING",
                }
                if args.basin_output:
                    args.basin_output.parent.mkdir(parents=True, exist_ok=True)
                    args.basin_output.write_text(json.dumps(basin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                report["post_stability_geometry"] = {
                    "delineated": False,
                    "morphometry_status": "BLOCKED_CLUSTER_GATE_NOT_PASSED",
                    "next_methodological_step": "PREDECLARE_AND_TEST_NEAREST_SAME_CHANNEL_SNAP_RULE_WITHOUT_TARGET_AREA",
                }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "dem": report["dem"].get("acquisition"),
        "snap_status": report.get("snap_status"),
        "cluster_m": report.get("max_selected_outlet_cluster_distance_m"),
        "topology": report.get("topology_audit"),
        "selected": report.get("selected_outlet"),
        "post": report.get("post_stability_geometry"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
