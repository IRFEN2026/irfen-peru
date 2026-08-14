#!/usr/bin/env python3
"""Genera un forecast experimental de precipitación para IRFEN desde GEOS-CF v2.

El resultado se guarda aparte de latest.json para impedir que el pronóstico de
investigación altere accidentalmente la amenaza o prioridad operativa.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import xarray as xr
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STORE = "s3://smce-geos-cf-public/geos-cf-v2-fcst-latest.zarr"
OUT = SITE / "data" / "forecast" / "latest.json"
ZONES = ROOT / "config" / "zones.json"

POLYGONS = {
    "san_ildefonso": SITE / "data" / "watersheds" / "san_ildefonso_watershed.geojson",
    "chosica": SITE / "data" / "watersheds" / "huaycoloro_watershed.geojson",
}


def normalize_lon(value):
    return ((float(value) + 180.0) % 360.0) - 180.0


def grid_step(values):
    vals = np.asarray(values, dtype=float)
    return float(np.nanmedian(np.abs(np.diff(vals))))


def polygon_cell_weights(geom, lat, lon):
    dlat = grid_step(lat)
    dlon = grid_step(lon)
    lon_norm = np.array([normalize_lon(x) for x in lon])
    minx, miny, maxx, maxy = geom.bounds
    yi = np.where((lat >= miny - dlat / 2) & (lat <= maxy + dlat / 2))[0]
    xi = np.where((lon_norm >= minx - dlon / 2) & (lon_norm <= maxx + dlon / 2))[0]
    cells = []
    for r in yi:
        for c in xi:
            x = lon_norm[c]
            y = float(lat[r])
            cell = box(x - dlon / 2, y - dlat / 2, x + dlon / 2, y + dlat / 2)
            inter = geom.intersection(cell)
            if inter.is_empty or inter.area <= 0:
                continue
            # Corrección aproximada por convergencia de meridianos.
            weight = float(inter.area) * max(np.cos(np.deg2rad(y)), 0.01)
            cells.append((int(r), int(c), weight))
    return cells, dlat, dlon


def target_specs():
    zones = json.loads(ZONES.read_text(encoding="utf-8"))["zones"]
    by_id = {z["id"]: z for z in zones}
    specs = []
    for zid in ("san_ildefonso", "chosica"):
        path = POLYGONS[zid]
        if path.exists():
            feature = json.loads(path.read_text(encoding="utf-8"))
            specs.append({
                "zone_id": zid,
                "name": by_id[zid]["name"],
                "method": "validated_dem_polygon",
                "areas": [(shape(feature["geometry"]).buffer(0), 1.0)],
            })
    cat = by_id.get("catacaos")
    if cat:
        areas = []
        for item in cat.get("sampling_areas", []):
            west, south, east, north = item["bbox"]
            areas.append((box(west, south, east, north), float(item.get("weight", 1.0))))
        if areas:
            specs.append({
                "zone_id": "catacaos",
                "name": cat["name"],
                "method": "provisional_weighted_operational_sampling_areas",
                "areas": areas,
            })
    return specs


def build_weights(spec, lat, lon):
    groups = []
    dlat = dlon = None
    for geom, area_weight in spec["areas"]:
        cells, dlat, dlon = polygon_cell_weights(geom, lat, lon)
        if cells:
            groups.append({"area_weight": area_weight, "cells": cells})
    return groups, dlat, dlon


def weighted_rate(field, groups):
    area_values = []
    area_weights = []
    for group in groups:
        sw = sv = 0.0
        for r, c, w in group["cells"]:
            value = float(field[r, c])
            if np.isfinite(value):
                sw += w
                sv += w * value
        if sw > 0:
            area_values.append(sv / sw)
            area_weights.append(group["area_weight"])
    if not area_weights:
        return None
    return float(np.average(area_values, weights=area_weights))


def accumulation(hourly, hours):
    vals = [x["precip_mm"] for x in hourly[:hours] if x.get("precip_mm") is not None]
    if len(vals) < hours:
        return None
    return round(float(sum(vals)), 2)


def main():
    ds = xr.open_zarr(STORE, storage_options={"anon": True}, consolidated=None)
    if "tprec" not in ds:
        raise RuntimeError("GEOS-CF público no contiene tprec")

    da = ds["tprec"]
    units = str(da.attrs.get("units", ""))
    lat = np.asarray(ds["lat"].values, dtype=float)
    lon = np.asarray(ds["lon"].values, dtype=float)
    times = np.asarray(ds["time"].values).astype("datetime64[ns]")
    if len(times) < 2:
        raise RuntimeError("Forecast GEOS sin eje temporal suficiente")

    step_seconds = int(round(float(np.median(np.diff(times).astype("timedelta64[s]").astype(float)))))
    if not 1800 <= step_seconds <= 10800:
        raise RuntimeError(f"Paso temporal GEOS inesperado: {step_seconds}s")

    now64 = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns")
    future_idx = np.where(times > now64)[0]
    # Si el ciclo está justo actualizándose, conservar todos los pasos futuros existentes.
    if not len(future_idx):
        raise RuntimeError("El dataset GEOS público no contiene horas futuras respecto de la ejecución")

    specs = target_specs()
    prepared = []
    for spec in specs:
        groups, dlat, dlon = build_weights(spec, lat, lon)
        if not groups:
            print("Zona omitida sin celdas GEOS:", spec["zone_id"])
            continue
        prepared.append({**spec, "groups": groups})

    results = {s["zone_id"]: [] for s in prepared}
    # Cargamos solo lat/lon necesarios por zona de manera sencilla. Son 120 pasos
    # y pocos cientos de celdas; el acceso sigue siendo muy pequeño frente al globo.
    for idx in future_idx:
        field = np.asarray(da.isel(time=int(idx)).values, dtype=float)
        valid_time = str(times[idx]).replace(".000000000", "Z")
        for spec in prepared:
            rate = weighted_rate(field, spec["groups"])
            mm = None if rate is None else max(0.0, rate * step_seconds)
            results[spec["zone_id"]].append({
                "valid_time": valid_time,
                "precip_mm": None if mm is None else round(mm, 3),
            })

    zone_payload = []
    for spec in prepared:
        hourly = results[spec["zone_id"]]
        zone_payload.append({
            "zone_id": spec["zone_id"],
            "name": spec["name"],
            "sampling_method": spec["method"],
            "forecast24_mm": accumulation(hourly, 24),
            "forecast72_mm": accumulation(hourly, 72),
            "forecast120_mm": accumulation(hourly, 120),
            "available_future_hours": len(hourly),
            "valid_from": hourly[0]["valid_time"] if hourly else None,
            "valid_to": hourly[-1]["valid_time"] if hourly else None,
            "hourly": hourly[:120],
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NASA GMAO GEOS-CF v2",
        "store": STORE,
        "variable": "tprec",
        "variable_long_name": str(da.attrs.get("long_name", "total_precipitation")),
        "units_source": units,
        "integration": f"tprec × {step_seconds} s; 1 kg m-2 = 1 mm de agua",
        "grid_resolution_deg": [round(grid_step(lat), 4), round(grid_step(lon), 4)],
        "dataset_time_start": str(times[0]),
        "dataset_time_end": str(times[-1]),
        "production_use": False,
        "status": "experimental_forecast_available",
        "warning": "Pronóstico NASA GEOS-CF de investigación. No modifica amenaza, prioridad ni alertas IRFEN. Debe validarse contra observaciones antes de cualquier uso operativo.",
        "zones": zone_payload,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "zones"}, ensure_ascii=False, indent=2))
    for z in zone_payload:
        print(z["zone_id"], "24h=", z["forecast24_mm"], "72h=", z["forecast72_mm"], "horas=", z["available_future_hours"])
    ds.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
