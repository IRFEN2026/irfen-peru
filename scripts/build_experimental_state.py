#!/usr/bin/env python3
"""Construye un estado experimental de decisión para IRFEN v0.8.

No genera alertas ni modifica la lógica operativa. Solo organiza observación,
forecast y puertas científicas para hacer pruebas reproducibles sin confundir
señales meteorológicas con respuesta hidráulica.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "data" / "experimental_state.json"


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def ratio(value, threshold):
    if value is None or threshold in (None, 0):
        return None
    return round(float(value) / float(threshold), 4)


def zone_observation(zone):
    exp = zone.get("experimental_polygon")
    if exp and exp.get("production_use") is False and zone.get("id") in {"san_ildefonso", "chosica"}:
        return {
            "method": "validated_dem_polygon_parallel",
            "rain24": exp.get("rain24"),
            "rain72": exp.get("rain72"),
            "rain7d": exp.get("rain7d"),
            "source_status": exp.get("status"),
        }
    return {
        "method": "operational_sampling_geometry",
        "rain24": zone.get("rain24"),
        "rain72": zone.get("rain72"),
        "rain7d": zone.get("rain7d"),
        "source_status": "operational_reference_only",
    }


def main():
    latest = load(SITE / "data" / "latest.json", {"zones": []}) or {"zones": []}
    forecast = load(SITE / "data" / "forecast" / "latest.json", {"zones": []}) or {"zones": []}
    hydraulics = load(SITE / "data" / "hydraulics" / "current_infrastructure.json", {"zones": []}) or {"zones": []}
    piura = load(SITE / "data" / "hydrology" / "piura_source_status.json", {}) or {}

    forecast_by = {z.get("zone_id"): z for z in forecast.get("zones", [])}
    hydraulic_by = {z.get("zone_id"): z for z in hydraulics.get("zones", [])}

    output = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "purpose": "Estado integrado para pruebas; no genera ni modifica alertas operativas.",
        "rules": {
            "no_composite_risk_score": True,
            "no_hydraulic_attenuation_without_calibration": True,
            "catacaos_requires_river_state": True,
            "threshold_crossings_are_test_signals_only": True,
        },
        "zones": [],
    }

    for zone in latest.get("zones", []):
        zid = zone.get("id")
        thresholds = zone.get("thresholds_provisional") or {}
        obs = zone_observation(zone)
        fc = forecast_by.get(zid, {})
        hyd = hydraulic_by.get(zid, {})

        observed_ratios = {
            "rain24": ratio(obs.get("rain24"), thresholds.get("rain24")),
            "rain72": ratio(obs.get("rain72"), thresholds.get("rain72")),
            "rain7d": ratio(obs.get("rain7d"), thresholds.get("rain7d")),
        }
        forecast_ratios = {
            "forecast24": ratio(fc.get("forecast24_mm"), thresholds.get("rain24")),
            "forecast72": ratio(fc.get("forecast72_mm"), thresholds.get("rain72")),
        }

        observed_crossings = [k for k, v in observed_ratios.items() if v is not None and v >= 1.0]
        forecast_crossings = [k for k, v in forecast_ratios.items() if v is not None and v >= 1.0]

        gate = (hyd.get("scientific_gate") or {}).get("status")
        modifier = hyd.get("production_modifier")

        if zid == "catacaos":
            river_available = bool((piura.get("senamhi") or {}).get("numeric_river_state_available"))
            readiness = "METEO_TESTABLE_RIVER_GATE_BLOCKED" if not river_available else "RESEARCH_INTEGRATION_READY"
            blockers = [] if river_available else ["numeric_river_state_required"]
            blockers.append("floodplain_and_current_channel_capacity_validation_required")
        else:
            river_available = None
            readiness = "METEO_TESTABLE_HYDRAULIC_GATE_BLOCKED" if gate else "METEO_TESTABLE"
            blockers = ["hydraulic_calibration_required"] if gate else []

        output["zones"].append({
            "zone_id": zid,
            "name": zone.get("name"),
            "production_use": False,
            "observation": obs,
            "thresholds_provisional": thresholds,
            "observed_threshold_ratios": observed_ratios,
            "observed_threshold_crossings": observed_crossings,
            "forecast": {
                "status": forecast.get("status"),
                "sampling_method": fc.get("sampling_method"),
                "forecast24_mm": fc.get("forecast24_mm"),
                "forecast72_mm": fc.get("forecast72_mm"),
                "available_future_hours": fc.get("available_future_hours"),
                "threshold_ratios": forecast_ratios,
                "threshold_crossings": forecast_crossings,
            },
            "hydraulic_gate": {
                "status": gate,
                "production_modifier": modifier,
                "system_status": hyd.get("system_status"),
            },
            "river_state_available": river_available,
            "readiness": readiness,
            "blockers": blockers,
            "interpretation": (
                "Cruces de umbral y forecast son señales de prueba. No equivalen a alerta mientras existan puertas hidráulicas/hidrológicas pendientes."
            ),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
