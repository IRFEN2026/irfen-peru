#!/usr/bin/env python3
"""Calcula IMERG Late en paralelo sobre polígonos científicos validados.

Este script NO modifica la amenaza ni la prioridad operativa. Añade un bloque
`experimental_polygon` a las zonas elegibles de `latest.json` para comparar el
muestreo espacial v0.8 con las cajas operativas v0.7.1.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import re
import tempfile

import earthaccess
import h5py
import numpy as np
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "site" / "data" / "latest.json"

TARGETS = [
    {
        "zone_id": "san_ildefonso",
        "name": "San Ildefonso",
        "geojson": ROOT / "site" / "data" / "watersheds" / "san_ildefonso_watershed.geojson",
        "validation": ROOT / "site" / "data" / "watersheds" / "san_ildefonso_validation.json",
    },
    {
        "zone_id": "chosica",
        "name": "Huaycoloro / Chosica",
        "geojson": ROOT / "site" / "data" / "watersheds" / "huaycoloro_watershed.geojson",
        "validation": ROOT / "site" / "data" / "watersheds" / "huaycoloro_validation.json",
    },
]


def find_dataset(group, names):
    for n in names:
        if n in group:
            return group[n]
        if f"Grid/{n}" in group:
            return group[f"Grid/{n}"]
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
            raise RuntimeError(f"Datasets IMERG no encontrados en {path}")
        lat = np.asarray(latd[:]).squeeze()
        lon = np.asarray(lond[:]).squeeze()
        p = np.asarray(pd[:], dtype=float).squeeze()
        while p.ndim > 2:
            p = p[0]
        if p.shape == (lon.size, lat.size):
            p = p.T
        p[p < 0] = np.nan
        units = pd.attrs.get("units", "")
        if isinstance(units, bytes):
            units = units.decode(errors="ignore")
        u = str(units).lower()
        if "mm/hr" in u or "mm h-1" in u or "mm/hour" in u:
            p *= 24.0
        return lat, lon, p


def polygon_mean(geom, lat, lon, p):
    dx = float(np.median(np.abs(np.diff(lon))))
    dy = float(np.median(np.abs(np.diff(lat))))
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - dx / 2) & (lon <= maxx + dx / 2))[0]
    ys = np.where((lat >= miny - dy / 2) & (lat <= maxy + dy / 2))[0]

    weight_sum = value_sum = 0.0
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
            v = float(p[r, c])
            if np.isfinite(v):
                valid += 1
                weight_sum += inter.area
                value_sum += inter.area * v

    value = value_sum / weight_sum if weight_sum else None
    return value, {
        "cells_intersected": intersected,
        "valid_cells": valid,
        "grid_resolution_deg": [round(dx, 4), round(dy, 4)],
        "data_coverage_pct": round(min(100.0, 100.0 * weight_sum / max(geom.area, 1e-15)), 2),
    }


def date_from_name(path):
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", Path(path).name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def eligible_targets():
    out = []
    for item in TARGETS:
        if not item["geojson"].exists() or not item["validation"].exists():
            print("Omitido", item["name"], "— geometría/validación no disponible")
            continue
        validation = json.loads(item["validation"].read_text(encoding="utf-8"))
        status = str(validation.get("status", "")).upper()
        decision = validation.get("decision")
        topology = validation.get("topology_check", {}).get("status", "CONSISTENT")
        if status == "FAIL" or topology == "REVIEW" or decision == "do_not_use":
            print("Omitido", item["name"], "— no supera puerta geométrica:", status, decision, topology)
            continue
        feature = json.loads(item["geojson"].read_text(encoding="utf-8"))
        geom = shape(feature["geometry"]).buffer(0)
        out.append({**item, "validation_data": validation, "geom": geom})
    return out


def accumulate(series, n):
    vals = [x["rain_mm"] for x in series if x.get("rain_mm") is not None]
    return round(sum(vals[-n:]), 2) if len(vals) >= n else None


def delta(a, b):
    return None if a is None or b is None else round(a - b, 2)


def main():
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("Falta EARTHDATA_TOKEN")
    targets = eligible_targets()
    if not targets:
        print("No hay polígonos elegibles. latest.json no cambia.")
        return 0

    earthaccess.login(strategy="environment")
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=12)
    granules = []
    product_version = "auto"
    for version in ("08", "07"):
        try:
            granules = earthaccess.search_data(
                short_name="GPM_3IMERGDL",
                version=version,
                temporal=(start.isoformat(), end.isoformat()),
                count=30,
            )
            if granules:
                product_version = version
                break
        except Exception as exc:
            print("Búsqueda IMERG", version, "falló:", exc)
    if not granules:
        granules = earthaccess.search_data(
            short_name="GPM_3IMERGDL",
            temporal=(start.isoformat(), end.isoformat()),
            count=30,
        )
    if not granules:
        raise RuntimeError("Sin gránulos IMERG para comparación poligonal")

    series = {t["zone_id"]: [] for t in targets}
    with tempfile.TemporaryDirectory(prefix="irfen_polygon_imerg_") as td:
        paths = earthaccess.download(granules, local_path=td, threads=4, show_progress=False)
        for path in sorted(paths):
            d = date_from_name(path)
            if not d:
                continue
            try:
                lat, lon, p = read_grid(path)
            except Exception as exc:
                print("Granulo omitido", path, exc)
                continue
            for t in targets:
                value, sampling = polygon_mean(t["geom"], lat, lon, p)
                series[t["zone_id"]].append({
                    "date": d,
                    "rain_mm": None if value is None else round(value, 2),
                    "sampling": sampling,
                })

    data = json.loads(LATEST.read_text(encoding="utf-8"))
    zone_map = {z["id"]: z for z in data.get("zones", [])}
    summaries = []
    for t in targets:
        zid = t["zone_id"]
        if zid not in zone_map:
            print("Zona no presente en latest.json:", zid)
            continue
        dedup = {x["date"]: x for x in series[zid]}
        ordered = [dedup[k] for k in sorted(dedup)]
        p24, p72, p7d = accumulate(ordered, 1), accumulate(ordered, 3), accumulate(ordered, 7)
        zone = zone_map[zid]
        zone["experimental_polygon"] = {
            "status": "parallel_validation_only",
            "production_use": False,
            "product": "NASA GPM IMERG Late Daily",
            "product_version": product_version,
            "geometry": str(t["geojson"].relative_to(ROOT / "site")).replace("\\", "/"),
            "validation_status": t["validation_data"].get("status"),
            "method": "IMERG por solape de celdas ponderado por área de intersección con polígono DEM",
            "rain24": p24,
            "rain72": p72,
            "rain7d": p7d,
            "delta_vs_operational_bbox_mm": {
                "rain24": delta(p24, zone.get("rain24")),
                "rain72": delta(p72, zone.get("rain72")),
                "rain7d": delta(p7d, zone.get("rain7d")),
            },
            "series": ordered[-14:],
            "warning": "Dato experimental; no modifica amenaza, prioridad ni alertas.",
        }
        summaries.append({"zone_id": zid, "rain24": p24, "rain72": p72, "rain7d": p7d})

    LATEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Comparación poligonal actualizada:")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
