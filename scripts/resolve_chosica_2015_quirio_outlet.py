#!/usr/bin/env python3
"""Resolve a pre-unblind Quirio outlet candidate from MML 2013 static anchors + D8 only.

The preregistered method reconstructs the local Rimac mainstem reach from MML R4 to R9,
then takes the first intersection of a downstream D8 trace from MML R8 (Quirio) with that
reach. It never reads 2015 activation/damage outcomes, A6680 numeric morphometry,
post-anchor rainfall, or post-event response layers.
"""
from __future__ import annotations

import argparse
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
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import requests

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/chosica_2015_quirio_outlet_resolution_contract_v0_1.json"
DEFAULT_REPORT = ROOT / "artifacts/chosica_2015_quirio_outlet_report.json"
DST_CRS = "EPSG:32718"
TARGET_RESOLUTION_M = 30.0
D8_DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
D8_STEPS = {
    64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1),
    4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1),
}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tile_name(lat: float, lon: float) -> str:
    lat0 = math.floor(lat)
    lon0 = math.floor(lon)
    latp = ("N" if lat0 >= 0 else "S") + f"{abs(lat0):02d}"
    lonp = ("E" if lon0 >= 0 else "W") + f"{abs(lon0):03d}"
    return f"Copernicus_DSM_COG_10_{latp}_00_{lonp}_00_DEM"


def tile_url(lat: float, lon: float) -> str:
    name = tile_name(lat, lon)
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"


def relevant_tiles(xmin: float, ymin: float, xmax: float, ymax: float) -> Iterable[tuple[int, int]]:
    for lat0 in range(math.floor(ymin), math.floor(ymax - 1e-12) + 1):
        for lon0 in range(math.floor(xmin), math.floor(xmax - 1e-12) + 1):
            yield lat0, lon0


def download_dem_crop(td: Path, bbox: tuple[float, float, float, float]) -> tuple[Path, list[dict]]:
    srcs = []
    provenance: list[dict] = []
    try:
        for lat0, lon0 in relevant_tiles(*bbox):
            url = tile_url(float(lat0), float(lon0))
            name = tile_name(float(lat0), float(lon0))
            path = td / f"{name}.tif"
            r = requests.get(url, timeout=(20, 180))
            r.raise_for_status()
            path.write_bytes(r.content)
            provenance.append({"url": url, "sha256": sha256_path(path), "bytes": path.stat().st_size})
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
        return out, provenance
    finally:
        for src in srcs:
            try:
                src.close()
            except Exception:
                pass


def cell_center(transform, row: int, col: int) -> tuple[float, float]:
    x, y = rasterio.transform.xy(transform, row, col, offset="center")
    return float(x), float(y)


def source_cells(transform, width: int, height: int, x: float, y: float) -> list[tuple[int, int]]:
    inv = ~transform
    col_f, row_f = inv * (x, y)
    row0, col0 = int(math.floor(row_f)), int(math.floor(col_f))
    rows = {row0}
    cols = {col0}
    eps = 1e-6
    if abs(row_f - round(row_f)) <= eps:
        rows.add(row0 - 1)
    if abs(col_f - round(col_f)) <= eps:
        cols.add(col0 - 1)
    return sorted((r, c) for r in rows for c in cols if 0 <= r < height and 0 <= c < width)


def trace_d8(fdir: np.ndarray, start: tuple[int, int]) -> list[tuple[int, int]]:
    rows, cols = fdir.shape
    current = start
    trace: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for _ in range(rows * cols):
        if current in seen:
            break
        seen.add(current)
        trace.append(current)
        r, c = current
        step = D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            break
        nr, nc = r + step[0], c + step[1]
        if not (0 <= nr < rows and 0 <= nc < cols):
            break
        current = (nr, nc)
    return trace


