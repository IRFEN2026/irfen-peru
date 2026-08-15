#!/usr/bin/env python3
"""Prueba acotada de IMERG Early 30 min para señales rápidas IRFEN v0.8.

Objetivo: comprobar que Earthdata entrega GPM_3IMERGHHE desde GitHub Actions y
muestrear únicamente San Ildefonso, Huaycoloro y Pedregal. Este script NO
cambia umbrales, amenaza, prioridad ni alertas.

La indisponibilidad temporal de Earthdata se registra como contingencia y no
se confunde con un cero de lluvia. El archivo histórico conserva los últimos
gránulos válidos y permite medir disponibilidad/latencia de la fuente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import re
import tempfile

import earthaccess
import h5py
import numpy as np
import requests
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "data" / "calibration" / "imerg_early_live_probe.json"
ARCHIVE = SITE / "data" / "calibration" / "imerg_early_live_archive.json"
SEARCH_WINDOW_HOURS = 12
MAX_DOWNLOADS_PER_RUN = 4

SOURCE = {
    "institution": "NASA GES DISC / GPM IMERG",
    "short_name": "GPM_3IMERGHHE",
    "version": "07",
    "role": "near_real_time_half_hourly_rainfall_probe",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def previous_probe():
    try:
        return load_json(OUT)
    except Exception:
        return {}


def archived_granule_names():
    """Return already sampled filenames without making the live probe depend on the archive."""
    try:
        archive = load_json(ARCHIVE)
    except Exception:
        return set()
    return {
        row.get("granule")
        for row in archive.get("granules", [])
        if row.get("granule")
    }


def load_targets():
    targets = []
    for zid, name, path in (
        ("san_ildefonso", "San Ildefonso", SITE / "data/watersheds/san_ildefonso_watershed.geojson"),
        ("huaycoloro_main_channel", "Huaycoloro", SITE / "data/watersheds/huaycoloro_watershed.geojson"),
    ):
        data = load_json(path)
        targets.append({"id": zid, "name": name, "geometry": shape(data["geometry"]).buffer(0)})

    local = load_json(SITE / "data/watersheds/chosica_local_candidate_sets.geojson")
    ped = next(
        f for f in local.get("features", [])
        if (f.get("properties") or {}).get("id") == "pedregal_3_8"
    )
    targets.append({
        "id": "pedregal_local",
        "name": "Pedregal / San Antonio de Pedregal",
        "geometry": shape(ped["geometry"]).buffer(0),
    })
    return targets


def find_dataset(group, names):
    for n in names:
        if n in group:
            return group[n]
        if f"Grid/{n}" in group:
            return group[f"Grid/{n}"]
    wanted = {x.lower() for x in names}
    found = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.split("/")[-1].lower() in wanted:
            found.append(obj)

    group.visititems(visit)
    return found[0] if found else None


def read_grid(path):
    with h5py.File(path, "r") as f:
        latd = find_dataset(f, ["lat", "latitude"])
        lond = find_dataset(f, ["lon", "longitude"])
        pd = find_dataset(f, ["precipitation", "precipitationCal", "precipitationUncal"])
        if latd is None or lond is None or pd is None:
            raise RuntimeError(f"No se encontraron lat/lon/precipitation en {Path(path).name}")
        lat = np.asarray(latd[:]).squeeze()
        lon = np.asarray(lond[:]).squeeze()
        p = np.asarray(pd[:], dtype=float).squeeze()
        while p.ndim > 2:
            p = p[0]
        if p.shape == (lon.size, lat.size):
            p = p.T
        if p.shape != (lat.size, lon.size):
            raise RuntimeError(f"Forma inesperada {p.shape}; lat={lat.size}, lon={lon.size}")
        p[p < 0] = np.nan
        units = pd.attrs.get("units", "")
        if isinstance(units, bytes):
            units = units.decode(errors="ignore")
        return lat, lon, p, str(units)


def polygon_mean(geom, lat, lon, values):
    dx = float(np.median(np.abs(np.diff(lon))))
    dy = float(np.median(np.abs(np.diff(lat))))
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - dx / 2) & (lon <= maxx + dx / 2))[0]
    ys = np.where((lat >= miny - dy / 2) & (lat <= maxy + dy / 2))[0]
    sw = sv = 0.0
    intersected = valid = 0
    for r in ys:
        for c in xs:
            cell = box(
                float(lon[c]) - dx / 2,
                float(lat[r]) - dy / 2,
                float(lon[c]) + dx / 2,
                float(lat[r]) + dy / 2,
            )
            inter = geom.intersection(cell)
            if inter.is_empty or inter.area <= 0:
                continue
            intersected += 1
            value = float(values[r, c])
            if np.isfinite(value):
                valid += 1
                sw += inter.area
                sv += inter.area * value
    return (sv / sw if sw else None), {
        "cells_intersected": intersected,
        "valid_cells": valid,
        "grid_resolution_deg": [round(dx, 4), round(dy, 4)],
        "covered_geometry_pct": round(min(100.0, 100.0 * sw / max(geom.area, 1e-15)), 2),
    }


def filename_for(granule):
    try:
        links = granule.data_links()
        if links:
            return Path(links[0].split("?", 1)[0]).name
    except Exception:
        pass
    text = str(granule)
    m = re.search(r"[^/\s\"']+\.HDF5", text, re.I)
    return m.group(0) if m else ""


def timestamp_from_filename(name):
    m = re.search(r"(20\d{6})-S(\d{6})", name)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def last_valid_summary(previous):
    samples = previous.get("samples") or []
    latest_targets = samples[-1].get("targets", []) if samples else []
    if previous.get("status") == "EARLY_HALFHOURLY_SOURCE_AVAILABLE":
        return {
            "probe_generated_at": previous.get("generated_at"),
            "latest_granule_time_utc": previous.get("latest_granule_time_utc"),
            "observed_latency_hours_at_probe": previous.get("observed_latency_hours_at_probe"),
            "latest_targets": latest_targets,
        }
    return previous.get("last_valid")


def write_contingency(now, previous, status, error=None, search_window_hours=None):
    result = {
        "version": "0.8-experimental",
        "generated_at": now.isoformat(),
        "production_use": False,
        "production_ready": False,
        "status": status,
        "source": SOURCE,
        "search_window_hours": search_window_hours,
        "granules_found": 0,
        "granules_downloaded": 0,
        "latest_granule_time_utc": None,
        "observed_latency_hours_at_probe": None,
        "samples": [],
        "last_valid": last_valid_summary(previous),
        "stale": True,
        "source_error": None if error is None else {
            "type": type(error).__name__,
            "message": str(error)[:500],
        },
        "scientific_gate": {
            "status": "SOURCE_TEMPORARILY_UNAVAILABLE",
            "rule": "La indisponibilidad de la fuente nunca se interpreta como cero de lluvia. Se conserva por separado el último dato válido y el archivo histórico mantiene los gránulos previos.",
            "last_valid_retained_for_archive": True,
            "pedregal_next_gate": "compare live/historical signal against ground or higher-fidelity evidence before any decision threshold",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "source_error": result["source_error"],
        "last_valid": result["last_valid"],
    }, ensure_ascii=False, indent=2))
    return 0


def earthdata_preflight():
    # Evita esperar varios minutos dentro de earthaccess cuando el runner no
    # tiene ruta a URS. Cualquier respuesta HTTP demuestra conectividad; 401/403
    # también sirven para esta comprobación.
    response = requests.get("https://urs.earthdata.nasa.gov/profile", timeout=(5, 10), allow_redirects=False)
    return response.status_code


def main():
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("Falta EARTHDATA_TOKEN")

    previous = previous_probe()
    now = datetime.now(timezone.utc)
    targets = load_targets()

    try:
        earthdata_preflight()
        earthaccess.login(strategy="environment")
        granules = earthaccess.search_data(
            short_name="GPM_3IMERGHHE",
            version="07",
            temporal=((now - timedelta(hours=SEARCH_WINDOW_HOURS)).isoformat(), now.isoformat()),
            count=30,
        )
    except (requests.RequestException, OSError, ConnectionError, TimeoutError) as exc:
        return write_contingency(now, previous, "SOURCE_TEMPORARILY_UNREACHABLE", error=exc, search_window_hours=SEARCH_WINDOW_HOURS)

    search_window_hours = SEARCH_WINDOW_HOURS
    if not granules:
        return write_contingency(now, previous, "NO_RECENT_GRANULES", search_window_hours=SEARCH_WINDOW_HOURS)

    indexed = []
    for g in granules:
        name = filename_for(g)
        ts = timestamp_from_filename(name)
        indexed.append((ts or datetime(1970, 1, 1, tzinfo=timezone.utc), name, g))
    indexed.sort(key=lambda x: x[0])
    archived = archived_granule_names()
    missing = [row for row in indexed if row[1] and row[1] not in archived]

    # Always include the newest available granule so latency remains current.
    # Use the remaining bounded slots for the oldest missing granules in the
    # 12-hour search window. This repairs short outages without an unbounded
    # historical download or a false zero in the time series.
    selected = [indexed[-1]]
    for row in missing:
        if row[1] == selected[0][1]:
            continue
        selected.append(row)
        if len(selected) >= MAX_DOWNLOADS_PER_RUN:
            break
    selected.sort(key=lambda x: x[0])

    samples = []
    try:
        with tempfile.TemporaryDirectory(prefix="irfen_imerg_early_") as td:
            paths = earthaccess.download([x[2] for x in selected], local_path=td, threads=2, show_progress=False)
            by_name = {Path(p).name: p for p in paths}
            for ts, expected_name, _ in selected:
                path = by_name.get(expected_name)
                if path is None and paths:
                    path = min(paths, key=lambda p: 0 if timestamp_from_filename(Path(p).name) == ts else 1)
                if path is None:
                    continue
                actual_name = Path(path).name
                actual_ts = timestamp_from_filename(actual_name) or ts
                lat, lon, p, units = read_grid(path)
                rate_units = "mm/hr" in units.lower() or "mm h-1" in units.lower() or "mm/hour" in units.lower()
                target_rows = []
                for target in targets:
                    value, meta = polygon_mean(target["geometry"], lat, lon, p)
                    rate = value if rate_units else None
                    accum = (value * 0.5) if value is not None and rate_units else value
                    target_rows.append({
                        "target_id": target["id"],
                        "name": target["name"],
                        "mean_source_value": None if value is None else round(value, 4),
                        "rate_mm_hr": None if rate is None else round(rate, 4),
                        "accum_30min_mm": None if accum is None else round(accum, 4),
                        "sampling": meta,
                    })
                samples.append({
                    "granule": actual_name,
                    "time_utc": actual_ts.isoformat() if actual_ts.year > 1970 else None,
                    "units": units,
                    "targets": target_rows,
                })
    except (requests.RequestException, OSError, ConnectionError, TimeoutError) as exc:
        return write_contingency(now, previous, "SOURCE_TEMPORARILY_UNREACHABLE", error=exc, search_window_hours=search_window_hours)

    valid_times = [datetime.fromisoformat(x["time_utc"]) for x in samples if x.get("time_utc")]
    latest_time = max(valid_times) if valid_times else None
    latency_hours = None if latest_time is None else round((now - latest_time).total_seconds() / 3600, 2)

    result = {
        "version": "0.8-experimental",
        "generated_at": now.isoformat(),
        "production_use": False,
        "production_ready": False,
        "status": "EARLY_HALFHOURLY_SOURCE_AVAILABLE" if samples else "NO_DOWNLOADED_GRANULES",
        "source": SOURCE,
        "search_window_hours": search_window_hours,
        "granules_found": len(granules),
        "granules_downloaded": len(samples),
        "archive_granules_seen": len(archived),
        "missing_granules_in_search_window": len(missing),
        "bounded_download_limit": MAX_DOWNLOADS_PER_RUN,
        "latest_granule_time_utc": latest_time.isoformat() if latest_time else None,
        "observed_latency_hours_at_probe": latency_hours,
        "samples": samples,
        "last_valid": None,
        "stale": False,
        "source_error": None,
        "scientific_gate": {
            "status": "SOURCE_CONNECTIVITY_ONLY",
            "rule": "Una descarga exitosa resuelve conectividad/latencia técnica, no demuestra que 0.1° represente adecuadamente una microcuenca pequeña.",
            "last_valid_retained_for_archive": True,
            "pedregal_next_gate": "compare live/historical signal against ground or higher-fidelity evidence before any decision threshold",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "granules_found": result["granules_found"],
        "granules_downloaded": result["granules_downloaded"],
        "latest_granule_time_utc": result["latest_granule_time_utc"],
        "observed_latency_hours_at_probe": result["observed_latency_hours_at_probe"],
        "latest_targets": samples[-1]["targets"] if samples else [],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
