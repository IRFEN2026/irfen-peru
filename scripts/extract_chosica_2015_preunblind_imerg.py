#!/usr/bin/env python3
"""Extract outcome-blind, basin-weighted IMERG Final V07 predictors for Chosica 2015.

This script is intentionally pre-unblind. It reads only frozen basin geometry provenance,
the frozen predictor-time plan, and NASA GPM IMERG precipitation. It never reads observed
activation labels or INGEMMET A6680 numeric morphometry and never derives thresholds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from pyproj import Transformer
import requests
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/chosica_2015_outlet_freeze_registry_v0_1.json"
TIME_PLAN = ROOT / "config/chosica_2015_preunblind_predictor_time_plan_v0_1.json"
EXECUTION = ROOT / "config/chosica_2015_preunblind_imerg_execution_v0_1.json"
SERVICE = "https://gis.earthdata.nasa.gov/image/rest/services/GESDISC/GPM_3IMERGHH/ImageServer/getSamples"
TARGETS = (
    "cashahuacra",
    "quirio",
    "pedregal_san_antonio",
    "la_libertad",
    "carossio",
    "rayos_de_sol",
)
UTC = timezone.utc
PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise RuntimeError(f"FAIL_CLOSED_NAIVE_TIME {value}")
    return dt.astimezone(UTC)


def find_exact_frozen_geometry(root: Path, target_id: str, expected_sha: str) -> Path:
    folder = root / target_id
    if not folder.exists():
        raise RuntimeError(f"FAIL_CLOSED_MISSING_GEOMETRY_DIR {target_id}")
    candidates = sorted(folder.rglob("*.geojson"))
    matches = [p for p in candidates if sha256_path(p) == expected_sha]
    if len(matches) != 1:
        raise RuntimeError(
            f"FAIL_CLOSED_GEOMETRY_HASH_MATCH_COUNT {target_id} expected={expected_sha} matches={len(matches)}"
        )
    return matches[0]


def imerg_cells_for_geometry(geom):
    minx, miny, maxx, maxy = geom.bounds
    ix0 = math.floor((minx + 180.0) / 0.1) - 1
    ix1 = math.floor((maxx + 180.0) / 0.1) + 1
    iy0 = math.floor((miny + 90.0) / 0.1) - 1
    iy1 = math.floor((maxy + 90.0) / 0.1) + 1
    projected_geom = shp_transform(PROJECT, geom)
    cells = []
    for ix in range(ix0, ix1 + 1):
        lon = -179.95 + ix * 0.1
        for iy in range(iy0, iy1 + 1):
            lat = -89.95 + iy * 0.1
            cell = box(lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05)
            if not geom.intersects(cell):
                continue
            inter = projected_geom.intersection(shp_transform(PROJECT, cell))
            area_m2 = float(inter.area)
            if area_m2 > 0:
                cells.append({
                    "lon": round(lon, 5),
                    "lat": round(lat, 5),
                    "intersection_area_m2": area_m2,
                })
    total = sum(c["intersection_area_m2"] for c in cells)
    if not cells or not math.isfinite(total) or total <= 0:
        raise RuntimeError("FAIL_CLOSED_NO_POSITIVE_IMERG_INTERSECTION")
    for c in cells:
        c["weight"] = c["intersection_area_m2"] / total
    if abs(sum(c["weight"] for c in cells) - 1.0) > 1e-12:
        raise RuntimeError("FAIL_CLOSED_WEIGHT_NORMALIZATION")
    return cells


def as_millis(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    try:
        return int(parse_utc(text).timestamp() * 1000)
    except Exception:
        return None


def sample_block(points, start: datetime, end_inclusive: datetime, session: requests.Session):
    geometry = json.dumps({
        "points": [[p["lon"], p["lat"]] for p in points],
        "spatialReference": {"wkid": 4326},
    }, separators=(",", ":"))
    params = {
        "geometry": geometry,
        "geometryType": "esriGeometryMultipoint",
        "time": f"{int(start.timestamp()*1000)},{int(end_inclusive.timestamp()*1000)}",
        "returnFirstValueOnly": "false",
        "outFields": "StdTime",
        "f": "json",
    }
    last = None
    for attempt in range(3):
        try:
            response = session.get(SERVICE, params=params, timeout=90)
            data = response.json()
            if response.status_code != 200 or data.get("error"):
                raise RuntimeError(f"HTTP {response.status_code}: {data.get('error', data)}")
            return data.get("samples") or []
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(
        f"FAIL_CLOSED_NASA_GIS_REQUEST {start.isoformat()} {end_inclusive.isoformat()} {last}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry-root", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    registry = load_json(REGISTRY)
    plan = load_json(TIME_PLAN)
    execution = load_json(EXECUTION)
    geometry_root = Path(args.geometry_root)
    report_path = Path(args.report)

    guards = {
        "RESEARCH_ONLY": True,
        "TEST_ONLY": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
    }
    if registry.get("guards") != guards or plan.get("guards") != guards or execution.get("guards") != guards:
        raise RuntimeError("FAIL_CLOSED_GUARD_MISMATCH")
    gate = registry.get("batch_gate", {})
    if gate.get("frozen_outlet_count") != 6 or gate.get("frozen_geometry_count") != 6:
        raise RuntimeError("FAIL_CLOSED_GEOMETRY_GATE_COUNTS")
    if gate.get("basin_weighted_imerg_allowed") is not True or gate.get("unblind_allowed") is not False:
        raise RuntimeError("FAIL_CLOSED_IMERG_OR_UNBLIND_GATE")

    start = parse_utc(plan["grid"]["start_utc"])
    end_exclusive = parse_utc(plan["grid"]["end_exclusive_utc"])
    anchor = parse_utc(plan["anchor_utc"])
    slot_minutes = int(plan["grid"]["slot_minutes"])
    slot_count = int(plan["grid"]["slot_count"])
    if end_exclusive != anchor or slot_minutes != 30 or slot_count != 720:
        raise RuntimeError("FAIL_CLOSED_FROZEN_TIME_GRID")
    expected_end = start + timedelta(minutes=slot_minutes * slot_count)
    if expected_end != end_exclusive:
        raise RuntimeError("FAIL_CLOSED_TIME_GRID_ARITHMETIC")

    basin_meta = {}
    global_cells = {}
    for target_id in TARGETS:
        t = registry["targets"][target_id]
        if t.get("outlet_status") != "FROZEN" or t.get("geometry_status") != "FROZEN_BY_REPRODUCIBLE_D8_HASH":
            raise RuntimeError(f"FAIL_CLOSED_TARGET_NOT_FROZEN {target_id}")
        expected_sha = t["geometry_freeze"]["geometry_geojson_sha256"]
        geom_path = find_exact_frozen_geometry(geometry_root, target_id, expected_sha)
        geom_doc = load_json(geom_path)
        geom = shape(geom_doc["features"][0]["geometry"] if geom_doc.get("type") == "FeatureCollection" else geom_doc["geometry"])
        if geom.is_empty or not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty or not geom.is_valid:
            raise RuntimeError(f"FAIL_CLOSED_INVALID_FROZEN_GEOMETRY {target_id}")
        cells = imerg_cells_for_geometry(geom)
        for c in cells:
            global_cells[(c["lon"], c["lat"])] = {"lon": c["lon"], "lat": c["lat"]}
        basin_meta[target_id] = {
            "geometry_sha256": expected_sha,
            "geometry_file_name": geom_path.name,
            "cells": cells,
        }

    points = [global_cells[k] for k in sorted(global_cells)]
    point_index = {(p["lon"], p["lat"]): i for i, p in enumerate(points)}
    for meta in basin_meta.values():
        for c in meta["cells"]:
            c["global_point_index"] = point_index[(c["lon"], c["lat"])]

    observations: dict[int, dict[int, float]] = {}
    duplicate_count = 0
    ignored_outside_grid = 0
    request_count = 0
    session = requests.Session()
    session.headers.update({"User-Agent": execution["retrieval"]["user_agent"]})
    cursor = start
    block_hours = int(execution["retrieval"]["block_hours"])
    while cursor < end_exclusive:
        block_end_exclusive = min(end_exclusive, cursor + timedelta(hours=block_hours))
        block_end_inclusive = block_end_exclusive - timedelta(minutes=slot_minutes)
        samples = sample_block(points, cursor, block_end_inclusive, session)
        request_count += 1
        for sample in samples:
            attrs = sample.get("attributes") or {}
            tm = as_millis(attrs.get("StdTime", attrs.get("stdtime")))
            if tm is None:
                continue
            dt = datetime.fromtimestamp(tm / 1000.0, tz=UTC)
            if dt < start or dt >= end_exclusive or ((dt - start).total_seconds() % (slot_minutes * 60)) != 0:
                ignored_outside_grid += 1
                continue
            loc = sample.get("location") or {}
            try:
                lon = float(loc["x"]); lat = float(loc["y"])
                value = float(sample.get("value"))
            except Exception:
                continue
            if not math.isfinite(value) or value < 0:
                continue
            key = (round(lon, 5), round(lat, 5))
            idx = point_index.get(key)
            if idx is None:
                distances = [((p["lon"] - lon) ** 2 + (p["lat"] - lat) ** 2, i) for i, p in enumerate(points)]
                d2, idx = min(distances)
                if d2 > 0.01 ** 2:
                    raise RuntimeError(f"FAIL_CLOSED_SAMPLE_LOCATION_MISMATCH {lon} {lat}")
            prior = observations.setdefault(tm, {}).get(idx)
            if prior is not None:
                duplicate_count += 1
                if abs(prior - value) > 1e-9:
                    raise RuntimeError(f"FAIL_CLOSED_CONFLICTING_DUPLICATE_SAMPLE {tm} {idx}")
            observations[tm][idx] = value
        cursor = block_end_exclusive

    slots = [start + timedelta(minutes=slot_minutes * i) for i in range(slot_count)]
    targets = []
    for target_id in TARGETS:
        meta = basin_meta[target_id]
        series = []
        valid_count = 0
        for index, dt in enumerate(slots):
            tm = int(dt.timestamp() * 1000)
            vals = observations.get(tm, {})
            missing = [c for c in meta["cells"] if c["global_point_index"] not in vals]
            if missing:
                rate = accum = None
            else:
                rate = sum(vals[c["global_point_index"]] * c["weight"] for c in meta["cells"])
                accum = rate * 0.5
                valid_count += 1
            series.append({
                "slot_index_0based": index,
                "time_utc": dt.isoformat().replace("+00:00", "Z"),
                "rate_mm_hr": None if rate is None else round(rate, 6),
                "accum_mm": None if accum is None else round(accum, 6),
                "all_weighted_cells_present": not missing,
                "missing_weighted_cell_count": len(missing),
            })

        windows = {}
        for w in plan["windows"]:
            a = int(w["grid_start_index_0based"])
            b = int(w["grid_end_index_0based_inclusive"])
            chunk = series[a:b + 1]
            if len(chunk) != int(w["expected_slot_count"]):
                raise RuntimeError(f"FAIL_CLOSED_WINDOW_INDEXING {target_id} {w['id']}")
            complete = all(r["accum_mm"] is not None for r in chunk)
            windows[w["id"]] = {
                "kind": w["kind"],
                "hours": w["hours"],
                "expected_slot_count": w["expected_slot_count"],
                "valid_slot_count": sum(r["accum_mm"] is not None for r in chunk),
                "complete": complete,
                "accum_mm": round(sum(r["accum_mm"] for r in chunk), 6) if complete else None,
            }
        targets.append({
            "target_id": target_id,
            "geometry_sha256": meta["geometry_sha256"],
            "intersecting_imerg_cell_count": len(meta["cells"]),
            "spatial_weights": [
                {
                    "lon": c["lon"], "lat": c["lat"],
                    "intersection_area_m2": round(c["intersection_area_m2"], 3),
                    "weight": round(c["weight"], 12),
                }
                for c in meta["cells"]
            ],
            "slot_count": len(series),
            "valid_slot_count": valid_count,
            "coverage_fraction": valid_count / slot_count,
            "windows": windows,
            "series": series,
        })

    report = {
        "schema_version": "0.1",
        "batch_id": plan["batch_id"],
        "status": "PASS_CHOSICA_2015_PREUNBLIND_IMERG_EXTRACTION",
        "phase": "PREUNBLIND_PREDICTOR_RECONSTRUCTION",
        "guards": guards,
        "outcome_evidence_read": False,
        "a6680_numeric_reference_read": False,
        "post_anchor_predictor_read": False,
        "source": execution["source"],
        "time_grid": plan["grid"],
        "anchor_utc": plan["anchor_utc"],
        "target_count": len(targets),
        "unique_imerg_cell_count": len(points),
        "request_count": request_count,
        "duplicate_sample_count": duplicate_count,
        "ignored_outside_grid_sample_count": ignored_outside_grid,
        "missingness_policy": execution["spatial_aggregation"]["partial_cell_missingness"],
        "geometry_or_outlet_modified": False,
        "window_shifted": False,
        "zero_imputation_used": False,
        "targets": targets,
    }
    if len(targets) != 6 or any(t["slot_count"] != 720 for t in targets):
        raise RuntimeError("FAIL_CLOSED_OUTPUT_DIMENSIONS")
    if any(r["time_utc"] >= plan["anchor_utc"] for t in targets for r in t["series"]):
        raise RuntimeError("FAIL_CLOSED_POST_ANCHOR_OUTPUT")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "target_count": report["target_count"],
        "unique_imerg_cell_count": report["unique_imerg_cell_count"],
        "request_count": request_count,
        "coverage": {t["target_id"]: round(t["coverage_fraction"], 6) for t in targets},
        "outcome_evidence_read": False,
        "a6680_numeric_reference_read": False,
        "post_anchor_predictor_read": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
