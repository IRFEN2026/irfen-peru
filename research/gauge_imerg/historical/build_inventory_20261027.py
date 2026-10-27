#!/usr/bin/env python3
"""Inventario offline (RESEARCH_ONLY): estaciones automáticas GBON/RBON del norte con identidad y coordenadas de
WMO OSCAR/Surface, y solapamiento con los campos IMERG de píxel ya archivados en el repositorio.

Entradas, todas ya versionadas, sin red:
* ``retrieval/output_20261026/raw_metadata/oscar_search_PER.json``: respuesta de OSCAR del 26-oct (HTTP 200);
* ``historical/open_data_20261027/download_log.json``: intento único de descarga del conjunto abierto de SENAMHI;
* campos IMERG Late diarios de 0,1° en la rama ``v09/forecast-data`` (``data/v09/obs_imerg/fields/*.npz``), leídos
  con ``git show`` si la rama está disponible localmente.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))
from irfen_gauge_imerg.grid import locate  # noqa: E402

OSCAR = PKG / "retrieval/output_20261026/raw_metadata/oscar_search_PER.json"
DL_LOG = HERE / "open_data_20261027/download_log.json"
NORTH = {"lat": (-7.3, -3.2), "lon_max": -78.8}  # Tumbes, Piura, Lambayeque y bordes de Cajamarca


def precision_deg(x: float) -> tuple[float, str]:
    """Precisión declarada: grados y minutos enteros (valor·60 entero) o número de decimales impresos."""
    s = repr(abs(float(x)))
    frac = s.split(".")[1] if "." in s else ""
    if len(frac) >= 5 and abs(abs(x) * 60 - round(abs(x) * 60)) < 1e-6:
        return round(1 / 60, 4), "ARCMIN"
    return float(Decimal(1).scaleb(-len(frac))) if frac else 1.0, f"{len(frac)}_DECIMALS"


def edge_margin_deg(x: float) -> float:
    """Distancia al borde de celda IMERG más cercano (bordes en múltiplos de 0,1°)."""
    r = (abs(x) * 10) % 1
    return round(min(r, 1 - r) / 10, 6)


def fields_from_git(ref: str = "origin/v09/forecast-data") -> list[dict]:
    try:
        names = [n.rsplit("/", 1)[-1] for n in subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", ":(top)data/v09/obs_imerg/fields"], text=True, cwd=PKG).split()]
    except subprocess.CalledProcessError:
        return []
    import numpy as np
    out = []
    for n in names:
        blob = subprocess.check_output(["git", "show", f"{ref}:data/v09/obs_imerg/fields/{n}"], cwd=PKG)
        z = np.load(io.BytesIO(blob), allow_pickle=False)
        out.append({"file": n, "rain_day_peru": n[:-4], "lat_range": [float(z["lat"].min()), float(z["lat"].max())],
                    "lon_range": [float(z["lon"].min()), float(z["lon"].max())],
                    "half_hours_valid_min": int(z["valid"].min()), "granules": len(z["granules"]),
                    "first_granule_utc": str(z["granules"][0]), "product": "IMERG Late V07 (GPM_3IMERGHHL), suma 07–07"})
    return out


def main():
    raw = json.loads(OSCAR.read_text(encoding="utf-8"))
    items = raw["stationSearchResults"]
    stations = []
    for it in items:
        la, lo = float(it["latitude"]), float(it["longitude"])
        if not (NORTH["lat"][0] <= la <= NORTH["lat"][1] and lo <= NORTH["lon_max"]):
            continue
        if it.get("stationTypeCode") != "landOceanSurface":
            continue
        p, kind = max(precision_deg(la), precision_deg(lo))
        margin = min(edge_margin_deg(la), edge_margin_deg(lo))
        cell, flags = locate(la, lo)
        progs = it.get("stationProgramsDeclaredStatuses", "")
        stations.append({
            "name": it["name"], "wigos_primary": it["wigosId"],
            "wigos_all": [w["wigosStationIdentifier"] for w in it.get("wigosStationIdentifiers", [])],
            "lat": la, "lon": lo, "elevation_m": it.get("elevation"), "coordinate_precision_deg": p,
            "coordinate_precision_kind": kind, "declared_status": it.get("declaredStatus"),
            "programs": progs, "gbon_or_rbon": ("GBON" in progs) or ("RBON" in progs),
            "automatic_network_wigos_0_604": it["wigosId"].startswith("0-604-"),
            "date_established": it.get("dateEstablished"),
            "imerg_cell": {"i_lon": cell.i, "j_lat": cell.j, "lon_center": cell.lon_center, "lat_center": cell.lat_center},
            "location_flags": flags,
            "edge_margin_deg": margin,
            # asignable si la precisión es ≤ 0,02° y el punto está a más de media precisión del borde de la celda
            "pixel_assignable": (p <= 0.02 and not flags and margin > p / 2),
            "source": "WMO OSCAR/Surface, búsqueda territoryName=PER, 26-oct-2026 22:53 UTC (HTTP 200)",
        })
    stations.sort(key=lambda s: -s["lat"])
    dl = json.loads(DL_LOG.read_text(encoding="utf-8"))
    fields = fields_from_git()
    doc = {
        "schema": "irfen.gauge_imerg.historical_inventory", "schema_version": "1.0.0",
        "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
        "stations_north": stations,
        "open_dataset": {
            "title": dl["dataset"], "page": "https://www.datosabiertos.gob.pe/dataset/"
                     "variables-meteorologicas-de-las-estaciones-autom%C3%A1ticas-de-intercambio-internacional-servicio",
            "ckan_metadata_created": "2024-05-31 22:50 (Vie, 05/31/2024)", "ckan_metadata_modified": "2025-09-08 16:27",
            "csv_size_declared": "48.14 MB", "license": "ODC-BY",
            "declared_fields": ["nombre", "latitud", "longitud", "altitud", "departamento", "provincia", "distrito",
                                "ubigeo", "red", "fecha", "hora", "temperatura", "humedad relativa", "precipitación (mm)"],
            "declared_quality": "datos horarios validados (sin método descrito); filtrar registros vacíos",
            "not_declared": ["cobertura temporal", "zona horaria de 'hora'", "periodo de acumulación de la precipitación",
                             "códigos de faltante"],
            "download_attempt": {k: {kk: v.get(kk) for kk in ("url", "http_status", "bytes", "sha256", "requested_at_utc")}
                                 for k, v in dl["files"].items()},
            "status": "BLOCKED_BY_PROVIDER" if all(v.get("http_status") != 200 for v in dl["files"].values()) else "OK",
        },
        "archived_imerg_pixel_fields": fields,
        "overlap": {
            "instrument_records_available": 0,
            "archived_pixel_imerg_days": [f["rain_day_peru"] for f in fields],
            "real_overlap_pairs": 0,
            "reason": "No se obtuvo ningún registro instrumental. Además, el conjunto abierto se modificó por última vez el "
                      "2025-09-08, antes de los únicos campos IMERG de píxel archivados (días pluviométricos completos 2026-10-09 a 2026-10-13).",
        },
    }
    out = HERE / "inventory_north_gbon_rbon_20261027.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for s in stations:
        print(f"{s['name']:20s} {s['wigos_primary']:20s} {s['lat']:>11} {s['lon']:>11} ±{s['coordinate_precision_deg']}° "
              f"{'RBON/GBON' if s['gbon_or_rbon'] else '-':9s} {s['declared_status']:12s} píxel={'sí' if s['pixel_assignable'] else 'NO'}")
    print("campos IMERG de píxel archivados:", [f["rain_day_peru"] for f in fields])


if __name__ == "__main__":
    main()
