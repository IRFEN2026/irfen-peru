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
OBSERVED_ARCHIVE = SITE / "data" / "forecast" / "observed_imerg_daily.json"
MIN_SAMPLES = 30
OBSERVED_ARCHIVE_RETENTION_CONTRACT = (
    "append_only_by_zone_method_valid_date; first_audited_value_wins; "
    "conflicting_revisions_are_logged_without_overwrite"
)
RUN170_SEED_PROVENANCE = {
    "source": "GitHub Actions update-and-deploy run #170 Pages artifact",
    "workflow_run_id": 32300707086,
    "workflow_run_url": "https://github.com/IRFEN2026/irfen-peru/actions/runs/32300707086",
    "artifact_id": 9382914636,
    "artifact_name": "github-pages",
    "artifact_sha256": "88c0cd15ebbde7a9b789cacf4720c81e946e31d46f60546275fcac1dad851d9b",
    "verification_path": "data/forecast/verification.json",
    "verification_sha256": "f4a79332710e8531e588b1f56222933e710439f38627c28a988ee7d11970ae1b",
    "latest_path": "data/latest.json",
    "latest_sha256": "47a78c7e5e98f225f1e391e53d6d01c6188450c918e15bc71da8226509959d46",
    "matched_observation_keys": 33,
    "missing_observation_keys": 0,
    "conflicting_observation_keys": 0,
    "role": "AUDITED_BACKFILL_SOURCE",
}


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


def merge_observed_archive(zones, prior, required_methods, generated_at=None):
    """Acumula observaciones diarias sin perder días al rotar latest.json.

    ``latest.json`` conserva una ventana móvil. El archivo acumulativo mantiene
    únicamente fecha, lluvia y contrato espacial; no convierte la ausencia de
    datos en cero ni habilita uso operativo.
    """
    if prior and prior.get("production_use") is not False:
        raise ValueError("observed_imerg_daily.json debe declarar production_use=false")

    merged = {}
    revision_candidates = list((prior or {}).get("revision_candidates") or [])
    revision_keys = {
        (
            row.get("zone_id"),
            row.get("sampling_method"),
            row.get("valid_date_utc"),
            row.get("candidate_rain_mm"),
        )
        for row in revision_candidates
    }
    for record in (prior or {}).get("records", []):
        key = (record.get("zone_id"), record.get("sampling_method"))
        if None in key:
            continue
        for row in record.get("series", []):
            if row.get("date") and row.get("rain_mm") is not None:
                archive_key = (key, row["date"])
                candidate = {
                    "date": row["date"],
                    "rain_mm": round(float(row["rain_mm"]), 3),
                }
                if archive_key not in merged:
                    merged[archive_key] = candidate
                    continue
                if merged[archive_key]["rain_mm"] != candidate["rain_mm"]:
                    raise ValueError(
                        "observed_imerg_daily.json contiene valores archivados "
                        f"conflictivos para {key} {row['date']}"
                    )

    for zid, method in sorted(required_methods):
        zone = zones.get(zid)
        if not zone:
            continue
        for row in observed_series(zone, method):
            if row.get("date") and row.get("rain_mm") is not None:
                key = ((zid, method), row["date"])
                candidate = {
                    "date": row["date"],
                    "rain_mm": round(float(row["rain_mm"]), 3),
                }
                if key not in merged:
                    merged[key] = candidate
                    continue
                if merged[key]["rain_mm"] == candidate["rain_mm"]:
                    continue
                revision_key = (zid, method, row["date"], candidate["rain_mm"])
                if revision_key not in revision_keys:
                    revision_candidates.append({
                        "zone_id": zid,
                        "sampling_method": method,
                        "valid_date_utc": row["date"],
                        "archived_rain_mm": merged[key]["rain_mm"],
                        "candidate_rain_mm": candidate["rain_mm"],
                        "first_seen_at": generated_at or datetime.now(timezone.utc).isoformat(),
                        "disposition": "LOGGED_NOT_OVERWRITTEN_PENDING_SCIENTIFIC_REVIEW",
                        "production_use": False,
                    })
                    revision_keys.add(revision_key)

    records = []
    for zid, method in sorted(required_methods):
        series = [
            row for ((key, _), row) in merged.items()
            if key == (zid, method)
        ]
        series.sort(key=lambda row: row["date"])
        if series:
            records.append({
                "zone_id": zid,
                "sampling_method": method,
                "series": series,
            })

    archive = {
        "version": "0.8-experimental",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "observation_source": "NASA GPM IMERG Late Daily",
        "record_count": len(records),
        "retention_contract": OBSERVED_ARCHIVE_RETENTION_CONTRACT,
        "missing_data_policy": "missing dates remain absent and are never interpreted as zero rain or low risk",
        "records": records,
        "revision_candidates": sorted(
            revision_candidates,
            key=lambda row: (
                row.get("valid_date_utc") or "",
                row.get("zone_id") or "",
                row.get("sampling_method") or "",
                row.get("candidate_rain_mm") if row.get("candidate_rain_mm") is not None else -1,
            ),
        ),
    }
    provenance = list((prior or {}).get("seed_provenance") or [])
    if not any(
        row.get("artifact_sha256") == RUN170_SEED_PROVENANCE["artifact_sha256"]
        for row in provenance
    ):
        provenance.append(dict(RUN170_SEED_PROVENANCE))
    archive["seed_provenance"] = provenance
    return archive


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
    required_methods = {
        (fz.get("zone_id"), fz.get("sampling_method"))
        for snap in archive.get("snapshots", [])
        for fz in snap.get("zones", [])
        if fz.get("zone_id") and fz.get("sampling_method")
    }
    required_methods.update({
        (record.get("zone_id"), record.get("sampling_method"))
        for record in historical.get("records", [])
        if record.get("zone_id") and record.get("sampling_method")
    })
    observed_archive = merge_observed_archive(
        zones,
        load(OBSERVED_ARCHIVE, {}),
        required_methods,
    )
    OBSERVED_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    OBSERVED_ARCHIVE.write_text(
        json.dumps(observed_archive, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archived_observations = {
        (record["zone_id"], record["sampling_method"]): {
            row["date"]: row["rain_mm"] for row in record.get("series", [])
        }
        for record in observed_archive.get("records", [])
    }
    pairs = []

    for snap in archive.get("snapshots", []):
        issued = dt(snap.get("generated_at"))
        for fz in snap.get("zones", []):
            zid = fz.get("zone_id")
            zone = zones.get(zid)
            if not zone:
                continue
            method = fz.get("sampling_method")
            obs = archived_observations.get((zid, method), {})
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
            obs = archived_observations.get((zid, method), {})
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
        "forecast_inputs": {
            "live_archive_snapshots": len(archive.get("snapshots", [])),
            "historical_daily_records_available": len(historical.get("records", [])),
            "historical_daily_pairs_used": sum(
                row.get("forecast_record_kind") == "historical_daily_backfill" for row in pairs
            ),
            "observed_daily_archive_records": sum(
                len(record.get("series", []))
                for record in observed_archive.get("records", [])
            ),
            "observed_daily_archive_generated_at": observed_archive.get("generated_at"),
        },
        "total_pairs": len(pairs),
        "overall_metrics": metrics(pairs),
        "by_zone": by_zone,
        "pairs": pairs,
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
