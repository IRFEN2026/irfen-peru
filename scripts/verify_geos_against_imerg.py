#!/usr/bin/env python3
"""Verifica pronósticos GEOS-CF archivados contra IMERG observado.

Compara únicamente días UTC completos (24 valores horarios GEOS) para los que ya
existe una observación IMERG compatible espacialmente. No ajusta el forecast,
no genera umbrales y no interviene en la operación v0.7.1.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ARCHIVE = SITE / "data" / "forecast" / "archive.json"
HISTORICAL_DAILY = SITE / "data" / "forecast" / "historical_daily.json"
LATEST = SITE / "data" / "latest.json"
OUT = SITE / "data" / "forecast" / "verification.json"
MIN_SAMPLES = 30


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def dt(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except Exception:
        # Tolerar precisión nanosegundo de algunos metadatos NumPy.
        if "." in text:
            head, rest = text.split(".", 1)
            suffix = "+00:00" if "+" not in rest and "-" not in rest[1:] else ""
            frac = "".join(ch for ch in rest if ch.isdigit())[:6]
            try:
                return datetime.fromisoformat(f"{head}.{frac}{suffix}").astimezone(timezone.utc)
            except Exception:
                pass
        return None


def observed_series(zone, sampling_method):
    if sampling_method == "validated_dem_polygon":
        exp = zone.get("experimental_polygon") or {}
        if exp.get("production_use") is False:
            return exp.get("series") or []
        return []
    return zone.get("series") or []


def lead_bucket(hours):
    if hours is None:
        return "unknown"
    if hours <= 24:
        return "D+1"
    if hours <= 48:
        return "D+2"
    if hours <= 72:
        return "D+3"
    if hours <= 96:
        return "D+4"
    return "D+5"


def metrics(rows):
    if not rows:
        return {"n": 0, "mae_mm": None, "rmse_mm": None, "bias_mm": None}
    errs = [float(r["error_mm"]) for r in rows]
    return {
        "n": len(rows),
        "mae_mm": round(sum(abs(e) for e in errs) / len(errs), 3),
        "rmse_mm": round(math.sqrt(sum(e * e for e in errs) / len(errs)), 3),
        "bias_mm": round(sum(errs) / len(errs), 3),
    }


def main():
    archive = load(ARCHIVE, {"snapshots": []})
    historical = load(HISTORICAL_DAILY, {"records": []})
    latest = load(LATEST, {"zones": []})
    zones = {z.get("id"): z for z in latest.get("zones", [])}
    pairs = []

    for snap in archive.get("snapshots", []):
        issued = dt(snap.get("generated_at"))
        for fz in snap.get("zones", []):
            zid = fz.get("zone_id")
            zone = zones.get(zid)
            if not zone:
                continue
            method = fz.get("sampling_method")
            obs = {
                x.get("date"): x.get("rain_mm")
                for x in observed_series(zone, method)
                if x.get("date") and x.get("rain_mm") is not None
            }
            if not obs:
                continue

            by_day = defaultdict(list)
            for h in fz.get("hourly", []):
                when = dt(h.get("valid_time"))
                val = h.get("precip_mm")
                if when is None or val is None:
                    continue
                by_day[when.date().isoformat()].append((when, float(val)))

            for day, values in sorted(by_day.items()):
                # Un día comparable debe contener exactamente las 24 horas únicas.
                unique = {v[0].isoformat(): v[1] for v in values}
                if len(unique) != 24 or day not in obs:
                    continue
                day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                lead_h = None if issued is None else (day_start - issued).total_seconds() / 3600
                # Evitar usar un "forecast" de un día ya iniciado antes de emitirse.
                if lead_h is not None and lead_h < 0:
                    continue
                forecast_mm = round(sum(unique.values()), 3)
                observed_mm = round(float(obs[day]), 3)
                error = round(forecast_mm - observed_mm, 3)
                pairs.append({
                    "zone_id": zid,
                    "sampling_method": method,
                    "snapshot_generated_at": snap.get("generated_at"),
                    "valid_date_utc": day,
                    "lead_hours_to_day_start": None if lead_h is None else round(lead_h, 2),
                    "lead_bucket": lead_bucket(lead_h),
                    "forecast_mm": forecast_mm,
                    "observed_imerg_mm": observed_mm,
                    "error_mm": error,
                    "absolute_error_mm": round(abs(error), 3),
                })

    # Backfill compacto: pronósticos realmente emitidos ya agregados a días UTC
    # completos. Se mantiene separado del archive horario para no inflar el sitio.
    if historical.get("production_use") is False:
        for record in historical.get("records", []):
            zid = record.get("zone_id")
            zone = zones.get(zid)
            day = record.get("valid_date_utc")
            method = record.get("sampling_method")
            issued = dt(record.get("issue_time"))
            if not zone or not day or issued is None or int(record.get("hour_count", 0)) != 24:
                continue
            obs = {
                row.get("date"): row.get("rain_mm")
                for row in observed_series(zone, method)
                if row.get("date") and row.get("rain_mm") is not None
            }
            if day not in obs:
                continue
            day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            lead_h = (day_start - issued).total_seconds() / 3600
            if lead_h < 0 or record.get("forecast_mm") is None:
                continue
            forecast_mm = round(float(record["forecast_mm"]), 3)
            observed_mm = round(float(obs[day]), 3)
            error = round(forecast_mm - observed_mm, 3)
            pairs.append({
                "zone_id": zid,
                "sampling_method": method,
                "snapshot_generated_at": record.get("issue_time"),
                "valid_date_utc": day,
                "lead_hours_to_day_start": round(lead_h, 2),
                "lead_bucket": lead_bucket(lead_h),
                "forecast_mm": forecast_mm,
                "observed_imerg_mm": observed_mm,
                "error_mm": error,
                "absolute_error_mm": round(abs(error), 3),
                "forecast_record_kind": "historical_daily_backfill",
                "source_dataset": record.get("source_dataset"),
            })

    # Eliminar duplicados exactos si el archivo de snapshots fue regenerado.
    dedup = {}
    for row in pairs:
        key = (row["zone_id"], row["snapshot_generated_at"], row["valid_date_utc"])
        dedup[key] = row
    pairs = sorted(dedup.values(), key=lambda r: (r["valid_date_utc"], r["zone_id"], r["snapshot_generated_at"] or ""))

    by_zone = {}
    for zid in ("san_ildefonso", "chosica", "catacaos"):
        rows = [r for r in pairs if r["zone_id"] == zid]
        zone_metrics = metrics(rows)
        zone_metrics["assessment"] = "sample_accumulation" if len(rows) < MIN_SAMPLES else "enough_samples_for_initial_bias_review"
        zone_metrics["minimum_samples_for_initial_review"] = MIN_SAMPLES
        zone_metrics["by_lead"] = {
            bucket: metrics([r for r in rows if r["lead_bucket"] == bucket])
            for bucket in ("D+1", "D+2", "D+3", "D+4", "D+5")
        }
        by_zone[zid] = zone_metrics

    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "status": "verification_available" if pairs else "awaiting_mature_forecasts",
        "forecast_source": "NASA GMAO GEOS-CF v2",
        "observation_source": "NASA GPM IMERG Late Daily",
        "comparison_unit": "UTC calendar day with 24 complete GEOS hourly values",
        "scientific_limitations": [
            "GEOS-CF e IMERG tienen resoluciones y errores propios; esta comparación mide consistencia, no verdad de terreno.",
            "San Ildefonso y Huaycoloro usan sus polígonos DEM; Catacaos conserva muestreo espacial provisional.",
            "No se corrige sesgo ni se cambia ningún umbral hasta acumular suficientes casos lluviosos y secos.",
        ],
        "minimum_samples_for_initial_review": MIN_SAMPLES,
        "total_pairs": len(pairs),
        "overall_metrics": metrics(pairs),
        "by_zone": by_zone,
        "pairs": pairs[-500:],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "total_pairs": report["total_pairs"],
        "overall_metrics": report["overall_metrics"],
        "by_zone": report["by_zone"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
