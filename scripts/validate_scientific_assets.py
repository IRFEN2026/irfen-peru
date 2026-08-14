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


def check_forecast_contract():
    p = SITE / "data" / "forecast" / "latest.json"
    if not p.exists():
        WARNINGS.append("forecast: dataset experimental aún no disponible")
        return
    data = load(p)
    if not data:
        return
    if data.get("production_use") is not False:
        ERRORS.append("forecast: production_use debe permanecer false")
    if data.get("status") != "experimental_forecast_available":
        WARNINGS.append(f"forecast: estado inesperado {data.get('status')}")
    for z in data.get("zones", []):
        for key in ("forecast24_mm", "forecast72_mm", "forecast120_mm"):
            v = z.get(key)
            if v is not None and float(v) < 0:
                ERRORS.append(f"forecast {z.get('zone_id')}: {key} negativo")
        if z.get("zone_id") == "catacaos" and z.get("sampling_method") != "provisional_weighted_operational_sampling_areas":
            ERRORS.append("Catacaos: el forecast aún debe mantenerse espacialmente provisional hasta tener modelo fluvial")


def check_hydraulic_inventory():
    p = SITE / "data" / "hydraulics" / "current_infrastructure.json"
    if not p.exists():
        WARNINGS.append("hydraulics: inventario de infraestructura aún no disponible")
        return
    data = load(p)
    if not data:
        return
    if data.get("production_use") is not False:
        ERRORS.append("hydraulics: production_use debe permanecer false")
    zones = data.get("zones", [])
    expected = {"san_ildefonso", "chosica", "catacaos"}
    present = {z.get("zone_id") for z in zones}
    missing = expected - present
    if missing:
        ERRORS.append(f"hydraulics: faltan zonas {sorted(missing)}")
    for z in zones:
        zid = z.get("zone_id")
        if z.get("production_modifier") is not None:
            ERRORS.append(f"hydraulics {zid}: production_modifier debe ser null hasta calibración")
        gate = z.get("scientific_gate") or {}
        if not gate.get("status"):
            ERRORS.append(f"hydraulics {zid}: falta scientific_gate.status")
        effect = z.get("hydrologic_effect") or {}
        if effect.get("numeric_attenuation_factor") is not None:
            ERRORS.append(f"hydraulics {zid}: numeric_attenuation_factor debe ser null sin calibración")
        if zid in {"san_ildefonso", "chosica"} and "HYDRAULIC_CALIBRATION_REQUIRED" not in str(gate.get("status", "")):
            ERRORS.append(f"hydraulics {zid}: debe mantener puerta HYDRAULIC_CALIBRATION_REQUIRED")
        if zid == "catacaos" and "RIVER_STATE_REQUIRED" not in str(gate.get("status", "")):
            ERRORS.append("hydraulics catacaos: debe mantener puerta RIVER_STATE_REQUIRED")


def check_experimental_state():
    p = SITE / "data" / "experimental_state.json"
    if not p.exists():
        ERRORS.append("experimental_state: archivo requerido no generado")
        return
    data = load(p)
    if not data:
        return
    if data.get("production_use") is not False:
        ERRORS.append("experimental_state: production_use debe permanecer false")
    rules = data.get("rules") or {}
    for key in (
        "no_composite_risk_score",
        "no_hydraulic_attenuation_without_calibration",
        "catacaos_requires_river_state",
        "threshold_crossings_are_test_signals_only",
    ):
        if rules.get(key) is not True:
            ERRORS.append(f"experimental_state: regla {key} debe ser true")
    expected = {"san_ildefonso", "chosica", "catacaos"}
    zones = data.get("zones", [])
    present = {z.get("zone_id") for z in zones}
    if expected - present:
        ERRORS.append(f"experimental_state: faltan zonas {sorted(expected - present)}")
    forbidden = {"alert", "alert_level", "final_alert", "operational_alert", "production_score"}
    for z in zones:
        zid = z.get("zone_id")
        if z.get("production_use") is not False:
            ERRORS.append(f"experimental_state {zid}: production_use debe ser false")
        if forbidden.intersection(z.keys()):
            ERRORS.append(f"experimental_state {zid}: contiene campos de alerta operativa prohibidos")
        if (z.get("hydraulic_gate") or {}).get("production_modifier") is not None:
            ERRORS.append(f"experimental_state {zid}: no puede aplicar modificador hidráulico")
        if zid == "catacaos" and z.get("river_state_available") is not True:
            blockers = set(z.get("blockers") or [])
            if "numeric_river_state_required" not in blockers:
                ERRORS.append("experimental_state catacaos: debe bloquearse sin estado numérico del río")


def check_frontend_contract():
    p = SITE / "index.html"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    start = text.find("function calc(z)")
    end = text.find("function bar(", start)
    block = text[start:end] if start >= 0 and end > start else ""
    if not block:
        ERRORS.append("No se pudo localizar function calc(z) para validar contrato operativo")
    elif "experimental_polygon" in block or "forecast" in block or "hydraulic" in block or "experimental_state" in block:
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
    check_forecast_contract()
    check_hydraulic_inventory()
    check_experimental_state()
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
