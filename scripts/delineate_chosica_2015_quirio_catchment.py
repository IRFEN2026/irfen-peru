#!/usr/bin/env python3
"""Delineate the frozen Quirio outlet catchment without reading sealed outcomes.

Geometry-only step. It reconstructs the exact DEM used by the frozen outlet diagnostic
from the frozen MML anchor coordinates (not the rounded report bbox), fails closed on
DEM/grid mismatch or clipped upstream area, and does not compute morphometry.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/chosica_2015_quirio_outlet_resolution_contract_v0_1.json"
REGISTRY = ROOT / "config/chosica_2015_outlet_freeze_registry_v0_1.json"
CANDIDATE = ROOT / "site/data/validation/chosica_2015_quirio_outlet_candidate.json"
DEFAULT_REPORT = ROOT / "artifacts/chosica_2015_quirio_catchment_report.json"
DEFAULT_GEOJSON = ROOT / "artifacts/chosica_2015_quirio_catchment.geojson"
DST_CRS = "EPSG:32718"
TARGET_RESOLUTION_M = 30.0
D8_DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
D8_STEPS = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tile_name(lat: float, lon: float) -> str:
    lat0, lon0 = math.floor(lat), math.floor(lon)
    latp = ("N" if lat0 >= 0 else "S") + f"{abs(lat0):02d}"
    lonp = ("E" if lon0 >= 0 else "W") + f"{abs(lon0):03d}"
    return f"Copernicus_DSM_COG_10_{latp}_00_{lonp}_00_DEM"


def relevant_tiles(xmin: float, ymin: float, xmax: float, ymax: float) -> Iterable[tuple[int, int]]:
    for lat0 in range(math.floor(ymin), math.floor(ymax - 1e-12) + 1):
        for lon0 in range(math.floor(xmin), math.floor(xmax - 1e-12) + 1):
            yield lat0, lon0


def download_dem_crop(td: Path, bbox: tuple[float, float, float, float]) -> Path:
    srcs = []
    try:
        for lat0, lon0 in relevant_tiles(*bbox):
            name = tile_name(float(lat0), float(lon0))
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
            path = td / f"{name}.tif"
            r = requests.get(url, timeout=(20, 180))
            r.raise_for_status()
            path.write_bytes(r.content)
            srcs.append(rasterio.open(path))
        if not srcs:
            raise RuntimeError("No Copernicus DEM tiles resolved")
        mosaic, src_transform = merge(srcs, bounds=bbox)
        src_profile = srcs[0].profile.copy()
        src_crs = srcs[0].crs
        for src in srcs:
            src.close()
        src_h, src_w = mosaic.shape[1], mosaic.shape[2]
        left, bottom, right, top = array_bounds(src_h, src_w, src_transform)
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src_crs, DST_CRS, src_w, src_h, left, bottom, right, top,
            resolution=TARGET_RESOLUTION_M,
        )
        src_nodata = src_profile.get("nodata")
        dst_nodata = -9999.0 if src_nodata is None else float(src_nodata)
        dst = np.full((dst_h, dst_w), dst_nodata, dtype="float32")
        reproject(
            source=mosaic[0], destination=dst,
            src_transform=src_transform, src_crs=src_crs, src_nodata=src_nodata,
            dst_transform=dst_transform, dst_crs=DST_CRS, dst_nodata=dst_nodata,
            resampling=Resampling.bilinear,
        )
        out = td / "chosica_quirio_rimac_dem_utm18s_30m.tif"
        profile = src_profile.copy()
        profile.update(
            driver="GTiff", width=dst_w, height=dst_h, count=1, dtype="float32",
            crs=DST_CRS, transform=dst_transform, nodata=dst_nodata, compress="deflate",
        )
        with rasterio.open(out, "w", **profile) as ds:
            ds.write(dst, 1)
        return out
    finally:
        for src in srcs:
            try:
                src.close()
            except Exception:
                pass


def upstream_mask(fdir: np.ndarray, outlet: tuple[int, int]) -> np.ndarray:
    rows, cols = fdir.shape
    n = rows * cols
    upstream = [[] for _ in range(n)]
    for r in range(rows):
        for c in range(cols):
            step = D8_STEPS.get(int(fdir[r, c]))
            if step is None:
                continue
            nr, nc = r + step[0], c + step[1]
            if 0 <= nr < rows and 0 <= nc < cols:
                upstream[nr * cols + nc].append(r * cols + c)
    out_idx = outlet[0] * cols + outlet[1]
    seen = np.zeros(n, dtype=bool)
    seen[out_idx] = True
    q = deque([out_idx])
    while q:
        cur = q.popleft()
        for src in upstream[cur]:
            if not seen[src]:
                seen[src] = True
                q.append(src)
    return seen.reshape((rows, cols))


def exact_frozen_bbox(contract: dict) -> tuple[float, float, float, float]:
    pts = contract["static_source"]["points"]
    xy = [
        (float(pts["rimac_upstream_bridge_r4"]["easting_m"]), float(pts["rimac_upstream_bridge_r4"]["northing_m"])),
        (float(pts["quirio_r8"]["easting_m"]), float(pts["quirio_r8"]["northing_m"])),
        (float(pts["rimac_downstream_bridge_r9"]["easting_m"]), float(pts["rimac_downstream_bridge_r9"]["northing_m"])),
    ]
    to_geo = Transformer.from_crs(DST_CRS, "EPSG:4326", always_xy=True)
    ll = [to_geo.transform(x, y) for x, y in xy]
    lons = [p[0] for p in ll]
    lats = [p[1] for p in ll]
    margin_deg = 0.05
    return (min(lons) - margin_deg, min(lats) - margin_deg, max(lons) + margin_deg, max(lats) + margin_deg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    args = ap.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.geojson.parent.mkdir(parents=True, exist_ok=True)

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    guards = registry["guards"]
    assert guards == {"RESEARCH_ONLY": True, "TEST_ONLY": True, "production_use": False, "production_ready": False, "operational_alerting_enabled": False}
    frozen = registry["targets"]["quirio"]
    assert frozen["outlet_status"] == "FROZEN"
    assert registry["batch_gate"]["batch_morphometry_allowed"] is False
    assert registry["batch_gate"]["unblind_allowed"] is False
    assert candidate["outcome_evidence_read"] is False
    assert candidate["a6680_numeric_reference_read"] is False
    assert candidate["post_anchor_predictor_read"] is False
    assert candidate["freeze_eligible"] is True
    assert candidate["contract_sha256"] == sha256_path(CONTRACT)

    bbox = exact_frozen_bbox(contract)
    rounded_bbox = [round(v, 8) for v in bbox]
    if rounded_bbox != candidate["dem_bbox_wgs84"]:
        raise RuntimeError("Frozen-anchor bbox no longer agrees with persisted candidate locator")

    report = {
        "schema_version": "0.1",
        "batch_id": registry["batch_id"],
        "target_id": "quirio",
        "status": "PENDING",
        "guards": guards,
        "geometry_only": True,
        "morphometry_computed": False,
        "outcome_evidence_read": False,
        "a6680_numeric_reference_read": False,
        "post_anchor_predictor_read": False,
        "outlet_registry_sha256": sha256_path(REGISTRY),
        "candidate_sha256": sha256_path(CANDIDATE),
        "method_contract_sha256": sha256_path(CONTRACT),
        "delineator_sha256": sha256_path(Path(__file__)),
        "analysis_crs": DST_CRS,
        "target_resolution_m": TARGET_RESOLUTION_M,
        "dem_bbox_wgs84": rounded_bbox,
        "dem_bbox_reconstruction": "EXACT_FROM_FROZEN_MML_UTM_ANCHORS_PLUS_0.05_DEG_MARGIN",
    }

    with tempfile.TemporaryDirectory(prefix="irfen_quirio_catchment_") as raw_td:
        td = Path(raw_td)
        dem_path = download_dem_crop(td, bbox)
        dem_hash = sha256_path(dem_path)
        report["dem_utm_sha256"] = dem_hash
        report["expected_dem_utm_sha256"] = candidate["dem_utm_sha256"]
        if dem_hash != candidate["dem_utm_sha256"]:
            report["status"] = "FAIL_CLOSED_DEM_RECONSTRUCTION_HASH_MISMATCH"
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return 2

        with rasterio.open(dem_path) as ds:
            transform = ds.transform
        outlet = frozen["accepted_outlet"]
        row, col = int(outlet["row"]), int(outlet["col"])
        x, y = rasterio.transform.xy(transform, row, col, offset="center")
        if abs(float(x) - float(outlet["x_m"])) > 0.01 or abs(float(y) - float(outlet["y_m"])) > 0.01:
            report["status"] = "FAIL_CLOSED_FROZEN_OUTLET_GRID_MISMATCH"
            report["reconstructed_cell_center_m"] = [float(x), float(y)]
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return 3

        grid = Grid.from_raster(str(dem_path))
        dem = grid.read_raster(str(dem_path))
        dem = grid.fill_pits(dem)
        dem = grid.fill_depressions(dem)
        dem = grid.resolve_flats(dem)
        fdir = np.asarray(grid.flowdir(dem, dirmap=D8_DIRMAP))
        mask = upstream_mask(fdir, (row, col))
        boundary_touch = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
        report["catchment_touches_dem_boundary"] = boundary_touch
        if boundary_touch:
            report["status"] = "FAIL_CLOSED_CATCHMENT_CLIPPED_BY_DEM_BBOX"
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return 4

        geoms = [shape(g) for g, value in shapes(mask.astype("uint8"), mask=mask, transform=transform) if int(value) == 1]
        if not geoms:
            raise RuntimeError("Catchment polygonization produced no geometry")
        geom_utm = unary_union(geoms)
        geom_wgs84 = shp_transform(Transformer.from_crs(DST_CRS, "EPSG:4326", always_xy=True).transform, geom_utm)
        feature = {
            "type": "Feature",
            "properties": {
                "batch_id": registry["batch_id"], "target_id": "quirio",
                "geometry_status": "PREUNBLIND_D8_CANDIDATE",
                "RESEARCH_ONLY": True, "TEST_ONLY": True,
                "production_use": False, "production_ready": False,
                "operational_alerting_enabled": False
            },
            "geometry": mapping(geom_wgs84),
        }
        args.geojson.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        report["geometry_geojson_sha256"] = sha256_path(args.geojson)
        report["status"] = "PASS_QUIRIO_D8_CATCHMENT_CANDIDATE"
        report["freeze_eligible"] = True

    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
