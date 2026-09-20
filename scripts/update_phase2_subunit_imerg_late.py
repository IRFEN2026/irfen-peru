#!/usr/bin/env python3
"""Fetch NASA GPM IMERG Late Daily over Claude-F Phase-2 research subunits.

RESEARCH_ONLY / TEST_ONLY. This script produces observed satellite rainfall
only. It never infers activation, risk, thresholds, antecedent state, or
candidate-wide rainfall.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile

import earthaccess
import h5py
import numpy as np
from shapely.geometry import box

from phase2_subunit_sampling import load_research_subunit_targets

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/phase2/subunit_imerg_late_v0_1.json"
PRODUCT = "GPM_3IMERGDL"
SOURCE_NAME = "NASA GPM IMERG Late Daily"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def existing_is_fresh(now, min_refresh_hours):
    if not OUT.is_file():
        return False
    try:
        existing = load_json(OUT)
        current_targets = load_research_subunit_targets()
    except Exception:
        return False

    expected_target_ids = {target["id"] for target in current_targets}
    existing_target_ids = {
        row.get("target_id")
        for row in existing.get("targets") or []
        if row.get("target_id")
    }
    if existing_target_ids != expected_target_ids:
        # A newly admitted Claude-F subunit must bootstrap its own Late
        # history immediately; a globally fresh file is not fresh for a
        # target that is absent from it.
        return False

    generated = parse_time(existing.get("generated_at"))
    if generated is None:
        return False
    age_hours = (now - generated.astimezone(timezone.utc)).total_seconds() / 3600.0
    latest = existing.get("latest_observation_date")
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    return age_hours < min_refresh_hours and latest is not None and latest >= yesterday


def find_dataset(group, preferred):
    for name in preferred:
        if name in group:
            return group[name]
        path = f"Grid/{name}"
        if path in group:
            return group[path]
    wanted = {name.lower() for name in preferred}
    found = []

    def visitor(name, obj):
        if isinstance(obj, h5py.Dataset) and name.split("/")[-1].lower() in wanted:
            found.append(obj)

    group.visititems(visitor)
    return found[0] if found else None


def read_daily_grid(path: Path):
    with h5py.File(path, "r") as handle:
        lat_ds = find_dataset(handle, ["lat", "latitude"])
        lon_ds = find_dataset(handle, ["lon", "longitude"])
        precip_ds = find_dataset(
            handle, ["precipitation", "precipitationCal", "precipitationUncal"]
        )
        if lat_ds is None or lon_ds is None or precip_ds is None:
            raise RuntimeError(f"missing lat/lon/precipitation in {path.name}")
        lat = np.asarray(lat_ds[:]).squeeze()
        lon = np.asarray(lon_ds[:]).squeeze()
        values = np.asarray(precip_ds[:], dtype=float).squeeze()
        while values.ndim > 2:
            values = values[0]
        if values.shape == (lon.size, lat.size):
            values = values.T
        if values.shape != (lat.size, lon.size):
            raise RuntimeError(
                f"unexpected grid shape {values.shape}; lat={lat.size} lon={lon.size}"
            )
        values[values < 0] = np.nan
        units = precip_ds.attrs.get("units", "")
        if isinstance(units, bytes):
            units = units.decode(errors="ignore")
        units_text = str(units)
        units_lower = units_text.lower()
        if "mm/hr" in units_lower or "mm h-1" in units_lower or "mm/hour" in units_lower:
            values *= 24.0
        return lat, lon, values, units_text


def polygon_mean_complete(geom, lat, lon, values):
    dx = float(np.median(np.abs(np.diff(lon))))
    dy = float(np.median(np.abs(np.diff(lat))))
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - dx / 2) & (lon <= maxx + dx / 2))[0]
    ys = np.where((lat >= miny - dy / 2) & (lat <= maxy + dy / 2))[0]

    total_area = 0.0
    valid_area = 0.0
    weighted_value = 0.0
    intersected = 0
    valid = 0
    for row in ys:
        for col in xs:
            cell = box(
                float(lon[col]) - dx / 2,
                float(lat[row]) - dy / 2,
                float(lon[col]) + dx / 2,
                float(lat[row]) + dy / 2,
            )
            intersection = geom.intersection(cell)
            if intersection.is_empty or intersection.area <= 0:
                continue
            area = float(intersection.area)
            intersected += 1
            total_area += area
            value = float(values[row, col])
            if np.isfinite(value):
                valid += 1
                valid_area += area
                weighted_value += area * value

    partial_mean = weighted_value / valid_area if valid_area else None
    geometry_covered = math.isclose(
        total_area, float(geom.area), rel_tol=1e-6, abs_tol=1e-12
    )
    complete = (
        intersected > 0
        and valid == intersected
        and geometry_covered
        and math.isclose(valid_area, total_area, rel_tol=1e-9, abs_tol=1e-12)
    )
    normalized = partial_mean if complete else None
    coverage_pct = (
        round(100.0 * valid_area / max(float(geom.area), 1e-15), 4)
        if geom.area > 0
        else None
    )
    return normalized, {
        "sampling_method": "AREA_WEIGHTED_GRID_CELL_INTERSECTION",
        "cells_intersected": intersected,
        "valid_cells": valid,
        "grid_resolution_deg": [round(dx, 6), round(dy, 6)],
        "valid_geometry_coverage_pct": coverage_pct,
        "complete_spatial_coverage": complete,
        "partial_mean_mm_non_decisional": (
            None if complete or partial_mean is None else round(partial_mean, 4)
        ),
    }


def date_from_name(path: Path):
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", path.name)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def search_granules(start, end):
    errors = []
    for version in ("08", "07"):
        try:
            granules = earthaccess.search_data(
                short_name=PRODUCT,
                version=version,
                temporal=(start.isoformat(), end.isoformat()),
                count=40,
            )
            if granules:
                return granules, version
        except Exception as exc:
            errors.append(f"V{version}: {exc}")
    granules = earthaccess.search_data(
        short_name=PRODUCT,
        temporal=(start.isoformat(), end.isoformat()),
        count=40,
    )
    if granules:
        return granules, "auto"
    raise RuntimeError("no IMERG Late Daily granules found; " + " | ".join(errors))


def consecutive_window(series, days):
    by_date = {
        date.fromisoformat(row["date"]): row
        for row in series
        if row.get("date")
    }
    usable_dates = sorted(
        day for day, row in by_date.items() if row.get("rain_mm") is not None
    )
    if not usable_dates:
        return {
            "available": False,
            "days_required": days,
            "days_available": 0,
            "start_date": None,
            "end_date": None,
            "accum_mm": None,
        }
    end = usable_dates[-1]
    required = [end - timedelta(days=offset) for offset in range(days)]
    rows = [by_date.get(day) for day in required]
    complete = all(row is not None and row.get("rain_mm") is not None for row in rows)
    return {
        "available": complete,
        "days_required": days,
        "days_available": sum(
            row is not None and row.get("rain_mm") is not None for row in rows
        ),
        "start_date": (end - timedelta(days=days - 1)).isoformat() if complete else None,
        "end_date": end.isoformat() if complete else None,
        "accum_mm": (
            round(sum(float(row["rain_mm"]) for row in rows), 3)
            if complete
            else None
        ),
    }


def contingency(now, error):
    if OUT.is_file():
        print("IMERG Late subunit source unavailable; preserving last valid artifact:", error)
        return 0
    targets = load_research_subunit_targets()
    payload = {
        "version": "phase2-subunit-imerg-late-v0.1",
        "generated_at": now.isoformat(),
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "status": "SOURCE_TEMPORARILY_UNAVAILABLE",
        "source": SOURCE_NAME,
        "product": PRODUCT,
        "product_version": None,
        "latest_observation_date": None,
        "source_error": {"type": type(error).__name__, "message": str(error)[:500]},
        "targets": [
            {
                "target_id": target["id"],
                "candidate_id": target["candidate_id"],
                "subunit_id": target["subunit_id"],
                "geometry_sha256": target["geometry_sha256"],
                "series": [],
                "windows": {
                    "24h": consecutive_window([], 1),
                    "72h": consecutive_window([], 3),
                    "7d": consecutive_window([], 7),
                },
            }
            for target in targets
        ],
    }
    write_json(OUT, payload)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=12)
    parser.add_argument("--min-refresh-hours", type=float, default=6.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    if not args.force and existing_is_fresh(now, args.min_refresh_hours):
        print("IMERG Late subunit artifact is fresh enough; skipping network refresh.")
        return 0
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("EARTHDATA_TOKEN is required")

    targets = load_research_subunit_targets()
    if not targets:
        raise SystemExit("No RESEARCH_SAMPLING_ELIGIBLE Phase-2 subunits")

    try:
        earthaccess.login(strategy="environment")
        end = now.date()
        start = end - timedelta(days=max(args.days, 8))
        granules, version = search_granules(start, end)
        with tempfile.TemporaryDirectory(prefix="irfen_phase2_subunit_late_") as tmp:
            paths = earthaccess.download(
                granules, local_path=tmp, threads=4, show_progress=False
            )
            series = {target["id"]: [] for target in targets}
            for raw_path in sorted(map(Path, paths)):
                day = date_from_name(raw_path)
                if day is None:
                    continue
                lat, lon, values, units = read_daily_grid(raw_path)
                for target in targets:
                    normalized, sampling = polygon_mean_complete(
                        target["geometry"], lat, lon, values
                    )
                    series[target["id"]].append({
                        "date": day.isoformat(),
                        "rain_mm": (
                            None if normalized is None else round(float(normalized), 4)
                        ),
                        "units_source": units,
                        "sampling": sampling,
                    })
    except Exception as exc:
        return contingency(now, exc)

    target_rows = []
    all_dates = []
    for target in targets:
        dedup = {row["date"]: row for row in series[target["id"]]}
        ordered = [dedup[key] for key in sorted(dedup)]
        all_dates.extend(
            row["date"] for row in ordered if row.get("rain_mm") is not None
        )
        target_rows.append({
            "target_id": target["id"],
            "candidate_id": target["candidate_id"],
            "subunit_id": target["subunit_id"],
            "geometry_path": target["geometry_path"],
            "geometry_sha256": target["geometry_sha256"],
            "declared_area_km2": target["declared_area_km2"],
            "series": ordered[-14:],
            "windows": {
                "24h": consecutive_window(ordered, 1),
                "72h": consecutive_window(ordered, 3),
                "7d": consecutive_window(ordered, 7),
            },
        })

    payload = {
        "version": "phase2-subunit-imerg-late-v0.1",
        "generated_at": now.isoformat(),
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "status": "OBSERVATION_DATA_AVAILABLE" if all_dates else "INSUFFICIENT_EVIDENCE",
        "source": SOURCE_NAME,
        "product": PRODUCT,
        "product_version": version,
        "latest_observation_date": max(all_dates) if all_dates else None,
        "source_error": None,
        "targets": target_rows,
        "guardrails": {
            "candidate_wide_interpretation_forbidden": True,
            "partial_spatial_coverage_is_not_normalized": True,
            "missing_data_is_unknown_never_zero": True,
            "threshold_inference_allowed": False,
            "activation_inference_allowed": False,
        },
    }
    write_json(OUT, payload)
    print(json.dumps({
        "status": payload["status"],
        "latest_observation_date": payload["latest_observation_date"],
        "targets": {
            row["subunit_id"]: {
                key: value.get("accum_mm")
                for key, value in row["windows"].items()
            }
            for row in target_rows
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
