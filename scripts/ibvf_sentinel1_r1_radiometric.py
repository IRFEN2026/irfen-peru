#!/usr/bin/env python3
"""IBVF Sentinel-1 A4-R1 native radiometric processing for Cashahuacra.

RESEARCH_ONLY / TEST_ONLY. This stage verifies the exact frozen Sentinel-1
assets by SHA-256, parses calibration/noise/product annotation XML, derives a
deterministic native-pixel window from the blinded basin geometry, and computes
noise-corrected calibrated sigma0 diagnostics independently for each date.

It performs NO pre/post comparison, NO terrain correction, NO common-support
inference, and NO activation/risk classification. Transport failures are
UNKNOWN/TRANSPORT_BLOCKED, never MISSING.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import numpy as np
import rasterio
import requests
import xml.etree.ElementTree as ET
from rasterio.windows import Window

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
ASSET_KEYS = ("schema-calibration-vv", "schema-noise-vv", "schema-product-vv", "vv")
USER_AGENT = "IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def local_name(tag: str) -> str:
    return tag.split("}")[-1]


def child_text(elem: ET.Element, name: str) -> str:
    for child in list(elem):
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    raise KeyError(f"XML child {name} absent under {local_name(elem.tag)}")


def float_list(text: str) -> np.ndarray:
    return np.asarray([float(x) for x in text.split()], dtype=np.float64)


def int_list(text: str) -> np.ndarray:
    return np.asarray([int(x) for x in text.split()], dtype=np.int64)


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def fetch_json(url: str, timeout: int = 90) -> dict[str, Any]:
    r = requests.get(url, timeout=(20, timeout), headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.json()


def download_verified(uri: str, expected_sha: str, expected_bytes: int | None, target: Path, timeout: int = 600) -> dict[str, Any]:
    url = s3_to_https(uri)
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(url, stream=True, timeout=(30, timeout), headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with target.open("wb") as fh:
                for chunk in r.iter_content(4 * 1024 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
        got = h.hexdigest()
        if got != expected_sha:
            raise ValueError(f"SHA256 mismatch for {target.name}: expected {expected_sha}, got {got}")
        if expected_bytes is not None and n != int(expected_bytes):
            raise ValueError(f"byte count mismatch for {target.name}: expected {expected_bytes}, got {n}")
        return {"transport_status": "SUCCESS", "bytes": n, "sha256": got, "resolved_url": url}
    except Exception as exc:
        if target.exists():
            target.unlink()
        return {
            "transport_status": "TRANSPORT_BLOCKED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            "bytes_received_before_failure": n,
            "resolved_url": url,
            "error": repr(exc),
        }


def geojson_points(obj: Any) -> Iterable[tuple[float, float]]:
    if isinstance(obj, dict):
        if obj.get("type") == "FeatureCollection":
            for f in obj.get("features", []):
                yield from geojson_points(f)
        elif obj.get("type") == "Feature":
            yield from geojson_points(obj.get("geometry"))
        elif "coordinates" in obj:
            yield from geojson_points(obj["coordinates"])
    elif isinstance(obj, list):
        if len(obj) >= 2 and all(isinstance(v, (int, float)) for v in obj[:2]):
            yield float(obj[0]), float(obj[1])
        else:
            for item in obj:
                yield from geojson_points(item)


def basin_bbox(path: Path) -> tuple[float, float, float, float]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    pts = list(geojson_points(obj))
    if not pts:
        raise ValueError("basin geometry has no coordinates")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def parse_geolocation(path: Path) -> list[dict[str, float]]:
    root = ET.parse(path).getroot()
    out: list[dict[str, float]] = []
    for elem in root.iter():
        if local_name(elem.tag) != "geolocationGridPoint":
            continue
        try:
            out.append({
                "line": float(child_text(elem, "line")),
                "pixel": float(child_text(elem, "pixel")),
                "lat": float(child_text(elem, "latitude")),
                "lon": float(child_text(elem, "longitude")),
            })
        except (KeyError, ValueError):
            continue
    if not out:
        raise ValueError("product annotation has no geolocationGridPoint records")
    return out


def derive_window(
    geo: list[dict[str, float]],
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
    margin_deg: float = 0.03,
    padding_px: int = 512,
) -> dict[str, Any]:
    minx, miny, maxx, maxy = bbox
    inside = [p for p in geo if minx - margin_deg <= p["lon"] <= maxx + margin_deg and miny - margin_deg <= p["lat"] <= maxy + margin_deg]
    rule = "GEOLOCATION_POINTS_WITHIN_BASIN_BBOX_PLUS_0P03_DEG"
    if len(inside) < 4:
        corners = [(minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy), ((minx+maxx)/2, (miny+maxy)/2)]
        coslat = math.cos(math.radians((miny + maxy) / 2))
        inside = []
        for x, y in corners:
            inside.append(min(geo, key=lambda p: ((p["lon"] - x) * coslat) ** 2 + (p["lat"] - y) ** 2))
        rule = "NEAREST_GEOLOCATION_POINT_TO_BBOX_CORNERS_AND_CENTER_FALLBACK"
    pmin = max(0, int(math.floor(min(p["pixel"] for p in inside))) - padding_px)
    pmax = min(width, int(math.ceil(max(p["pixel"] for p in inside))) + padding_px + 1)
    lmin = max(0, int(math.floor(min(p["line"] for p in inside))) - padding_px)
    lmax = min(height, int(math.ceil(max(p["line"] for p in inside))) + padding_px + 1)
    if pmax <= pmin or lmax <= lmin:
        raise ValueError("derived native window is empty")
    return {
        "rule": rule,
        "margin_deg": margin_deg,
        "padding_px": padding_px,
        "geolocation_points_used": len(inside),
        "col_off": pmin,
        "row_off": lmin,
        "width": pmax - pmin,
        "height": lmax - lmin,
    }


def parse_calibration(path: Path) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    out = []
    for elem in root.iter():
        if local_name(elem.tag) != "calibrationVector":
            continue
        try:
            pixels = int_list(child_text(elem, "pixel"))
            vals = float_list(child_text(elem, "sigmaNought"))
            line = int(child_text(elem, "line"))
        except (KeyError, ValueError):
            continue
        if pixels.size != vals.size or pixels.size < 2:
            continue
        out.append({"line": line, "pixels": pixels, "values": vals})
    out.sort(key=lambda x: x["line"])
    if len(out) < 2:
        raise ValueError("insufficient calibration vectors")
    return out


def parse_noise(path: Path) -> tuple[list[dict[str, Any]], str]:
    root = ET.parse(path).getroot()
    for vector_tag in ("noiseRangeVector", "noiseVector"):
        out = []
        for elem in root.iter():
            if local_name(elem.tag) != vector_tag:
                continue
            try:
                pixels = int_list(child_text(elem, "pixel"))
                vals = float_list(child_text(elem, "noiseRangeLut" if vector_tag == "noiseRangeVector" else "noiseLut"))
                line = int(child_text(elem, "line"))
            except (KeyError, ValueError):
                continue
            if pixels.size != vals.size or pixels.size < 2:
                continue
            out.append({"line": line, "pixels": pixels, "values": vals})
        out.sort(key=lambda x: x["line"])
        if len(out) >= 2:
            return out, vector_tag
    raise ValueError("insufficient Sentinel-1 noise range vectors")


def interp_vector(vectors: list[dict[str, Any]], line: int, pixels: np.ndarray) -> np.ndarray:
    lines = [int(v["line"]) for v in vectors]
    j = bisect.bisect_right(lines, line)
    if j <= 0:
        lo = hi = 0
    elif j >= len(vectors):
        lo = hi = len(vectors) - 1
    else:
        lo, hi = j - 1, j
    v0, v1 = vectors[lo], vectors[hi]
    a0 = np.interp(pixels, v0["pixels"], v0["values"])
    if lo == hi or v1["line"] == v0["line"]:
        return a0
    a1 = np.interp(pixels, v1["pixels"], v1["values"])
    w = (line - v0["line"]) / (v1["line"] - v0["line"])
    return a0 * (1.0 - w) + a1 * w


def quantiles(values: np.ndarray) -> dict[str, float | None]:
    if values.size == 0:
        return {k: None for k in ("p05", "p25", "median", "p75", "p95")}
    q = np.quantile(values, [0.05, 0.25, 0.5, 0.75, 0.95])
    return dict(zip(("p05", "p25", "median", "p75", "p95"), [float(x) for x in q]))


def process_native(
    vv_path: Path,
    calibration_path: Path,
    noise_path: Path,
    product_path: Path,
    bbox: tuple[float, float, float, float],
    chunk_rows: int = 128,
) -> dict[str, Any]:
    cal = parse_calibration(calibration_path)
    noise, noise_schema = parse_noise(noise_path)
    geo = parse_geolocation(product_path)
    with rasterio.open(vv_path) as ds:
        w = derive_window(geo, bbox, ds.width, ds.height)
        cols = np.arange(w["col_off"], w["col_off"] + w["width"], dtype=np.float64)
        valid_chunks: list[np.ndarray] = []
        total = 0
        zero_dn = 0
        nonpositive_signal = 0
        for r0 in range(w["row_off"], w["row_off"] + w["height"], chunk_rows):
            h = min(chunk_rows, w["row_off"] + w["height"] - r0)
            dn = ds.read(1, window=Window(w["col_off"], r0, w["width"], h)).astype(np.float64)
            total += dn.size
            zero_dn += int(np.count_nonzero(dn == 0))
            for local_row in range(h):
                line = r0 + local_row
                a = interp_vector(cal, line, cols)
                eta = interp_vector(noise, line, cols)
                signal = dn[local_row] ** 2 - eta
                bad = (~np.isfinite(signal)) | (~np.isfinite(a)) | (signal <= 0) | (a <= 0)
                nonpositive_signal += int(np.count_nonzero((signal <= 0) | (~np.isfinite(signal))))
                sigma = np.full(signal.shape, np.nan, dtype=np.float64)
                sigma[~bad] = signal[~bad] / (a[~bad] ** 2)
                good = sigma[np.isfinite(sigma) & (sigma > 0)]
                if good.size:
                    valid_chunks.append(good.astype(np.float32))
        vals = np.concatenate(valid_chunks) if valid_chunks else np.asarray([], dtype=np.float32)
        db = 10.0 * np.log10(vals.astype(np.float64)) if vals.size else np.asarray([], dtype=np.float64)
        return {
            "native_measurement_shape": {"height": ds.height, "width": ds.width, "dtype": str(ds.dtypes[0])},
            "native_window": w,
            "noise_schema": noise_schema,
            "calibration_vector_count": len(cal),
            "noise_vector_count": len(noise),
            "pixel_count_total": total,
            "pixel_count_valid_sigma0": int(vals.size),
            "valid_sigma0_fraction": float(vals.size / total) if total else None,
            "zero_dn_fraction": float(zero_dn / total) if total else None,
            "nonpositive_noise_corrected_signal_fraction": float(nonpositive_signal / total) if total else None,
            "sigma0_linear_quantiles": quantiles(vals.astype(np.float64)),
            "sigma0_db_quantiles": quantiles(db),
            "diagnostic_semantics": "NATIVE_GEOMETRY_SINGLE_DATE_DIAGNOSTIC_NOT_PRE_POST_COMPARABLE",
            "common_support_established": False,
            "terrain_correction_performed": False,
        }


def stac_item(item_id: str) -> dict[str, Any]:
    return fetch_json(f"{EARTH_SEARCH}/collections/sentinel-1-grd/items/{quote(item_id, safe='')}")


def side_run(side: str, frozen: dict[str, Any], bbox: tuple[float, float, float, float], tmp: Path) -> dict[str, Any]:
    item_id = frozen["item_id"]
    try:
        item = stac_item(item_id)
    except Exception as exc:
        return {
            "side": side,
            "item_id": item_id,
            "status": "TRANSPORT_BLOCKED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            "error": repr(exc),
        }
    paths: dict[str, Path] = {}
    verified: dict[str, Any] = {}
    for key in ASSET_KEYS:
        href = ((item.get("assets") or {}).get(key) or {}).get("href")
        expected = (frozen.get("assets") or {}).get(key) or {}
        if not href or not expected.get("sha256"):
            return {
                "side": side,
                "item_id": item_id,
                "status": "UNKNOWN_ASSET_REFERENCE_OR_FROZEN_HASH_ABSENT",
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
                "asset": key,
            }
        suffix = ".tif" if key == "vv" else ".xml"
        p = tmp / f"{side}-{key}{suffix}"
        result = download_verified(href, expected["sha256"], expected.get("bytes"), p)
        verified[key] = result
        if result["transport_status"] != "SUCCESS":
            return {
                "side": side,
                "item_id": item_id,
                "status": "TRANSPORT_BLOCKED",
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
                "assets_verified": verified,
            }
        paths[key] = p
    diag = process_native(
        paths["vv"],
        paths["schema-calibration-vv"],
        paths["schema-noise-vv"],
        paths["schema-product-vv"],
        bbox,
    )
    return {
        "side": side,
        "item_id": item_id,
        "datetime": frozen.get("datetime"),
        "platform": frozen.get("platform"),
        "relative_orbit": frozen.get("relative_orbit"),
        "orbit_state": frozen.get("orbit_state"),
        "instrument_mode": frozen.get("instrument_mode"),
        "polarizations": frozen.get("polarizations"),
        "status": "R1_NATIVE_RADIOMETRIC_COMPLETE",
        "assets_verified": verified,
        "diagnostics": diag,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", required=True, type=Path)
    ap.add_argument("--basin", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    required_false = ("production_use", "production_ready", "operational_alerting_enabled", "uses_operational_event_none_labels")
    if any(freeze.get(k) is not False for k in required_false):
        raise ValueError("frozen Sentinel-1 manifest violates IBVF guardrails")
    if freeze.get("territorial_activation_evidence_blinded") is not True:
        raise ValueError("territorial evidence must remain blinded")
    if freeze.get("freeze_status") != "ALL_REQUESTED_ASSETS_SHA256_FROZEN":
        raise ValueError("R1 requires all requested Sentinel-1 assets frozen by SHA-256")
    bbox = basin_bbox(args.basin)
    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-sentinel1-a4-r1-v0.1",
        "generated_at": now(),
        "case_id": freeze.get("case_id"),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "stage": "A4_R1_NATIVE_RADIOMETRIC",
        "source_freeze_sha256": hashlib.sha256(args.freeze.read_bytes()).hexdigest(),
        "basin_geometry_sha256": hashlib.sha256(args.basin.read_bytes()).hexdigest(),
        "basin_bbox_lonlat": list(bbox),
        "radiometric_equation": "sigma0_linear=(DN^2-noise_range_lut)/(sigmaNought_calibration_lut^2)",
        "invalid_signal_rule": "DN^2-noise<=0 -> INVALID_NAN_NEVER_ZERO",
        "comparison_performed": False,
        "terrain_correction_performed": False,
        "common_support_established": False,
        "interpretation_forbidden": True,
    }
    with tempfile.TemporaryDirectory(prefix="irfen-ibvf-s1-r1-") as td:
        tmp = Path(td)
        report["pre"] = side_run("pre", freeze["pre"], bbox, tmp)
        report["post"] = side_run("post", freeze["post"], bbox, tmp)
    statuses = [report["pre"].get("status"), report["post"].get("status")]
    if statuses == ["R1_NATIVE_RADIOMETRIC_COMPLETE", "R1_NATIVE_RADIOMETRIC_COMPLETE"]:
        report["r1_status"] = "COMPLETE_BOTH_DATES_NO_COMPARISON"
        report["next_stage"] = "A4_R2_TERRAIN_GEOMETRIC_CORRECTION_COMMON_GRID_PREREGISTERED_BEFORE_DIFFERENCES"
    elif "TRANSPORT_BLOCKED" in statuses:
        report["r1_status"] = "TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING"
        report["next_stage"] = "RETRY_R1_WITH_IDENTICAL_CONTRACT"
    else:
        report["r1_status"] = "INCOMPLETE_UNKNOWN_NOT_MISSING"
        report["next_stage"] = "RESOLVE_R1_INPUT_INTEGRITY_WITHOUT_CHANGING_SCIENTIFIC_RULES"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "r1_status": report["r1_status"],
        "pre": {k: report["pre"].get(k) for k in ("item_id", "status")},
        "post": {k: report["post"].get(k) for k in ("item_id", "status")},
        "pre_diagnostics": report["pre"].get("diagnostics"),
        "post_diagnostics": report["post"].get("diagnostics"),
        "comparison_performed": False,
        "serious_modeling_gate": report["serious_modeling_gate"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
