#!/usr/bin/env python3
"""Construye reanálisis IMERG Early fail-closed para eventos Phase 2.

Los acumulados 3/6/24 h solo se publican cuando cada intervalo de 30 minutos
está presente. Una serie parcial conserva cobertura y huecos, pero nunca se
interpreta como lluvia baja, validación local, umbral ni activación.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTAKE_DIR = ROOT / "site/data/validation/phase2_event_intake"
ARCHIVE_PATH = ROOT / "site/data/calibration/imerg_early_live_archive.json"
OUT_PATH = ROOT / "site/data/phase2/event_reanalysis.json"
WINDOWS_HOURS = (3, 6, 24)
STEP = timedelta(minutes=30)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp sin zona horaria: {value}")
    return parsed.astimezone(timezone.utc)


def target_series(archive, target_id):
    by_time = {}
    for granule in archive.get("granules") or []:
        timestamp = parse_time(granule.get("time_utc"))
        target = next(
            (row for row in granule.get("targets") or [] if row.get("target_id") == target_id),
            None,
        )
        if not target or target.get("accum_30min_mm") is None:
            continue
        by_time[timestamp] = {
            "accum_30min_mm": float(target["accum_30min_mm"]),
            "rate_mm_hr": target.get("rate_mm_hr"),
            "valid_cells": target.get("valid_cells"),
        }
    return by_time


def build_window(series, occurrence_utc, hours):
    start = occurrence_utc - timedelta(hours=hours)
    required = hours * 2
    expected = [start + index * STEP for index in range(required)]
    available = [timestamp for timestamp in expected if timestamp in series]
    missing = [timestamp for timestamp in expected if timestamp not in series]
    complete = len(available) == required
    partial = round(sum(series[t]["accum_30min_mm"] for t in available), 3) if available else None
    return {
        "window_hours": hours,
        "start_utc": start.isoformat(),
        "end_utc_exclusive": occurrence_utc.isoformat(),
        "required_half_hour_samples": required,
        "available_half_hour_samples": len(available),
        "coverage_pct": round(100.0 * len(available) / required, 1),
        "continuous": complete,
        "accum_mm": partial if complete else None,
        "partial_accum_mm_non_decisional": None if complete else partial,
        "missing_slots_utc": [timestamp.isoformat() for timestamp in missing],
        "interpretation": (
            "Acumulado satelital completo; todavía requiere corroboración local y no valida umbrales."
            if complete
            else "Serie incompleta: el acumulado no es interpretable y la ausencia de datos no implica bajo riesgo."
        ),
    }


def blocked_item(row, status, reason):
    location = row.get("reported_location") or {}
    event = row.get("reported_event") or {}
    return {
        "event_id": row.get("event_id"),
        "status": status,
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "decision_use": "TEST_ONLY",
        "local_validation": False,
        "counts_toward_v08_closeout": False,
        "operational_zone_activation": False,
        "research_role": row.get("research_role"),
        "is_huaico_or_torrent_event": row.get("is_huaico_or_torrent_event"),
        "can_train_zone_activation_model": row.get("can_train_zone_activation_model"),
        "reported_date_local": event.get("reported_date_local"),
        "feature_name": location.get("feature_name"),
        "windows": {},
        "blocker": reason,
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    }


def build_event(row, archive):
    verification = row.get("verification") or {}
    analysis = row.get("analysis") or {}
    if verification.get("event_confirmed") is not True:
        return blocked_item(row, "BLOCKED_UNVERIFIED_EVENT", "Falta confirmación oficial completa del evento.")
    if analysis.get("status") != "READY_FOR_REANALYSIS":
        return blocked_item(row, "BLOCKED_EVENT_NOT_READY", "La identidad o geometría de análisis aún no está lista.")

    occurrence = parse_time((row.get("reported_event") or {}).get("occurrence_time_local"))
    target_id = f"phase2_event:{row['event_id']}"
    series = target_series(archive, target_id)
    windows = {f"{hours}h": build_window(series, occurrence, hours) for hours in WINDOWS_HOURS}
    complete_count = sum(window["continuous"] for window in windows.values())
    available_count = sum(window["available_half_hour_samples"] for window in windows.values())
    if complete_count == len(WINDOWS_HOURS):
        status = "COMPLETE_SATELLITE_REANALYSIS"
        blocker = None
    elif available_count:
        status = "PARTIAL_SATELLITE_REANALYSIS"
        blocker = "Faltan intervalos IMERG Early dentro de al menos una ventana 3/6/24 h."
    else:
        status = "BLOCKED_INCOMPLETE_OBSERVATION"
        blocker = "No hay muestras IMERG Early archivadas dentro de las ventanas previas al evento."

    location = row.get("reported_location") or {}
    event = row.get("reported_event") or {}
    coordinates = location.get("coordinates") or {}
    if row.get("research_role") == "METEOROLOGICAL_REFERENCE_EVENT":
        interpretation = (
            "Referencia meteorológica para validar ingestión, continuidad y acumulados. "
            f"{location.get('district') or location.get('feature_name') or row['event_id']} no "
            "representa una quebrada ni valida huaicos, torrentes o respuesta hidrológica "
            "local, incluso con 3/6/24 h completos."
        )
    else:
        interpretation = (
            "Control positivo de impacto para investigación. Incluso con 3/6/24 h completos, "
            "una celda IMERG de referencia no constituye validación hidrológica local."
        )
    return {
        "event_id": row["event_id"],
        "target_id": target_id,
        "status": status,
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "decision_use": "TEST_ONLY",
        "local_validation": False,
        "counts_toward_v08_closeout": False,
        "operational_zone_activation": False,
        "threshold_inference_allowed": False,
        "hydraulic_transfer_allowed": False,
        "research_role": row.get("research_role"),
        "is_huaico_or_torrent_event": row.get("is_huaico_or_torrent_event"),
        "can_train_zone_activation_model": row.get("can_train_zone_activation_model"),
        "validation_scope": analysis.get("validation_scope"),
        "can_validate_hydrologic_or_hydraulic_response": analysis.get(
            "can_validate_hydrologic_or_hydraulic_response"
        ),
        "can_validate_huaico_or_torrent_model": analysis.get(
            "can_validate_huaico_or_torrent_model"
        ),
        "reported_date_local": event.get("reported_date_local"),
        "occurrence_time_local": event.get("occurrence_time_local"),
        "occurrence_time_utc": occurrence.isoformat(),
        "feature_name": location.get("feature_name"),
        "sampling_reference": {
            "lat": coordinates.get("lat"),
            "lon": coordinates.get("lon"),
            "precision": coordinates.get("precision"),
            "official_event_geometry": coordinates.get("official_event_geometry") is True,
            "role": coordinates.get("role"),
        },
        "official_outcome": {
            "source_url": verification.get("official_event_source"),
            "report_id": verification.get("official_report_id"),
            "reported_impacts": event.get("reported_impacts"),
            "rainfall_mm_published_by_source": False,
        },
        "windows": windows,
        "complete_window_count": complete_count,
        "blocker": blocker,
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "interpretation": interpretation,
    }


def build_document(rows, archive, generated_at=None):
    items = [build_event(row, archive) for row in rows]
    return {
        "version": "phase2-event-reanalysis-v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "deployment_status": "RESEARCH_ONLY",
        "decision_use": "TEST_ONLY",
        "relationship_to_v08": {
            "v08_scope_unchanged": True,
            "counts_toward_v08_closeout": False,
            "can_activate_operational_zones": False,
        },
        "guardrails": {
            "complete_intervals_required_for_accumulation": True,
            "local_validation": False,
            "threshold_inference_allowed": False,
            "hydraulic_transfer_allowed": False,
            "missing_data_is_not_low_risk": True,
            "official_outcome_does_not_supply_rainfall_mm": True,
            "meteorological_reference_is_not_hazard_model_validation": True,
        },
        "source": {
            "satellite": archive.get("source"),
            "archive_updated_at": archive.get("updated_at"),
            "temporal_resolution_minutes": 30,
        },
        "summary": {
            "registered_events": len(items),
            "complete_satellite_reanalyses": sum(i["status"] == "COMPLETE_SATELLITE_REANALYSIS" for i in items),
            "partial_satellite_reanalyses": sum(i["status"] == "PARTIAL_SATELLITE_REANALYSIS" for i in items),
            "blocked_events": sum(str(i["status"]).startswith("BLOCKED_") for i in items),
            "operational_activations": 0,
        },
        "items": items,
    }


def generate(write=True):
    rows = [load_json(path) for path in sorted(INTAKE_DIR.glob("*.json"))]
    archive = load_json(ARCHIVE_PATH)
    document = build_document(rows, archive)
    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    return document


if __name__ == "__main__":
    result = generate()
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
