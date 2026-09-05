#!/usr/bin/env python3
"""Compute outcome-blind phase-1 DEM morphometry for the frozen Chosica 2015 batch.

This script is intentionally unable to read the sealed A6680 numeric reference. It accepts
only frozen geometry artifacts, the frozen outlet registry, geometry diagnostics, and
Copernicus DEM source tiles whose hashes were already recorded during outlet/geometry work.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/chosica_2015_outlet_freeze_registry_v0_1.json"
METHOD = ROOT / "config/chosica_2015_dem_morphometry_contract_v0_1.json"
EXECUTION = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_1.json"
DST = "EPSG:32718"
RES = 30.0
CELL_AREA_M2 = RES * RES
D8 = (64, 128, 1, 2, 4, 8, 16, 32)
D8_STEPS = {
    64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
    4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1),
}
TARGET_KEYS = (
    "cashahuacra", "quirio", "pedregal_san_antonio",
    "la_libertad", "carossio", "rayos_de_sol",
)


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tile_name(lat: float, lon: float) -> str:
    a, b = math.floor(lat), math.floor(lon)
    return f"Copernicus_DSM_COG_10_{('N' if a >= 0 else 'S') + f'{abs(a):02d}'}_00_{('E' if b >= 0 else 'W') + f'{abs(b):03d}'}_00_DEM"


def tile_url(lat: float, lon: float) -> str:
    n = tile_name(lat, lon)
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"


def relevant_tiles(bbox):
    xmin, ymin, xmax, ymax = bbox
    for lat0 in range(math.floor(ymin), math.floor(ymax - 1e-12) + 1):
        for lon0 in range(math.floor(xmin), math.floor(xmax - 1e-12) + 1):
            yield lat0, lon0


def expected_tile_hashes(registry: dict) -> dict[str, str]:
    expected: dict[str, str] = {}
    for key in TARGET_KEYS:
        candidate = ROOT / registry["targets"][key]["candidate_path"]
        data = load_json(candidate)
        for item in data.get("dem_tiles", []):
            url, digest = item["url"], item["sha256"]
            if url in expected and expected[url] != digest:
                raise RuntimeError(f"FAIL_CLOSED_CONFLICTING_SOURCE_TILE_HASH {url}")
            expected[url] = digest
    return expected


def get_tile(cache: Path, lat0: int, lon0: int, expected: dict[str, str]):
    url = tile_url(float(lat0), float(lon0))
    if url not in expected:
        raise RuntimeError(f"FAIL_CLOSED_UNREGISTERED_SOURCE_TILE {url}")
    n = tile_name(float(lat0), float(lon0))
    path = cache / f"{n}.tif"
    if not path.exists():
        r = requests.get(url, timeout=(20, 180))
        r.raise_for_status()
        path.write_bytes(r.content)
    digest = sha256_path(path)
    if digest != expected[url]:
        raise RuntimeError(f"FAIL_CLOSED_SOURCE_TILE_HASH_MISMATCH {url}")
    return path, {"url": url, "sha256": digest, "bytes": path.stat().st_size}


def build_exact_geometry_dem(td: Path, cache: Path, bbox, expected):
    srcs = []
    provenance = []
    try:
        for lat0, lon0 in relevant_tiles(bbox):
            path, prov = get_tile(cache, lat0, lon0, expected)
            provenance.append(prov)
            srcs.append(rasterio.open(path))
        if not srcs:
            raise RuntimeError("FAIL_CLOSED_NO_DEM_TILES")
        arr, src_transform = merge(srcs, bounds=bbox)
        profile = srcs[0].profile.copy()
        src_crs = srcs[0].crs
        h, w = arr.shape[1:]
        left, bottom, right, top = array_bounds(h, w, src_transform)
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src_crs, DST, w, h, left, bottom, right, top, resolution=RES
        )
        src_nodata = profile.get("nodata")
        dst_nodata = -9999.0 if src_nodata is None else float(src_nodata)
        out_arr = np.full((dst_h, dst_w), dst_nodata, dtype="float32")
        reproject(
            source=arr[0], destination=out_arr,
            src_transform=src_transform, src_crs=src_crs, src_nodata=src_nodata,
            dst_transform=dst_transform, dst_crs=DST, dst_nodata=dst_nodata,
            resampling=Resampling.bilinear,
        )
        out = td / "dem.tif"
        profile.update(
            driver="GTiff", width=dst_w, height=dst_h, count=1,
            dtype="float32", crs=DST, transform=dst_transform,
            nodata=dst_nodata, compress="deflate",
        )
        with rasterio.open(out, "w", **profile) as ds:
            ds.write(out_arr, 1)
        return out, provenance
    finally:
        for src in srcs:
            try:
                src.close()
            except Exception:
                pass


def geometry_bbox_from_report(report: dict):
    if "dem_bbox_wgs84" in report:
        return tuple(float(v) for v in report["dem_bbox_wgs84"])
    chosen = float(report["chosen_margin_degrees"])
    attempts = [a for a in report["attempts"] if abs(float(a["margin_degrees"]) - chosen) < 1e-12]
    if len(attempts) != 1 or attempts[0].get("status") != "COMPLETE":
        raise RuntimeError("FAIL_CLOSED_GEOMETRY_REPORT_CHOSEN_ATTEMPT")
    return tuple(float(v) for v in attempts[0]["bbox_wgs84"])


def find_geometry(root: Path, key: str) -> Path:
    candidates = sorted((root / key).glob("*.geojson"))
    if len(candidates) != 1:
        raise RuntimeError(f"FAIL_CLOSED_GEOMETRY_FILE_COUNT {key} {len(candidates)}")
    return candidates[0]


def load_geometry(path: Path):
    doc = load_json(path)
    feats = doc.get("features", [])
    if len(feats) != 1:
        raise RuntimeError(f"FAIL_CLOSED_GEOMETRY_FEATURE_COUNT {path}")
    geom = shape(feats[0]["geometry"])
    if geom.is_empty or not geom.is_valid:
        raise RuntimeError(f"FAIL_CLOSED_INVALID_GEOMETRY {path}")
    return geom


def horn_slope_deg(z: np.ndarray, valid: np.ndarray, dx: float, dy: float):
    out = np.full(z.shape, np.nan, dtype="float64")
    v9 = (
        valid[:-2, :-2] & valid[:-2, 1:-1] & valid[:-2, 2:] &
        valid[1:-1, :-2] & valid[1:-1, 1:-1] & valid[1:-1, 2:] &
        valid[2:, :-2] & valid[2:, 1:-1] & valid[2:, 2:]
    )
    z1, z2, z3 = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    z4, z6 = z[1:-1, :-2], z[1:-1, 2:]
    z7, z8, z9 = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((z3 + 2.0*z6 + z9) - (z1 + 2.0*z4 + z7)) / (8.0 * dx)
    dzdy = ((z7 + 2.0*z8 + z9) - (z1 + 2.0*z2 + z3)) / (8.0 * dy)
    core = np.degrees(np.arctan(np.sqrt(dzdx*dzdx + dzdy*dzdy)))
    out[1:-1, 1:-1][v9] = core[v9]
    return out


def d8_metrics(fdir: np.ndarray, accumulation: np.ndarray, basin: np.ndarray, outlet_rc, area_m2: float, dx: float, dy: float):
    rows, cols = fdir.shape
    orow, ocol = outlet_rc
    if not (0 <= orow < rows and 0 <= ocol < cols):
        raise RuntimeError("FAIL_CLOSED_OUTLET_OUTSIDE_DEM")
    if not basin[orow, ocol]:
        raise RuntimeError("FAIL_CLOSED_OUTLET_CELL_NOT_IN_FROZEN_GEOMETRY_MASK")

    dist = np.full((rows, cols), np.nan, dtype="float64")
    dist[orow, ocol] = 0.0
    upstream: dict[int, list[tuple[int, int, float]]] = {}
    basin_rc = np.argwhere(basin)
    for r, c in basin_rc:
        step = D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if not (0 <= nr < rows and 0 <= nc < cols) or not basin[nr, nc]:
            continue
        link = math.hypot(dx * step[1], dy * step[0])
        upstream.setdefault(nr * cols + nc, []).append((int(r), int(c), link))

    q = deque([(orow, ocol)])
    while q:
        r, c = q.popleft()
        base = float(dist[r, c])
        for ur, uc, link in upstream.get(r * cols + c, []):
            if math.isnan(dist[ur, uc]):
                dist[ur, uc] = base + link
                q.append((ur, uc))
    reached = basin & np.isfinite(dist)
    reached_count = int(reached.sum())
    basin_count = int(basin.sum())
    coverage = reached_count / basin_count if basin_count else 0.0
    if coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_D8_ROUTING_COVERAGE {coverage:.9f}")
    main_length = float(np.nanmax(dist[reached]))

    threshold_m2 = 0.01 * area_m2
    acc_area = np.asarray(accumulation, dtype="float64") * CELL_AREA_M2
    channel = basin & (acc_area >= threshold_m2)
    channel_length = 0.0
    qualifying_links = 0
    for r, c in np.argwhere(channel):
        step = D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if 0 <= nr < rows and 0 <= nc < cols and basin[nr, nc]:
            channel_length += math.hypot(dx * step[1], dy * step[0])
            qualifying_links += 1
    drainage_density = (channel_length / 1000.0) / (area_m2 / 1e6)
    return {
        "routing_coverage_fraction": coverage,
        "routing_reached_cell_count": reached_count,
        "basin_center_cell_count": basin_count,
        "main_channel_length_m": main_length,
        "channel_contributing_area_threshold_m2": threshold_m2,
        "channel_qualifying_link_count": qualifying_links,
        "channel_length_km": channel_length / 1000.0,
        "drainage_density_km_per_km2": drainage_density,
    }


def target_metrics(key: str, geom_path: Path, registry: dict, expected_tiles: dict, cache: Path, work: Path):
    frozen = registry["targets"][key]
    gfreeze = frozen["geometry_freeze"]
    if sha256_path(geom_path) != gfreeze["geometry_geojson_sha256"]:
        raise RuntimeError(f"FAIL_CLOSED_FROZEN_GEOMETRY_HASH {key}")
    geom_wgs = load_geometry(geom_path)
    geom_utm = shp_transform(Transformer.from_crs("EPSG:4326", DST, always_xy=True).transform, geom_wgs)
    if geom_utm.geom_type not in {"Polygon", "MultiPolygon"}:
        raise RuntimeError(f"FAIL_CLOSED_NONPOLYGON_GEOMETRY {key}")
    area_m2 = float(geom_utm.area)
    perimeter_m = float(geom_utm.length)
    if area_m2 <= 0 or perimeter_m <= 0:
        raise RuntimeError(f"FAIL_CLOSED_NONPOSITIVE_GEOMETRY_METRIC {key}")

    report_path = ROOT / gfreeze["diagnostic_path"]
    report = load_json(report_path)
    bbox = geometry_bbox_from_report(report)
    td = work / key
    td.mkdir(parents=True, exist_ok=True)
    dem_path, provenance = build_exact_geometry_dem(td, cache, bbox, expected_tiles)
    dem_hash = sha256_path(dem_path)
    if dem_hash != gfreeze["dem_utm_sha256"]:
        raise RuntimeError(f"FAIL_CLOSED_FROZEN_DEM_HASH {key} {dem_hash} != {gfreeze['dem_utm_sha256']}")

    with rasterio.open(dem_path) as ds:
        z = ds.read(1).astype("float64")
        transform = ds.transform
        nodata = ds.nodata
        dx, dy = abs(float(transform.a)), abs(float(transform.e))
        valid = np.isfinite(z)
        if nodata is not None:
            valid &= z != float(nodata)
        mask = geometry_mask([geom_utm.__geo_interface__], out_shape=z.shape, transform=transform, invert=True, all_touched=False)
        basin = mask & valid
        values = z[basin]
        if values.size == 0:
            raise RuntimeError(f"FAIL_CLOSED_EMPTY_ELEVATION_MASK {key}")
        slopes = horn_slope_deg(z, valid, dx, dy)
        slope_values = slopes[basin & np.isfinite(slopes)]
        if slope_values.size == 0:
            raise RuntimeError(f"FAIL_CLOSED_EMPTY_SLOPE_MASK {key}")
        outlet = frozen["accepted_outlet"]
        outlet_rc = ds.index(float(outlet["x_m"]), float(outlet["y_m"]))
        outlet_center = rasterio.transform.xy(transform, *outlet_rc, offset="center")
        outlet_distance = math.hypot(float(outlet_center[0]) - float(outlet["x_m"]), float(outlet_center[1]) - float(outlet["y_m"]))
        if outlet_distance > math.hypot(dx, dy):
            raise RuntimeError(f"FAIL_CLOSED_OUTLET_MAPPING_TOLERANCE {key}")

    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))
    dem = grid.fill_pits(dem)
    dem = grid.fill_depressions(dem)
    dem = grid.resolve_flats(dem)
    fdir = np.asarray(grid.flowdir(dem, dirmap=D8))
    accumulation = np.asarray(grid.accumulation(fdir, dirmap=D8))
    hydro = d8_metrics(fdir, accumulation, basin, outlet_rc, area_m2, dx, dy)

    return {
        "target_id": key,
        "hydrologic_identity": "corrales" if key == "rayos_de_sol" else key,
        "geometry_geojson_sha256": sha256_path(geom_path),
        "geometry_diagnostic_sha256": sha256_path(report_path),
        "dem_utm_sha256": dem_hash,
        "dem_bbox_wgs84": [round(v, 8) for v in bbox],
        "source_tiles": provenance,
        "outlet_grid_cell": {"row": int(outlet_rc[0]), "col": int(outlet_rc[1]), "center_distance_to_frozen_outlet_m": round(outlet_distance, 6)},
        "area_km2": round(area_m2 / 1e6, 9),
        "perimeter_km": round(perimeter_m / 1000.0, 9),
        "elevation_min_m": round(float(np.min(values)), 6),
        "elevation_max_m": round(float(np.max(values)), 6),
        "relief_m": round(float(np.max(values) - np.min(values)), 6),
        "mean_basin_slope_deg": round(float(np.mean(slope_values)), 9),
        "median_basin_slope_deg": round(float(np.median(slope_values)), 9),
        "p90_basin_slope_deg": round(float(np.percentile(slope_values, 90)), 9),
        "slope_valid_cell_count": int(slope_values.size),
        **{k: (round(v, 9) if isinstance(v, float) else v) for k, v in hydro.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry-root", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)

    registry = load_json(REGISTRY)
    method = load_json(METHOD)
    execution = load_json(EXECUTION)
    guards = {"RESEARCH_ONLY": True, "TEST_ONLY": True, "production_use": False, "production_ready": False, "operational_alerting_enabled": False}
    assert registry["guards"] == guards
    assert method["guards"] == guards
    assert execution["guards"] == guards
    assert registry["batch_gate"]["frozen_outlet_count"] == 6
    assert registry["batch_gate"]["frozen_geometry_count"] == 6
    assert registry["batch_gate"]["batch_morphometry_allowed"] is True
    assert registry["batch_gate"]["unblind_allowed"] is False
    assert method["input_gate"]["a6680_numeric_reference_access_before_output_freeze"] is False
    assert execution["phase_1_output"]["a6680_numeric_reference_read"] is False
    for key in TARGET_KEYS:
        assert registry["targets"][key]["outlet_status"] == "FROZEN"
        assert registry["targets"][key]["geometry_status"] == "FROZEN_BY_REPRODUCIBLE_D8_HASH"

    result = {
        "schema_version": "0.1",
        "batch_id": registry["batch_id"],
        "status": "PENDING",
        "phase": "PHASE_1_PREUNBLIND_DEM_MORPHOMETRY",
        "guards": guards,
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "registry_sha256": sha256_path(REGISTRY),
        "morphometry_contract_sha256": sha256_path(METHOD),
        "execution_contract_sha256": sha256_path(EXECUTION),
        "implementation_sha256": sha256_path(Path(__file__)),
        "target_count": 0,
        "targets": [],
    }
    try:
        expected = expected_tile_hashes(registry)
        with tempfile.TemporaryDirectory(prefix="irfen_chosica_2015_morphometry_") as raw:
            root = Path(raw)
            cache = root / "tile_cache"
            cache.mkdir()
            work = root / "targets"
            work.mkdir()
            for key in TARGET_KEYS:
                geom_path = find_geometry(args.geometry_root, key)
                result["targets"].append(target_metrics(key, geom_path, registry, expected, cache, work))
        result["target_count"] = len(result["targets"])
        if result["target_count"] != 6:
            raise RuntimeError("FAIL_CLOSED_TARGET_COUNT")
        result["status"] = "PASS_CHOSICA_2015_PHASE1_MORPHOMETRY"
    except Exception as exc:
        result["status"] = "FAIL_CLOSED_PHASE1_MORPHOMETRY"
        result["error"] = str(exc)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
