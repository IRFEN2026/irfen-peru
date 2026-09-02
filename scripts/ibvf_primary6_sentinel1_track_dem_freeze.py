#!/usr/bin/env python3
"""Freeze/reproduce one geometry-derived PRIMARY6 Sentinel-1 external DEM.

RESEARCH_ONLY / TEST_ONLY. This script reads only the frozen unit geometry and
static DEM/geoid resources. It never reads Sentinel-1 response pixels, rainfall
magnitudes, territorial outcomes, event dates, or case/control roles.

The scientific rule is frozen in ibvf_primary6_sentinel1_r2r4_execution_contract_v01.json:
buffer the frozen geometry by 1500 m in its frozen UTM CRS, transform the
buffered envelope to WGS84, include every intersecting Copernicus GLO-30
one-degree tile, then convert EGM2008 orthometric heights to WGS84 ellipsoidal
heights at the original merged GLO-30 pixel centers without horizontal
resampling.
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
import pyproj
import rasterio
import requests
from pyproj import Transformer
from rasterio.merge import merge as rio_merge
from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union

UA = "IRFEN-IBVF/0.4 RESEARCH_ONLY TEST_ONLY"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def download(url: str, path: Path) -> dict[str, Any]:
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(url, stream=True, timeout=(30, 900), headers={"User-Agent": UA}) as r:
            r.raise_for_status()
            with path.open("wb") as fh:
                for chunk in r.iter_content(4 * 1024 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
        return {"status": "SUCCESS", "url": url, "sha256": h.hexdigest(), "bytes": n}
    except Exception as exc:
        if path.exists():
            path.unlink()
        return {
            "status": "TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING",
            "url": url,
            "error_class": type(exc).__name__,
            "message": str(exc)[:1000],
            "bytes_received": n,
        }


def assert_contract(c: dict[str, Any]) -> None:
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["test_only"] is True
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["uses_operational_event_none_labels"] is False
    assert c["territorial_activation_evidence_blinded"] is True
    assert c["decision_timing"]["territorial_outcomes_used"] is False
    assert c["decision_timing"]["sar_response_used"] is False
    assert c["track_dem_rule"]["geometry_only"] is True
    assert c["track_dem_rule"]["buffer_m"] == 1500.0
    assert c["track_dem_rule"]["horizontal_resampling_for_vertical_conversion"] is False
    assert c["track_dem_rule"]["case_specific_height_adjustment_allowed"] is False


def selected_geometries(doc: dict[str, Any], selector: dict[str, Any] | None) -> list[Any]:
    if doc.get("type") == "Feature":
        features = [doc]
    elif doc.get("type") == "FeatureCollection":
        features = doc.get("features") or []
    else:
        raise ValueError("geometry file must be GeoJSON Feature or FeatureCollection")
    if selector is not None:
        prop = selector["property"]
        value = selector["value"]
        features = [f for f in features if (f.get("properties") or {}).get(prop) == value]
    if not features:
        raise ValueError("frozen geometry selector returned no features")
    geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:
        raise ValueError("selected frozen geometry has no shapes")
    return geoms


def tile_id(lat_floor: int, lon_floor: int) -> str:
    lat = f"N{lat_floor:02d}" if lat_floor >= 0 else f"S{abs(lat_floor):02d}"
    lon = f"E{lon_floor:03d}" if lon_floor >= 0 else f"W{abs(lon_floor):03d}"
    return f"Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM"


def tile_inventory(bbox: list[float]) -> list[dict[str, Any]]:
    xmin, ymin, xmax, ymax = bbox
    eps = 1e-12
    lon0, lon1 = math.floor(xmin), math.floor(xmax - eps)
    lat0, lat1 = math.floor(ymin), math.floor(ymax - eps)
    out = []
    for lat in range(lat0, lat1 + 1):
        for lon in range(lon0, lon1 + 1):
            item = tile_id(lat, lon)
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{item}/{item}.tif"
            out.append({"item_id": item, "url": url, "lat_floor": lat, "lon_floor": lon})
    if not out:
        raise ValueError("no GLO-30 tiles selected")
    return out


def geometry_buffered_bbox(geometry_path: Path, selector: dict[str, Any] | None, utm_crs: str, buffer_m: float) -> tuple[list[float], int]:
    doc = load(geometry_path)
    geoms = selected_geometries(doc, selector)
    merged = unary_union(geoms)
    if merged.is_empty or not merged.is_valid:
        if merged.is_empty:
            raise ValueError("selected frozen geometry is empty")
        merged = merged.buffer(0)
        if merged.is_empty or not merged.is_valid:
            raise ValueError("selected frozen geometry is invalid")
    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    to_wgs = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)
    g_utm = shp_transform(to_utm.transform, merged)
    buffered = g_utm.buffer(buffer_m)
    buffered_wgs = shp_transform(to_wgs.transform, buffered)
    xmin, ymin, xmax, ymax = [float(x) for x in buffered_wgs.bounds]
    if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
        raise ValueError(f"invalid buffered WGS84 bbox {(xmin,ymin,xmax,ymax)}")
    return [xmin, ymin, xmax, ymax], len(geoms)


def compare_expected(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    keys = ["unit_id", "geometry_file_sha256", "geometry_selector", "target_projection", "buffer_m", "buffered_bbox_wgs84"]
    for key in keys:
        if actual[key] != expected[key]:
            raise ValueError(f"reproduction mismatch {key}: {actual[key]!r} != {expected[key]!r}")
    if actual["vertical_grid"]["sha256"] != expected["vertical_grid"]["sha256"] or actual["vertical_grid"]["bytes"] != expected["vertical_grid"]["bytes"]:
        raise ValueError("reproduction mismatch vertical grid identity")
    a_tiles = [(x["item_id"], x["url"], x["sha256"], x["bytes"]) for x in actual["glo30_tiles"]]
    e_tiles = [(x["item_id"], x["url"], x["sha256"], x["bytes"]) for x in expected["glo30_tiles"]]
    if a_tiles != e_tiles:
        raise ValueError("reproduction mismatch GLO-30 tile identity")
    for key in ("sha256", "bytes", "shape", "transform", "horizontal_crs", "vertical_semantics", "valid_pixel_count"):
        if actual["output_dem"][key] != expected["output_dem"][key]:
            raise ValueError(f"reproduction mismatch output_dem.{key}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--unit-id", required=True)
    ap.add_argument("--output-dem", type=Path, required=True)
    ap.add_argument("--output-report", type=Path, required=True)
    ap.add_argument("--expected-report", type=Path)
    args = ap.parse_args()

    c = load(args.contract)
    assert_contract(c)
    if args.unit_id not in c["unit_geometry_and_projection"]:
        raise SystemExit(f"unit not frozen in contract: {args.unit_id}")
    unit = c["unit_geometry_and_projection"][args.unit_id]
    geometry_path = Path(unit["geometry_path"])
    if not geometry_path.is_file():
        raise SystemExit(f"frozen geometry absent: {geometry_path}")
    geom_sha, geom_bytes = sha256_file(geometry_path)
    selector = unit.get("geometry_selector")
    buffer_m = float(c["track_dem_rule"]["buffer_m"])
    bbox, selected_feature_count = geometry_buffered_bbox(
        geometry_path, selector, unit["target_projection"], buffer_m
    )
    inventory = tile_inventory(bbox)

    args.output_dem.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"ibvf-primary6-{args.unit_id}-dem-") as td_raw:
        td = Path(td_raw)
        tile_paths: list[Path] = []
        tile_reports: list[dict[str, Any]] = []
        transport_blocked = False
        for rec in inventory:
            dst = td / f"{rec['item_id']}.tif"
            dl = download(rec["url"], dst)
            row = {**rec, **dl}
            tile_reports.append(row)
            if dl["status"] != "SUCCESS":
                transport_blocked = True
            else:
                tile_paths.append(dst)

        grid_cfg = c["track_dem_rule"]["vertical_grid"]
        grid_path = td / Path(grid_cfg["url"]).name
        grid_dl = download(grid_cfg["url"], grid_path)
        if grid_dl["status"] != "SUCCESS":
            transport_blocked = True

        if transport_blocked:
            report = {
                "schema_version": "irfen-ibvf-primary6-sentinel1-track-dem-v0.1",
                "generated_at": now(),
                "unit_id": args.unit_id,
                "deployment_status": "RESEARCH_ONLY",
                "test_only": True,
                "production_use": False,
                "production_ready": False,
                "operational_alerting_enabled": False,
                "uses_operational_event_none_labels": False,
                "territorial_activation_evidence_blinded": True,
                "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
                "geometry_path": str(geometry_path),
                "geometry_file_sha256": geom_sha,
                "geometry_file_bytes": geom_bytes,
                "geometry_selector": selector,
                "selected_geometry_feature_count": selected_feature_count,
                "target_projection": unit["target_projection"],
                "buffer_m": buffer_m,
                "buffered_bbox_wgs84": bbox,
                "glo30_tiles": tile_reports,
                "vertical_grid": grid_dl,
                "r2_science_pixels_read": False,
                "territorial_outcomes_read": False,
                "case_control_role_assigned": False,
                "activation_inference_allowed": False,
                "status": "BLOCKED_TRANSPORT_UNKNOWN_NOT_MISSING",
            }
            args.output_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({"status": report["status"], "unit_id": args.unit_id}, sort_keys=True))
            return 2

        if grid_dl["sha256"] != grid_cfg["sha256"] or grid_dl["bytes"] != int(grid_cfg["bytes"]):
            raise RuntimeError("frozen EGM2008 grid identity mismatch")

        datasets = [rasterio.open(p) for p in tile_paths]
        try:
            for ds in datasets:
                if ds.crs is None or ds.crs.to_epsg() != 4326:
                    raise RuntimeError(f"unexpected GLO-30 CRS {ds.crs}")
            mosaic, tr = rio_merge(datasets, bounds=tuple(bbox), nodata=-9999.0, dtype="float64")
            z = mosaic[0].astype(np.float64)
            source_profile = datasets[0].profile.copy()
            source_nodata_values = [ds.nodata for ds in datasets]
        finally:
            for ds in datasets:
                ds.close()

        valid = np.isfinite(z) & (z != -9999.0)
        for nd in source_nodata_values:
            if nd is not None and np.isfinite(float(nd)):
                valid &= z != float(nd)
        input_valid = int(valid.sum())
        if input_valid == 0:
            raise RuntimeError("merged buffered DEM contains no valid pixels")

        pipeline = (
            f"+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad "
            f"+step +proj=vgridshift +grids={grid_path} +multiplier=1 "
            f"+step +proj=unitconvert +xy_in=rad +xy_out=deg"
        )
        pyproj.network.set_network_enabled(False)
        transformer = Transformer.from_pipeline(pipeline)
        out = np.full(z.shape, -9999.0, dtype=np.float32)
        corr_min = float("inf")
        corr_max = float("-inf")
        corr_sum = 0.0
        corr_n = 0
        max_xy_delta = 0.0
        cols = np.arange(z.shape[1], dtype=np.float64)
        for r0 in range(0, z.shape[0], 128):
            r1 = min(z.shape[0], r0 + 128)
            rows = np.arange(r0, r1, dtype=np.float64)
            cc, rr = np.meshgrid(cols, rows)
            xx = tr.c + (cc + 0.5) * tr.a + (rr + 0.5) * tr.b
            yy = tr.f + (cc + 0.5) * tr.d + (rr + 0.5) * tr.e
            vv = valid[r0:r1]
            if not vv.any():
                continue
            xin, yin, zin = xx[vv], yy[vv], z[r0:r1][vv]
            x2, y2, z2 = transformer.transform(xin, yin, zin, errcheck=True)
            x2 = np.asarray(x2)
            y2 = np.asarray(y2)
            z2 = np.asarray(z2)
            if not np.isfinite(z2).all():
                raise RuntimeError("non-finite ellipsoidal heights")
            max_xy_delta = max(max_xy_delta, float(np.max(np.maximum(np.abs(x2 - xin), np.abs(y2 - yin)))))
            correction = z2 - zin
            corr_min = min(corr_min, float(np.min(correction)))
            corr_max = max(corr_max, float(np.max(correction)))
            corr_sum += float(np.sum(correction))
            corr_n += int(correction.size)
            block = out[r0:r1]
            block[vv] = z2.astype(np.float32)
            out[r0:r1] = block

        if corr_n != input_valid:
            raise RuntimeError("vertical transform count mismatch")
        if corr_min < -150.0 or corr_max > 150.0:
            raise RuntimeError(f"vertical correction outside broad sanity range {corr_min},{corr_max}")
        if max_xy_delta > 1e-10:
            raise RuntimeError(f"vertical transform changed horizontal coordinates {max_xy_delta}")

        source_profile.update(
            driver="GTiff",
            height=out.shape[0],
            width=out.shape[1],
            transform=tr,
            crs="EPSG:4326",
            count=1,
            dtype="float32",
            nodata=-9999.0,
            compress="deflate",
            predictor=3,
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        with rasterio.open(args.output_dem, "w", **source_profile) as dst:
            dst.write(out, 1)
            dst.update_tags(
                IBVF_VERTICAL_SEMANTICS="WGS84_ELLIPSOIDAL_HEIGHT",
                IBVF_SOURCE_VERTICAL="EGM2008_EPSG3855",
                IBVF_RESEARCH_ONLY="true",
                IBVF_UNIT_ID=args.unit_id,
            )

        out_sha, out_bytes = sha256_file(args.output_dem)
        with rasterio.open(args.output_dem) as chk:
            zchk = chk.read(1)
            valid_out = np.isfinite(zchk) & (zchk != chk.nodata)
            output_valid = int(valid_out.sum())
            output_meta = {
                "sha256": out_sha,
                "bytes": out_bytes,
                "shape": [chk.height, chk.width],
                "transform": [float(x) for x in list(chk.transform)[:6]],
                "horizontal_crs": str(chk.crs),
                "vertical_semantics": "WGS84_ELLIPSOIDAL_HEIGHT",
                "valid_pixel_count": output_valid,
                "nodata_value": float(chk.nodata),
            }
        if output_valid != input_valid:
            raise RuntimeError("output valid pixel count changed")

        report = {
            "schema_version": "irfen-ibvf-primary6-sentinel1-track-dem-v0.1",
            "generated_at": now(),
            "unit_id": args.unit_id,
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "uses_operational_event_none_labels": False,
            "territorial_activation_evidence_blinded": True,
            "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
            "execution_contract_path": str(args.contract),
            "execution_contract_sha256": sha256_file(args.contract)[0],
            "geometry_path": str(geometry_path),
            "geometry_file_sha256": geom_sha,
            "geometry_file_bytes": geom_bytes,
            "geometry_selector": selector,
            "selected_geometry_feature_count": selected_feature_count,
            "target_projection": unit["target_projection"],
            "buffer_m": buffer_m,
            "buffered_bbox_wgs84": bbox,
            "glo30_tile_selection_rule": "EVERY_ONE_DEGREE_TILE_INTERSECTING_GEOMETRY_BUFFERED_BBOX_WGS84",
            "glo30_tiles": tile_reports,
            "vertical_grid": {
                "url": grid_cfg["url"],
                "sha256": grid_dl["sha256"],
                "bytes": grid_dl["bytes"],
            },
            "conversion": {
                "pipeline": pipeline.replace(str(grid_path), Path(grid_cfg["url"]).name),
                "pyproj_version": pyproj.__version__,
                "proj_version": pyproj.proj_version_str,
                "network_enabled": False,
                "horizontal_max_abs_delta_degrees": max_xy_delta,
                "geoid_correction_min_m": corr_min,
                "geoid_correction_max_m": corr_max,
                "geoid_correction_mean_m": corr_sum / corr_n,
                "case_specific_height_adjustment_used": False,
                "horizontal_resampling_for_vertical_conversion": False,
            },
            "output_dem": output_meta,
            "r2_science_pixels_read": False,
            "sar_response_used_for_dem_choice": False,
            "rainfall_magnitude_used_for_dem_choice": False,
            "territorial_outcomes_read": False,
            "known_event_dates_read": False,
            "case_control_role_assigned": False,
            "activation_inference_allowed": False,
            "modeling_allowed": False,
            "status": "PASS_TRACK_DEM_FROZEN_NO_R2_SCIENCE_VALUES",
        }

        if args.expected_report:
            expected = load(args.expected_report)
            compare_expected(report, expected)
            report["reproduction_against_archived_report"] = "PASS_EXACT_IDENTITIES"
            report["status"] = "PASS_TRACK_DEM_REPRODUCED_EXACTLY_R2_EXECUTION_ALLOWED_FOR_UNIT"

        args.output_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "unit_id": args.unit_id,
            "geometry_sha256": geom_sha,
            "tile_count": len(tile_reports),
            "output_dem_sha256": out_sha,
            "buffered_bbox_wgs84": bbox,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
