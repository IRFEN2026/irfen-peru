#!/usr/bin/env python3
"""IRFEN v0.9: offline SENAMHI station / NASA IMERG Early grid-cell replay.

Reads locally available original NASA GPM_3IMERGHHE V07 HDF5 granules; NEVER
derives a station pixel from province/basin means. Requires explicit station
coordinate provenance and an exactly matched UTC, half-open accumulation window.
This is NOT a hydrological warning or a validated station/satellite bias.

Example (48 original HDF5 granules must be supplied for a complete 24 h result):
  python scripts/v09_station_imerg_cell_replay.py \
    --granule-dir /tmp/imerg-hdf5 \
    --start 2026-10-27T12:00:00Z --end 2026-10-28T12:00:00Z \
    --output /tmp/irfen-station-cell-replay.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATIONS = ROOT / "config/v09_senamhi_station_points_research_v0_1.json"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
              production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False,
              activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False)
VALID_RATE_UNITS = ("mm/hr", "mm h-1", "mm/hour")
HALF_HOUR = timedelta(minutes=30)


def utc(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.utcoffset() is None:
        raise ValueError("UTC timestamps must include a time-zone offset")
    return ts.astimezone(timezone.utc)


def granule_start(filename: str) -> datetime | None:
    m = re.search(r"(20\d{6})-S(\d{6})", filename)
    if not m:
        return None
    return datetime.strptime("".join(m.groups()), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def slots(start: datetime, end: datetime) -> list[datetime]:
    if end <= start or (end - start) > timedelta(hours=72):
        raise ValueError("Require a positive observation window up to 72 hours")
    if (start.minute % 30 or start.second or start.microsecond or
        end.minute % 30 or end.second or end.microsecond):
        raise ValueError("Both timestamps must align to UTC 00/30-minute boundaries")
    duration = (end - start).total_seconds()
    if duration % HALF_HOUR.total_seconds():
        raise ValueError("Window must comprise integral half hours")
    return [start + i * HALF_HOUR for i in range(int(duration // 1800))]


def verify_station(row: dict) -> None:
    if not row.get("station_code") or not row.get("station_name"):
        raise ValueError("Station identity is required")
    if not row.get("coordinate_provenance") or not row.get("coordinate_datum_status"):
        raise ValueError("Coordinate provenance and datum status are required")
    lat, lon = row.get("latitude"), row.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise ValueError("Numeric latitude and longitude are required")
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid station coordinates")


def pixel_at_station(lats, lons, rates, station_lat: float, station_lon: float, units: str) -> dict:
    """Nearest cell CENTER; accept only if station is inside that cell, never extrapolate.

    The grid has already been oriented [lat, lon] by probe.read_grid().
    A grid cell is ~0.1 degrees, so its value is not an in-situ measurement.
    """
    if not any(u in units.lower().replace(" ", "") for u in ("mm/hr", "mmh-1", "mm/hour")):
        raise ValueError(f"IMERG units must represent a rate in mm/hour; got {units!r}")
    lat = np.asarray(lats, dtype=float)
    lon = np.asarray(lons, dtype=float)
    grid = np.asarray(rates, dtype=float)
    if lat.ndim != 1 or lon.ndim != 1 or len(lat) < 2 or len(lon) < 2:
        raise ValueError("Grid latitude/longitude must be one-dimensional with >= 2 cells")
    if grid.shape != (len(lat), len(lon)):
        raise ValueError("Grid shape must be [latitude, longitude]")
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("Nonfinite grid coordinates")
    dy = float(np.median(np.abs(np.diff(lat))))
    dx = float(np.median(np.abs(np.diff(lon))))
    if dx <= 0 or dy <= 0:
        raise ValueError("Invalid grid resolution")
    # Most IMERG longitude arrays use -180..180. Some use 0..360.
    station_lon_grid = station_lon % 360 if lon.min() >= 0 and lon.max() > 180 else station_lon
    r = int(np.argmin(np.abs(lat - station_lat)))
    c = int(np.argmin(np.abs(lon - station_lon_grid)))
    center_lat, center_lon = float(lat[r]), float(lon[c])
    if abs(center_lat - station_lat) > dy / 2 + 1e-7 or abs(center_lon - station_lon_grid) > dx / 2 + 1e-7:
        raise ValueError("Station is outside the supplied IMERG grid: NO_EXTRAPOLATION")
    value = float(grid[r, c])
    valid = np.isfinite(value) and value >= 0
    return dict(cell_id=f"r{r}:c{c}", cell_center_latitude=center_lat,
                cell_center_longitude=center_lon if center_lon <= 180 else center_lon - 360,
                resolution_degrees=[round(dx, 6), round(dy, 6)],
                rate_mm_hr=round(value, 5) if valid else None,
                accumulation_30min_mm=round(value * 0.5, 5) if valid else None,
                status="VALID_SATELLITE_ESTIMATE" if valid else "MISSING_NOT_ZERO",
                spatial_meaning="Grid-cell estimate around station, NOT point rain at gauge")


def summarize(expected_times: list[datetime], observations: dict[str, dict]) -> dict:
    expected = [t.isoformat() for t in expected_times]
    rows = []
    for time in expected:
        row = observations.get(time)
        rows.append(dict(time_utc=time, **row) if row else
                    dict(time_utc=time, status="GRANULE_NOT_AVAILABLE",
                         accumulation_30min_mm=None))
    good = [r for r in rows if r["status"] == "VALID_SATELLITE_ESTIMATE"]
    complete = len(good) == len(rows)
    return dict(status="COMPLETE" if complete else "INCOMPLETE_UNKNOWN_NOT_ZERO",
                expected_half_hours=len(rows), valid_half_hours=len(good),
                missing_half_hours=len(rows) - len(good),
                satellite_accumulated_mm=round(sum(r["accumulation_30min_mm"] for r in good), 3)
                if complete else None, half_hours=rows)


def build_report(stations: list[dict], filenames: list[Path], start: datetime, end: datetime,
                 reader=None) -> dict:
    """Reader injection permits fully offline tests without creating fake NASA records."""
    for row in stations:
        verify_station(row)
    ids = [s["station_code"] for s in stations]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate station codes")
    expected = slots(start, end)
    want = set(expected)
    inputs: dict[datetime, Path] = {}
    for p in filenames:
        if p.suffix.lower() not in (".hdf5", ".h5"):
            continue
        t = granule_start(p.name)
        if t in want:
            if t in inputs:
                raise ValueError(f"Duplicate IMERG granule for {t.isoformat()}")
            inputs[t] = p
    if reader is None:
        sys.path.insert(0, str(ROOT / "scripts"))
        from probe_imerg_early_live import read_grid
        reader = read_grid
    per_station = {code: {} for code in ids}
    granule_manifest = []
    for t in sorted(inputs):
        path = inputs[t]
        # A failed read aborts rather than silently recording a false zero.
        lats, lons, values, units = reader(path)
        sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        granule_manifest.append(dict(time_utc=t.isoformat(), file=path.name, sha256=sha,
                                     unit_original=units))
        for s in stations:
            pixel = pixel_at_station(lats, lons, values, s["latitude"], s["longitude"], units)
            per_station[s["station_code"]][t.isoformat()] = pixel
    results = []
    for s in stations:
        code = s["station_code"]
        series = summarize(expected, per_station[code])
        cells = sorted(set(r.get("cell_id") for r in series["half_hours"] if r.get("cell_id")))
        results.append(dict(station=s, unique_imerg_cell_ids=cells,
                            station_observation_mm=None,
                            station_observation_status="NOT_SUPPLIED_OR_NOT_PRIMARY_VALIDATED",
                            gauge_vs_grid_comparison="BLOCKED_UNTIL_IDENTICAL_WINDOW_PRIMARY_GAUGE_QA",
                            basin_or_quebrada_relationship="UNRESOLVED_REQUIRES_VERIFIED_HYDROLOGIC_CROSSWALK",
                            **series))
    return dict(schema_version="0.1", output_id="irfen-v09-station-imerg-cell-replay",
                purpose="TEST_ONLY station-grid spatial sampling; not a flow, flood or activation prediction",
                **GUARDS, source="NASA GPM_3IMERGHHE V07 HDF5 (local input)",
                source_rate_units="mm/hour", input_station_registry=str(STATIONS.relative_to(ROOT)),
                window_start_utc=start.isoformat(), window_end_utc=end.isoformat(),
                method="Nearest IMERG grid-cell center containing station; rate * 0.5 hour",
                granule_manifest=granule_manifest, stations=results,
                evidence_limitations=["A single IMERG 0.1-degree cell is not a gauge observation.",
                                      "Station coordinates supplied by user screenshot; datum remains unverified.",
                                      "No statistical validation until station gauge 2026 source and daily cutoff are verified.",
                                      "Archive province means cannot be substituted for grid-cell values.",
                                      "Missing files/data are unknown, never 0 mm or low hydrological risk."])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--granule-dir", type=Path, required=True)
    p.add_argument("--stations", type=Path, default=STATIONS)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    metadata = json.loads(args.stations.read_text(encoding="utf-8"))
    stations = metadata["stations"]
    files = list(args.granule_dir.glob("*.HDF5")) + list(args.granule_dir.glob("*.hdf5"))
    result = build_report(stations, files, utc(args.start), utc(args.end))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), count_stations=len(stations),
                          accepted_granules=len(result["granule_manifest"]),
                          statuses={s["station"]["station_code"]: s["status"] for s in result["stations"]})))


if __name__ == "__main__":
    main()
