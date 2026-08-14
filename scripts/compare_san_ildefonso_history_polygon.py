#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timedelta
import json
import os
import re
import tempfile

import earthaccess
import h5py
import numpy as np
from shapely.geometry import shape, box

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "site" / "data" / "history.json"
POLYGON = ROOT / "site" / "data" / "watersheds" / "san_ildefonso_watershed.geojson"
EVENT_ID = "SI-2017-03-15"
EVENT_DATE = datetime.fromisoformat("2017-03-15").date()


def find_dataset(group, names):
    for name in names:
        if name in group:
            return group[name]
        path = f"Grid/{name}"
        if path in group:
            return group[path]
    found = []
    wanted = {x.lower() for x in names}
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
            raise RuntimeError("datasets IMERG no encontrados")
        lat = np.asarray(latd[:]).squeeze()
        lon = np.asarray(lond[:]).squeeze()
        rain = np.asarray(pd[:], dtype=float).squeeze()
        while rain.ndim > 2:
            rain = rain[0]
        if rain.shape == (lon.size, lat.size):
            rain = rain.T
        elif rain.shape != (lat.size, lon.size):
            raise RuntimeError(f"dimensiones inesperadas {rain.shape}")
        rain[rain < 0] = np.nan
        units = pd.attrs.get("units", "")
        if isinstance(units, bytes):
            units = units.decode(errors="ignore")
        units = str(units).lower()
        if "mm/hr" in units or "mm h-1" in units or "mm/hour" in units:
            rain *= 24.0
        return lat, lon, rain


def polygon_mean(lat, lon, rain, geom):
    dx = float(np.median(np.abs(np.diff(lon))))
    dy = float(np.median(np.abs(np.diff(lat))))
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - dx / 2) & (lon <= maxx + dx / 2))[0]
    ys = np.where((lat >= miny - dy / 2) & (lat <= maxy + dy / 2))[0]
    weighted = 0.0
    weight = 0.0
    cells = 0
    valid = 0
    for r in ys:
        y = float(lat[r])
        for c in xs:
            x = float(lon[c])
            cell = box(x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2)
            inter = geom.intersection(cell)
            if inter.is_empty or inter.area <= 0:
                continue
            cells += 1
            value = float(rain[r, c])
            if np.isfinite(value):
                valid += 1
                weight += inter.area
                weighted += inter.area * value
    coverage = 100.0 * weight / max(float(geom.area), 1e-15)
    meta = {
        "cells_intersected": cells,
        "valid_cells": valid,
        "grid_resolution_deg": [round(dx, 4), round(dy, 4)],
        "data_coverage_pct": round(min(100.0, coverage), 2),
    }
    return (weighted / weight if weight else None), meta


def file_date(path):
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", Path(path).name)
    if not match:
        return None
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date()


def total_for_event(series, days):
    by_date = {x["date"]: x["rain_mm"] for x in series}
    values = [by_date.get((EVENT_DATE - timedelta(days=i)).isoformat()) for i in range(days)]
    return round(sum(values), 2) if all(v is not None for v in values) else None


def main():
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("Falta EARTHDATA_TOKEN")

    geom_data = json.loads(POLYGON.read_text(encoding="utf-8"))
    geom = shape(geom_data["geometry"]).buffer(0)
    earthaccess.login(strategy="environment")

    start = EVENT_DATE - timedelta(days=7)
    end = EVENT_DATE + timedelta(days=1)
    granules = earthaccess.search_data(
        short_name="GPM_3IMERGDF",
        version="07",
        temporal=(start.isoformat(), end.isoformat()),
        count=20,
    )
    if not granules:
        raise RuntimeError("No se encontraron gránulos IMERG Final para SI-2017")

    series = []
    with tempfile.TemporaryDirectory(prefix="irfen_hist_poly_") as td:
        paths = earthaccess.download(granules, local_path=td, threads=4, show_progress=False)
        for path in paths:
            date = file_date(path)
            if date is None:
                continue
            lat, lon, rain = read_grid(path)
            value, metadata = polygon_mean(lat, lon, rain, geom)
            if value is not None:
                series.append({
                    "date": date.isoformat(),
                    "rain_mm": round(value, 2),
                    "sampling": metadata,
                })

    series = sorted({x["date"]: x for x in series}.values(), key=lambda x: x["date"])
    polygon24 = total_for_event(series, 1)
    polygon72 = total_for_event(series, 3)
    polygon7d = total_for_event(series, 7)

    data = json.loads(HISTORY.read_text(encoding="utf-8"))
    event = next((x for x in data.get("events", []) if x.get("id") == EVENT_ID), None)
    if event is None:
        raise RuntimeError("Evento SI-2017 no encontrado en history.json")

    def delta(new, old):
        return None if new is None or old is None else round(new - old, 2)

    event["experimental_polygon"] = {
        "status": "historical_parallel_validation",
        "production_use": False,
        "dataset": "Copernicus DEM GLO-30 watershed + GPM_3IMERGDF v07 Final",
        "geometry": "data/watersheds/san_ildefonso_watershed.geojson",
        "method": "IMERG Final ponderado por solape de celdas con la microcuenca DEM",
        "rain24": polygon24,
        "rain72": polygon72,
        "rain7d": polygon7d,
        "delta_vs_legacy_bbox_mm": {
            "rain24": delta(polygon24, event.get("rain24")),
            "rain72": delta(polygon72, event.get("rain72")),
            "rain7d": delta(polygon7d, event.get("rain7d")),
        },
        "series": series,
        "warning": "Comparación científica experimental; los valores históricos originales se conservan sin cambios.",
    }

    HISTORY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SI-2017 legado:", event.get("rain24"), event.get("rain72"), event.get("rain7d"))
    print("SI-2017 polígono:", polygon24, polygon72, polygon7d)
    print("Deltas:", event["experimental_polygon"]["delta_vs_legacy_bbox_mm"])


if __name__ == "__main__":
    main()
