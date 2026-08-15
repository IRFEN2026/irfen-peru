#!/usr/bin/env python3
"""Recupera pronósticos GEOS-CF ya emitidos para validación en sombra IRFEN.

El backfill consulta el agregado histórico oficial OPeNDAP y descarga únicamente
el rectángulo mínimo de celdas que cubre los tres pilotos. Sólo conserva totales
de días UTC con 24 horas completas; la evidencia queda separada de la operación,
con ``production_use=false`` y sin calcular umbrales, correcciones ni alertas.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import re
from pathlib import Path
from urllib.parse import quote

import numpy as np
import requests
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "forecast" / "historical_daily.json"
ZONES = ROOT / "config" / "zones.json"
POLYGONS = {
    "san_ildefonso": ROOT / "site" / "data" / "watersheds" / "san_ildefonso_watershed.geojson",
    "chosica": ROOT / "site" / "data" / "watersheds" / "huaycoloro_watershed.geojson",
}
COLLECTION = "met_tavg_1hr_glo_L1440x721_slv"
BASE = f"https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/v2/fcst/{COLLECTION}"
MAX_ISSUES = 120
GRID_LAT = np.arange(-90.0, 90.0001, 0.25)
GRID_LON = np.arange(-180.0, 180.0, 0.25)


def normalize_lon(value):
    return ((float(value) + 180.0) % 360.0) - 180.0


def polygon_cell_weights(geom, lat, lon):
    dlat = float(np.nanmedian(np.abs(np.diff(lat))))
    dlon = float(np.nanmedian(np.abs(np.diff(lon))))
    lon_norm = np.array([normalize_lon(x) for x in lon])
    minx, miny, maxx, maxy = geom.bounds
    yi = np.where((lat >= miny - dlat / 2) & (lat <= maxy + dlat / 2))[0]
    xi = np.where((lon_norm >= minx - dlon / 2) & (lon_norm <= maxx + dlon / 2))[0]
    cells = []
    for row in yi:
        for col in xi:
            x, y = lon_norm[col], float(lat[row])
            grid_cell = box(x - dlon / 2, y - dlat / 2, x + dlon / 2, y + dlat / 2)
            intersection = geom.intersection(grid_cell)
            if intersection.is_empty or intersection.area <= 0:
                continue
            weight = float(intersection.area) * max(np.cos(np.deg2rad(y)), 0.01)
            cells.append((int(row), int(col), weight))
    return cells


def target_specs():
    zones = json.loads(ZONES.read_text(encoding="utf-8"))["zones"]
    by_id = {zone["id"]: zone for zone in zones}
    specs = []
    for zone_id in ("san_ildefonso", "chosica"):
        feature = json.loads(POLYGONS[zone_id].read_text(encoding="utf-8"))
        specs.append({
            "zone_id": zone_id,
            "method": "validated_dem_polygon",
            "areas": [(shape(feature["geometry"]).buffer(0), 1.0)],
        })
    catacaos = by_id["catacaos"]
    specs.append({
        "zone_id": "catacaos",
        "method": "provisional_weighted_operational_sampling_areas",
        "areas": [
            (box(*area["bbox"]), float(area.get("weight", 1.0)))
            for area in catacaos.get("sampling_areas", [])
        ],
    })
    return specs


def build_weights(spec, lat, lon):
    groups = []
    for geom, area_weight in spec["areas"]:
        cells = polygon_cell_weights(geom, lat, lon)
        if cells:
            groups.append({"area_weight": area_weight, "cells": cells})
    return groups


def localize_groups(groups, row_pos, col_pos):
    return [
        {
            "area_weight": group["area_weight"],
            "cells": [
                (row_pos[row], col_pos[col], weight)
                for row, col, weight in group["cells"]
                if row in row_pos and col in col_pos
            ],
        }
        for group in groups
    ]


def weighted_rate(field, groups):
    area_values, area_weights = [], []
    for group in groups:
        total_weight = total_value = 0.0
        for row, col, weight in group["cells"]:
            value = float(field[row, col])
            if np.isfinite(value):
                total_weight += weight
                total_value += weight * value
        if total_weight > 0:
            area_values.append(total_value / total_weight)
            area_weights.append(group["area_weight"])
    if not area_weights:
        return None
    return float(np.average(area_values, weights=area_weights))


def accumulation(hourly, hours):
    values = [row.get("precip_mm") for row in hourly[:hours]]
    if len(values) < hours or any(value is None for value in values):
        return None
    return round(float(sum(values)), 2)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def dataset_name(issue_date: date) -> str:
    return f"{COLLECTION}.{issue_date:%Y%m%d}_09z"


def parse_ascii_tprec(text: str, expected_shape: tuple[int, int, int]) -> np.ndarray:
    """Convierte una respuesta ASCII OPeNDAP acotada en un cubo t/y/x."""
    lines = text.splitlines()
    if not lines or text.lstrip().startswith("Error {"):
        raise RuntimeError("dataset OPeNDAP no disponible")
    dims = tuple(int(x) for x in re.findall(r"\[(\d+)\]", lines[0]))
    if dims != expected_shape:
        raise RuntimeError(f"forma OPeNDAP inesperada: {dims}; esperada: {expected_shape}")

    cube = np.full(expected_shape, np.nan, dtype=float)
    for line in lines[1:]:
        if line.startswith("time,"):
            break
        if not line.startswith("["):
            continue
        prefix, raw_values = line.split(",", 1)
        indices = [int(x) for x in re.findall(r"\[(\d+)\]", prefix)]
        if len(indices) != 2:
            raise RuntimeError(f"índice t/y inesperado: {prefix}")
        values = np.fromstring(raw_values, sep=",")
        if len(values) != expected_shape[2]:
            raise RuntimeError(f"fila OPeNDAP incompleta: {len(values)} valores")
        cube[indices[0], indices[1], :] = values

    if np.isnan(cube).all():
        raise RuntimeError("respuesta OPeNDAP sin valores tprec")
    cube[np.abs(cube) >= 1e14] = np.nan
    return cube


def get_ascii_cube(session, issue_date, row_min, row_max, col_min, col_max, timeout):
    dataset = dataset_name(issue_date)
    selection = f"tprec[0:1:119][{row_min}:1:{row_max}][{col_min}:1:{col_max}]"
    url = f"{BASE}/{dataset}.ascii?{quote(selection, safe='[]:')}"
    last_error = None
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=(15, timeout))
            unavailable_response = (
                response.status_code == 404
                or response.text.lstrip().startswith("Error {")
                or "GrADS Data Server - error" in response.text
            )
            if unavailable_response:
                raise FileNotFoundError(dataset)
            response.raise_for_status()
            return parse_ascii_tprec(
                response.text,
                (120, row_max - row_min + 1, col_max - col_min + 1),
            )
        except FileNotFoundError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                continue
    raise RuntimeError(f"falló OPeNDAP para {dataset}: {last_error}")


def prepare_targets():
    prepared = []
    needed_rows = set()
    needed_cols = set()
    for spec in target_specs():
        groups = build_weights(spec, GRID_LAT, GRID_LON)
        if not groups:
            raise RuntimeError(f"sin celdas GEOS para {spec['zone_id']}")
        prepared.append({**spec, "global_groups": groups})
        for group in groups:
            for row, col, _ in group["cells"]:
                needed_rows.add(row)
                needed_cols.add(col)

    expected = {"san_ildefonso", "chosica", "catacaos"}
    observed = {x["zone_id"] for x in prepared}
    if observed != expected:
        raise RuntimeError(f"pilotos incompletos: {sorted(observed)}")

    row_min, row_max = min(needed_rows), max(needed_rows)
    col_min, col_max = min(needed_cols), max(needed_cols)
    row_pos = {row: row - row_min for row in range(row_min, row_max + 1)}
    col_pos = {col: col - col_min for col in range(col_min, col_max + 1)}
    for spec in prepared:
        spec["groups"] = localize_groups(spec.pop("global_groups"), row_pos, col_pos)
    return prepared, row_min, row_max, col_min, col_max


def daily_records_from_cube(issue_date, cube, prepared, retrieved_at):
    issued = datetime.combine(issue_date, time(9), tzinfo=timezone.utc)
    first_valid = issued + timedelta(minutes=30)
    hourly_by_zone = {spec["zone_id"]: [] for spec in prepared}
    for hour, field in enumerate(cube):
        valid = first_valid + timedelta(hours=hour)
        for spec in prepared:
            rate = weighted_rate(field, spec["groups"])
            precip = None if rate is None else round(max(0.0, rate * 3600.0), 3)
            hourly_by_zone[spec["zone_id"]].append({
                "valid_time": iso_z(valid),
                "precip_mm": precip,
            })

    records = []
    for spec in prepared:
        hourly = hourly_by_zone[spec["zone_id"]]
        by_day = {}
        for row in hourly:
            day = row["valid_time"][:10]
            by_day.setdefault(day, []).append(row)
        for day, values in sorted(by_day.items()):
            unique = {row["valid_time"]: row["precip_mm"] for row in values}
            if len(unique) != 24 or any(value is None for value in unique.values()):
                continue
            day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            records.append({
                "zone_id": spec["zone_id"],
                "sampling_method": spec["method"],
                "issue_time": iso_z(issued),
                "retrieved_at": retrieved_at,
                "source_dataset": dataset_name(issue_date),
                "valid_date_utc": day,
                "lead_hours_to_day_start": round((day_start - issued).total_seconds() / 3600, 2),
                "hour_count": 24,
                "valid_time_first": min(unique),
                "valid_time_last": max(unique),
                "forecast_mm": round(float(sum(unique.values())), 3),
                "production_use": False,
            })
    return records


def load_evidence():
    if not OUT.exists():
        return {"version": "0.8-experimental", "production_use": False, "records": []}
    evidence = json.loads(OUT.read_text(encoding="utf-8"))
    if evidence.get("production_use") is not False:
        raise RuntimeError("la evidencia GEOS debe conservar production_use=false")
    return evidence


def date_range(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="fecha inicial YYYY-MM-DD")
    parser.add_argument("--end", help="fecha final YYYY-MM-DD; por defecto ayer UTC")
    parser.add_argument("--days", type=int, default=20, help="lookback si no se indica --start")
    parser.add_argument("--max-new", type=int, default=20, help="máximo de emisiones nuevas por corrida")
    parser.add_argument("--timeout", type=int, default=120, help="timeout de lectura por emisión")
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    end = date.fromisoformat(args.end) if args.end else today - timedelta(days=1)
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=max(args.days - 1, 0))
    if start > end or args.max_new < 1:
        raise SystemExit("rango o límite inválido")

    evidence = load_evidence()
    records = evidence.setdefault("records", [])
    existing = {row.get("source_dataset") for row in records if row.get("source_dataset")}
    prepared, row_min, row_max, col_min, col_max = prepare_targets()
    retrieved_at = iso_z(datetime.now(timezone.utc))
    added = []
    unavailable = []
    session = requests.Session()
    session.headers["User-Agent"] = "IRFEN-v0.8-shadow-validation/1.0"

    for issue_date in date_range(start, end):
        dataset = dataset_name(issue_date)
        if dataset in existing or len(added) >= args.max_new:
            continue
        try:
            cube = get_ascii_cube(
                session, issue_date, row_min, row_max, col_min, col_max, args.timeout
            )
        except FileNotFoundError:
            unavailable.append(dataset)
            continue
        records.extend(daily_records_from_cube(issue_date, cube, prepared, retrieved_at))
        existing.add(dataset)
        added.append(dataset)
        print("GEOS histórico agregado:", dataset)

    issue_order = sorted({row["source_dataset"] for row in records})[-MAX_ISSUES:]
    retained = set(issue_order)
    evidence["records"] = sorted(
        (row for row in records if row.get("source_dataset") in retained),
        key=lambda row: (row.get("issue_time") or "", row.get("valid_date_utc") or "", row.get("zone_id") or ""),
    )
    evidence["updated_at"] = retrieved_at
    evidence["source"] = "NASA GMAO GEOS-CF v2 historical OPeNDAP"
    evidence["collection"] = COLLECTION
    evidence["grid_resolution_deg"] = [0.25, 0.25]
    evidence["validation_goal"] = (
        "Comparar pronósticos realmente emitidos con IMERG observado; "
        "sin corrección de sesgo ni uso operativo."
    )
    evidence["historical_backfill"] = {
        "production_use": False,
        "source": "NASA GMAO GEOS-CF v2 OPeNDAP",
        "collection": COLLECTION,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "retrieved_at": retrieved_at,
        "added_count": len(added),
        "added_datasets": added,
        "unavailable_count": len(unavailable),
        "spatial_subset": {
            "lat_index": [row_min, row_max],
            "lon_index": [col_min, col_max],
            "cells_per_hour": (row_max - row_min + 1) * (col_max - col_min + 1),
        },
        "safety_gate": "TEST_ONLY; no thresholds, bias correction, alerts or production modifiers",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "added": len(added),
        "unavailable": len(unavailable),
        "issues_retained": len(issue_order),
        "daily_records": len(evidence["records"]),
        "production_use": evidence.get("production_use"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
