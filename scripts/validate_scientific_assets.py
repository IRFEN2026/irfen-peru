#!/usr/bin/env python3
"""Puertas automáticas de seguridad científica para IRFEN v0.8.

Falla CI si un activo experimental viola invariantes básicos, pero nunca cambia
la lógica operativa por sí mismo.
"""
from pathlib import Path
import json
import sys

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ERRORS = []
WARNINGS = []


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"JSON inválido {path}: {exc}")
        return None


def check_watershed(zone_id, geo_name, val_name):
    gp = SITE / "data" / "watersheds" / geo_name
    vp = SITE / "data" / "watersheds" / val_name
    if not gp.exists() or not vp.exists():
        WARNINGS.append(f"{zone_id}: activos de cuenca aún no disponibles")
        return
    geo = load(gp)
    val = load(vp)
    if not geo or not val:
        return
    try:
        geom = shape(geo["geometry"])
        if geom.is_empty or not geom.is_valid:
            ERRORS.append(f"{zone_id}: GeoJSON vacío o inválido")
    except Exception as exc:
        ERRORS.append(f"{zone_id}: geometría no legible: {exc}")

    if geo.get("properties", {}).get("production_ready") is not False:
        ERRORS.append(f"{zone_id}: el polígono v0.8 debe seguir production_ready=false")
    if val.get("production_ready") is not False:
        ERRORS.append(f"{zone_id}: la validación v0.8 debe seguir production_ready=false")

    status = str(val.get("status", "")).upper()
    err = val.get("relative_area_error_pct")
    if status == "PASS" and (err is None or float(err) > 15.0):
        ERRORS.append(f"{zone_id}: PASS incompatible con error de área {err}%")
    if status == "REVIEW" and err is not None and float(err) <= 15.0:
        WARNINGS.append(f"{zone_id}: REVIEW pese a error de área <=15%; revisar otras puertas")

    topo = val.get("topology_check")
    if topo and status == "PASS" and topo.get("status") != "CONSISTENT":
        ERRORS.append(f"{zone_id}: PASS con topología no consistente")

    if val.get("decision") == "candidate_for_hydraulic_review":
        hyd = val.get("hydraulic_context") or val.get("hydraulic_context_2026") or {}
        if not hyd or "REQUIRED" not in str(hyd.get("status", "")):
            ERRORS.append(f"{zone_id}: falta puerta hidráulica requerida")


def check_latest_contract():
    p = SITE / "data" / "latest.json"
    data = load(p)
    if not data:
        return
    for z in data.get("zones", []):
        exp = z.get("experimental_polygon")
        if exp and exp.get("production_use") is not False:
            ERRORS.append(f"{z.get('id')}: experimental_polygon no puede ser production_use=true")


def check_history_contract():
    p = SITE / "data" / "history.json"
    data = load(p)
    if not data:
        return
    for e in data.get("events", []):
        exp = e.get("experimental_polygon")
        if exp and exp.get("production_use") is not False:
            ERRORS.append(f"{e.get('id')}: comparación histórica experimental no puede ser productiva")


def check_frontend_contract():
    p = SITE / "index.html"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    # La función calc operativa no debe consumir campos experimentales.
    start = text.find("function calc(z)")
    end = text.find("function bar(", start)
    block = text[start:end] if start >= 0 and end > start else ""
    if not block:
        ERRORS.append("No se pudo localizar function calc(z) para validar contrato operativo")
    elif "experimental_polygon" in block or "forecast" in block:
        ERRORS.append("La función operativa calc(z) está consumiendo campos experimentales")


def check_manifest():
    p = SITE / "data" / "scientific_status.json"
    data = load(p)
    if not data:
        return
    for z in data.get("zones", []):
        if z.get("production_ready") is not False:
            ERRORS.append(f"Manifest {z.get('id')}: production_ready debe ser false en v0.8")


def main():
    check_watershed("san_ildefonso", "san_ildefonso_watershed.geojson", "san_ildefonso_validation.json")
    check_watershed("chosica", "huaycoloro_watershed.geojson", "huaycoloro_validation.json")
    check_latest_contract()
    check_history_contract()
    check_frontend_contract()
    check_manifest()

    for warning in WARNINGS:
        print("WARNING:", warning)
    if ERRORS:
        for error in ERRORS:
            print("ERROR:", error)
        print(f"Validación científica FALLÓ: {len(ERRORS)} error(es)")
        return 1
    print(f"Validación científica OK · {len(WARNINGS)} advertencia(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
