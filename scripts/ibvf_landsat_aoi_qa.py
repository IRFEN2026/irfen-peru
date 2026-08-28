#!/usr/bin/env python3
"""AOI-level Landsat Collection 2 Level-2 QA for IRFEN IBVF.

RESEARCH_ONLY / TEST_ONLY. This tool reports diagnostic QA coverage inside an
explicit AOI. It does not classify activation, risk, priority, or operational
status and it does not use global scene cloud cover as an acceptance rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.mask import mask
from rasterio.warp import transform_geom


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def pct(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 3) if den else None


def select_geometry(path: Path, prop: str, value: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features") if data.get("type") == "FeatureCollection" else [data]
    matches = [f for f in features if (f.get("properties") or {}).get(prop) == value]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one AOI feature for {prop}={value!r}; got {len(matches)}")
    geom = matches[0].get("geometry")
    if not geom:
        raise ValueError("Selected AOI feature has no geometry")
    return geom


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def download(uri: str, destination: Path, timeout: int = 120) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = s3_to_https(uri)
    req = Request(url, headers={"User-Agent": "IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"})
    try:
        with urlopen(req, timeout=timeout) as r, destination.open("wb") as f:
            shutil.copyfileobj(r, f, length=1024 * 1024)
        return {
            "transport_status": "SUCCESS",
            "source_uri": uri,
            "resolved_url": url,
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
        }
    except Exception as exc:
        if destination.exists():
            destination.unlink()
        return {
            "transport_status": "TRANSPORT_BLOCKED",
            "source_uri": uri,
            "resolved_url": url,
            "error": repr(exc),
        }


def find_landsat_items(inventory: dict[str, Any], dates: set[str]) -> list[dict[str, Any]]:
    coll = next((c for c in inventory.get("collections", []) if c.get("collection") == "landsat-c2-l2"), None)
    if not coll or coll.get("transport_status") != "SUCCESS":
        raise RuntimeError("Landsat inventory is not transport-successful")
    out = []
    for item in coll.get("items", []):
        dt = str(item.get("datetime") or "")
        if dt[:10] in dates:
            out.append(item)
    return sorted(out, key=lambda x: x.get("datetime") or "")


def read_masked(path: Path, geom_wgs84: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, Any, Any]:
    with rasterio.open(path) as ds:
        geom = transform_geom("EPSG:4326", ds.crs, geom_wgs84, precision=6)
        arr, transform = mask(ds, [geom], crop=True, filled=False, indexes=1)
        data = np.asarray(arr.data)
        outside_or_nodata = np.asarray(arr.mask)
        if outside_or_nodata.ndim == 0:
            outside_or_nodata = np.full(data.shape, bool(outside_or_nodata), dtype=bool)
        inside = geometry_mask([geom], out_shape=data.shape, transform=transform, invert=True)
        return data, inside, transform, ds.crs


def ensure_aligned(reference: tuple[np.ndarray, np.ndarray, Any, Any], other: tuple[np.ndarray, np.ndarray, Any, Any]) -> None:
    a, inside_a, tx_a, crs_a = reference
    b, inside_b, tx_b, crs_b = other
    if a.shape != b.shape or inside_a.shape != inside_b.shape or tx_a != tx_b or crs_a != crs_b:
        raise ValueError("QA rasters are not aligned after AOI crop")


def analyze_scene(item: dict[str, Any], geom: dict[str, Any], download_dir: Path) -> dict[str, Any]:
    required = ["qa_pixel", "qa_radsat", "qa_aerosol"]
    assets = item.get("assets") or {}
    missing_assets = [k for k in required if not (assets.get(k) or {}).get("href")]
    base = {
        "item_id": item.get("id"),
        "scene_id": item.get("scene_id"),
        "datetime": item.get("datetime"),
        "wrs_path": item.get("wrs_path"),
        "wrs_row": item.get("wrs_row"),
        "cloud_cover_global_pct_metadata_only": item.get("cloud_cover_global_pct"),
        "required_qa_assets": required,
        "missing_qa_assets": missing_assets,
    }
    if missing_assets:
        return {**base, "qa_status": "UNKNOWN_MISSING_ASSET_REFERENCE"}

    local: dict[str, Path] = {}
    acquisition: dict[str, Any] = {}
    for key in required:
        href = assets[key]["href"]
        dest = download_dir / f"{item['id']}_{key}.tif"
        acquisition[key] = download(href, dest)
        if acquisition[key]["transport_status"] == "SUCCESS":
            local[key] = dest
    base["asset_acquisition"] = acquisition
    if len(local) != len(required):
        return {**base, "qa_status": "UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING"}

    qpix = read_masked(local["qa_pixel"], geom)
    qrad = read_masked(local["qa_radsat"], geom)
    qaer = read_masked(local["qa_aerosol"], geom)
    ensure_aligned(qpix, qrad)
    ensure_aligned(qpix, qaer)

    pixel, inside, _, _ = qpix
    radsat = qrad[0]
    aerosol = qaer[0]

    aoi_pixels = int(inside.sum())
    fill = (pixel & 1) != 0
    data_domain = inside & ~fill
    data_pixels = int(data_domain.sum())

    adverse_mask = 0
    for bit in (1, 2, 3, 4, 5):
        adverse_mask |= 1 << bit
    strict_clear = data_domain & ((pixel & adverse_mask) == 0)
    water = data_domain & ((pixel & (1 << 7)) != 0)
    radsat_nonzero = data_domain & (radsat != 0)

    aerosol_valid = data_domain & ((aerosol & (1 << 1)) != 0)
    aerosol_level = (aerosol >> 6) & 0b11
    aerosol_high = aerosol_valid & (aerosol_level == 3)
    aerosol_medium = aerosol_valid & (aerosol_level == 2)
    aerosol_low_or_clim = aerosol_valid & (aerosol_level <= 1)
    combined_proxy = strict_clear & (radsat == 0) & aerosol_valid & (aerosol_level <= 2)

    metrics = {
        "aoi_pixels": aoi_pixels,
        "data_coverage_pixels": data_pixels,
        "data_coverage_pct": pct(data_pixels, aoi_pixels),
        "strict_clear_pixels": int(strict_clear.sum()),
        "strict_clear_pct_of_data": pct(int(strict_clear.sum()), data_pixels),
        "water_pct_of_data": pct(int(water.sum()), data_pixels),
        "radsat_nonzero_pct_of_data": pct(int(radsat_nonzero.sum()), data_pixels),
        "aerosol_valid_pct_of_data": pct(int(aerosol_valid.sum()), data_pixels),
        "aerosol_high_pct_of_data": pct(int(aerosol_high.sum()), data_pixels),
        "aerosol_medium_pct_of_data": pct(int(aerosol_medium.sum()), data_pixels),
        "aerosol_low_or_climatology_pct_of_data": pct(int(aerosol_low_or_clim.sum()), data_pixels),
        "combined_qa_usable_proxy_pct_of_data": pct(int(combined_proxy.sum()), data_pixels),
    }
    return {
        **base,
        "qa_status": "MEASURED_REFERENCE_AOI_NOT_FINAL_IBVF_BASIN",
        "qa_rule": {
            "global_cloud_cover_used_for_acceptance": False,
            "strict_clear_excludes_qa_pixel_bits": [0, 1, 2, 3, 4, 5],
            "combined_proxy_is_acceptance_threshold": False,
            "note": "Metrics are diagnostics only until the final IBVF basin/AOI and acceptance rule are frozen.",
        },
        "metrics": metrics,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--geojson", required=True, type=Path)
    ap.add_argument("--selector-property", required=True)
    ap.add_argument("--selector-value", required=True)
    ap.add_argument("--date", action="append", required=True)
    ap.add_argument("--download-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    geom = select_geometry(args.geojson, args.selector_property, args.selector_value)
    dates = set(args.date)
    items = find_landsat_items(inventory, dates)

    report = {
        "schema_version": "irfen-ibvf-landsat-aoi-qa-v0.1",
        "generated_at": utc_now(),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "source_inventory_manifest_sha256": inventory.get("manifest_sha256"),
        "aoi_source": str(args.geojson),
        "aoi_selector": {"property": args.selector_property, "value": args.selector_value},
        "aoi_semantics": "EXISTING_REVIEW_ONLY_REFERENCE_GEOMETRY_NOT_FINAL_IBVF_BASIN",
        "requested_dates": sorted(dates),
        "matched_item_count": len(items),
        "scenes": [analyze_scene(item, geom, args.download_dir) for item in items],
    }
    if len(items) != len(dates):
        report["completeness_status"] = "INCOMPLETE_EXPECTED_ONE_ITEM_PER_REQUESTED_DATE"
    elif all(s.get("qa_status", "").startswith("MEASURED_") for s in report["scenes"]):
        report["completeness_status"] = "MEASURED_ALL_REQUESTED_DATES_REFERENCE_AOI"
    else:
        report["completeness_status"] = "UNKNOWN_TRANSPORT_OR_ASSET_BLOCK"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"matched": len(items), "status": report["completeness_status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