def load_contract() -> tuple[dict, dict, dict, dict]:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    g = data["guards"]
    assert g["RESEARCH_ONLY"] is True and g["TEST_ONLY"] is True
    assert g["production_use"] is False and g["production_ready"] is False
    assert g["operational_alerting_enabled"] is False
    m = data["predeclared_resolution_method"]
    assert m["selection_used_basin_area"] is False
    assert m["selection_used_channel_length"] is False
    assert m["selection_used_rainfall"] is False
    assert m["selection_used_activation_or_damage"] is False
    assert m["selection_used_a6680_numeric_morphometry"] is False
    pts = data["static_source"]["points"]
    return data, pts["rimac_upstream_bridge_r4"], pts["quirio_r8"], pts["rimac_downstream_bridge_r9"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)

    contract, r4, r8, r9 = load_contract()
    report = {
        "schema_version": "0.1",
        "batch_id": contract["batch_id"],
        "target_id": "quirio",
        "method": contract["predeclared_resolution_method"]["name"],
        "guards": contract["guards"],
        "outcome_evidence_read": False,
        "a6680_numeric_reference_read": False,
        "post_anchor_predictor_read": False,
        "source_anchor_id": contract["static_source"]["source_id"],
        "contract_sha256": sha256_path(CONTRACT),
        "resolver_sha256": sha256_path(Path(__file__)),
        "dem_source": contract["dem"]["source"],
        "analysis_crs": DST_CRS,
        "target_resolution_m": TARGET_RESOLUTION_M,
        "accepted_outlet": None,
        "freeze_eligible": False,
    }

    to_geo = Transformer.from_crs(DST_CRS, "EPSG:4326", always_xy=True)
    src_xy = [
        (float(r4["easting_m"]), float(r4["northing_m"])),
        (float(r8["easting_m"]), float(r8["northing_m"])),
        (float(r9["easting_m"]), float(r9["northing_m"])),
    ]
    src_ll = [to_geo.transform(x, y) for x, y in src_xy]
    lons = [p[0] for p in src_ll]
    lats = [p[1] for p in src_ll]
    margin_deg = 0.05
    bbox = (min(lons) - margin_deg, min(lats) - margin_deg, max(lons) + margin_deg, max(lats) + margin_deg)
    report["dem_bbox_wgs84"] = [round(float(v), 8) for v in bbox]

    with tempfile.TemporaryDirectory(prefix="irfen_quirio_d8_") as raw_td:
        td = Path(raw_td)
        dem_path, provenance = download_dem_crop(td, bbox)
        report["dem_tiles"] = provenance
        report["dem_utm_sha256"] = sha256_path(dem_path)
        with rasterio.open(dem_path) as ds:
            transform, width, height = ds.transform, ds.width, ds.height
            cell_x, cell_y = abs(float(transform.a)), abs(float(transform.e))

        grid = Grid.from_raster(str(dem_path))
        dem = grid.read_raster(str(dem_path))
        dem = grid.fill_pits(dem)
        dem = grid.fill_depressions(dem)
        dem = grid.resolve_flats(dem)
        fdir = np.asarray(grid.flowdir(dem, dirmap=D8_DIRMAP))

        r4_xy, r8_xy, r9_xy = src_xy
        r4_starts = source_cells(transform, width, height, *r4_xy)
        r8_starts = source_cells(transform, width, height, *r8_xy)
        report["r4_source_cells"] = [{"row": r, "col": c} for r, c in r4_starts]
        report["r8_source_cells"] = [{"row": r, "col": c} for r, c in r8_starts]
        identity_tolerance_m = 2.0 * math.hypot(cell_x, cell_y)
        report["cell_size_m"] = [cell_x, cell_y]
        report["identity_tolerance_m"] = round(identity_tolerance_m, 6)

        rimac_paths: list[list[tuple[int, int]]] = []
        rimac_diagnostics: list[dict] = []
        for start in r4_starts:
            trace = trace_d8(fdir, start)
            if not trace:
                rimac_diagnostics.append({"start": list(start), "status": "NO_TRACE"})
                continue
            centers = np.array([cell_center(transform, r, c) for r, c in trace], dtype=float)
            d2 = (centers[:, 0] - r9_xy[0]) ** 2 + (centers[:, 1] - r9_xy[1]) ** 2
            idx = int(np.argmin(d2))
            nearest_dist = float(math.sqrt(float(d2[idx])))
            start_dist = float(math.hypot(centers[0, 0] - r9_xy[0], centers[0, 1] - r9_xy[1]))
            progresses = nearest_dist < start_dist
            passes = progresses and nearest_dist <= identity_tolerance_m
            rimac_diagnostics.append({
                "start": list(start),
                "trace_cells": len(trace),
                "nearest_r9_row": trace[idx][0],
                "nearest_r9_col": trace[idx][1],
                "nearest_r9_distance_m": round(nearest_dist, 3),
                "start_to_r9_distance_m": round(start_dist, 3),
                "progresses_toward_r9": progresses,
                "within_identity_tolerance": nearest_dist <= identity_tolerance_m,
            })
            if passes:
                rimac_paths.append(trace[: idx + 1])
        report["rimac_path_diagnostics"] = rimac_diagnostics

        if not r4_starts or len(rimac_paths) != len(r4_starts):
            report["status"] = "PENDING_REVIEW_R4_TO_R9_MAINSTEM_NOT_REPRODUCED"
        elif not r8_starts:
            report["status"] = "PENDING_REVIEW_NO_QUIRIO_R8_SOURCE_CELL"
        else:
            intersections: list[tuple[int, int]] = []
            intersection_diags: list[dict] = []
            for qstart in r8_starts:
                qtrace = trace_d8(fdir, qstart)
                if not qtrace:
                    intersection_diags.append({"quirio_start": list(qstart), "status": "NO_TRACE"})
                    continue
                for pidx, rimac_path in enumerate(rimac_paths):
                    path_cells = set(rimac_path)
                    first = next((cell for cell in qtrace if cell in path_cells), None)
                    if first is None:
                        intersection_diags.append({
                            "quirio_start": list(qstart), "rimac_path_index": pidx,
                            "status": "NO_INTERSECTION",
                        })
                    else:
                        intersections.append(first)
                        intersection_diags.append({
                            "quirio_start": list(qstart), "rimac_path_index": pidx,
                            "status": "FIRST_INTERSECTION_FOUND", "row": first[0], "col": first[1],
                        })
            report["intersection_diagnostics"] = intersection_diags
            expected = len(r8_starts) * len(rimac_paths)
            unique = sorted(set(intersections))
            report["first_intersection_cells_unique"] = [{"row": r, "col": c} for r, c in unique]
            if len(intersections) != expected:
                report["status"] = "PENDING_REVIEW_MISSING_QUIRIO_RIMAC_INTERSECTION"
            elif len(unique) != 1:
                report["status"] = "PENDING_REVIEW_NONCONVERGENT_QUIRIO_OUTLET"
            else:
                selected = unique[0]
                x, y = cell_center(transform, *selected)
                lon, lat = to_geo.transform(x, y)
                report["accepted_outlet"] = {
                    "row": selected[0], "col": selected[1],
                    "x_m": round(x, 3), "y_m": round(y, 3),
                    "lon": round(float(lon), 8), "lat": round(float(lat), 8),
                }
                report["status"] = "PASS_QUIRIO_D8_MAINSTEM_INTERSECTION_CANDIDATE"
                report["freeze_eligible"] = True

    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
