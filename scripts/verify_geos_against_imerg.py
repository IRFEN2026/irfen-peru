#!/usr/bin/env python3
"""Verifica GEOS-CF exclusivamente contra el histórico IMERG científico.

El histórico es independiente de la ventana operativa móvil. Este módulo no
lee ni hidrata ``latest.json`` y falla cerrado ante duplicados, conflictos o
disminuciones de pares que no tengan una retirada explícita y aprobada.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ARCHIVE = SITE / "data" / "forecast" / "archive.json"
HISTORICAL_DAILY = SITE / "data" / "forecast" / "historical_daily.json"
OBSERVATION_HISTORY = SITE / "data" / "forecast" / "imerg_verification_history.json"
OUT = SITE / "data" / "forecast" / "verification.json"
PILOT_METHODS = {
    "san_ildefonso": "validated_dem_polygon",
    "chosica": "validated_dem_polygon",
    "catacaos": "provisional_weighted_operational_sampling_areas",
}
MIN_SAMPLES = 30


class VerificationError(ValueError):
    pass


def canonical_sha256(value):
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_required(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VerificationError(f"No se pudo leer {path}: {exc}") from exc


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path):
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def dt(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except Exception:
        if "." in text:
            head, rest = text.split(".", 1)
            suffix = "+00:00" if "+" not in rest and "-" not in rest[1:] else ""
            frac = "".join(ch for ch in rest if ch.isdigit())[:6]
            try:
                return datetime.fromisoformat(f"{head}.{frac}{suffix}").astimezone(timezone.utc)
            except Exception:
                pass
        return None


def history_key(row):
    return (
        row.get("zone_id"),
        row.get("sampling_method"),
        row.get("valid_date_utc"),
    )


def validate_history(history):
    if history.get("production_use") is not False:
        raise VerificationError("El histórico IMERG debe declarar production_use=false")
    if history.get("production_ready") is not False:
        raise VerificationError("El histórico IMERG debe declarar production_ready=false")
    retention = history.get("retention_policy") or {}
    if retention.get("mode") != "APPEND_ONLY":
        raise VerificationError("La retención del histórico IMERG debe ser APPEND_ONLY")
    if retention.get("deduplication_key") != [
        "zone_id", "sampling_method", "valid_date_utc"
    ]:
        raise VerificationError("Clave de deduplicación IMERG inesperada")
    if retention.get("tombstone_creation_policy") != "MANUAL_REVIEWED_COMMIT_ONLY":
        raise VerificationError("La creación de tombstones debe ser manual y revisada")
    if retention.get("automatic_tombstone_creation") is not False:
        raise VerificationError("La creación automática de tombstones está prohibida")

    evidence_by_id = {}
    for evidence in history.get("source_evidence") or []:
        evidence_id = evidence.get("evidence_id")
        if not evidence_id or evidence_id in evidence_by_id:
            raise VerificationError(f"Evidencia de procedencia duplicada o sin ID: {evidence_id}")
        evidence_by_id[evidence_id] = evidence

    observations = history.get("observations") or []
    seen = {}
    for row in observations:
        key = history_key(row)
        if key in seen:
            raise VerificationError(f"Observación histórica duplicada: {key}")
        if key[0] not in PILOT_METHODS or PILOT_METHODS.get(key[0]) != key[1]:
            raise VerificationError(f"Contrato espacial histórico inesperado: {key[:2]}")
        if not key[2] or row.get("observed_imerg_mm") is None:
            raise VerificationError(f"Observación incompleta: {key}")
        if float(row["observed_imerg_mm"]) < 0:
            raise VerificationError(f"Precipitación histórica negativa: {key}")
        if row.get("provenance_evidence_id") not in evidence_by_id:
            raise VerificationError(f"Observación sin procedencia: {key}")
        seen[key] = row

    withdrawals = history.get("withdrawals") or []
    withdrawn = set()
    for row in withdrawals:
        key = (
            row.get("zone_id"), row.get("sampling_method"), row.get("valid_date_utc")
        )
        required = (
            row.get("withdrawal_id"), row.get("reason"),
            row.get("approval_reference"), row.get("approved_by"),
            row.get("approved_at"), row.get("recorded_at"),
            row.get("observation_sha256"), row.get("evidence_sha256"),
        )
        if row.get("status") != "APPROVED" or not all(required):
            raise VerificationError(f"Retirada no explícita o no aprobada: {key}")
        if row.get("creation_mode") != "MANUAL_REVIEWED_COMMIT":
            raise VerificationError(f"Tombstone no creado mediante commit manual revisado: {key}")
        if row.get("automatic_creation") is not False:
            raise VerificationError(f"Tombstone automático prohibido: {key}")
        if key not in seen:
            raise VerificationError(f"Retirada sin observación histórica: {key}")
        if key in withdrawn:
            raise VerificationError(f"Retirada duplicada: {key}")
        observation = seen[key]
        evidence = evidence_by_id[observation["provenance_evidence_id"]]
        if row["observation_sha256"] != canonical_sha256(observation):
            raise VerificationError(f"Hash de observación inválido en tombstone: {key}")
        if row["evidence_sha256"] != canonical_sha256(evidence):
            raise VerificationError(f"Hash de evidencia inválido en tombstone: {key}")
        withdrawn.add(key)

    expected_contracts = set(PILOT_METHODS.items())
    actual_contracts = {(key[0], key[1]) for key in seen}
    if actual_contracts != expected_contracts:
        raise VerificationError(
            f"Pilotos/contratos del histórico no coinciden: {sorted(actual_contracts)}"
        )
    return seen, withdrawn


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
    errors = [float(row["error_mm"]) for row in rows]
    return {
        "n": len(rows),
        "mae_mm": round(sum(abs(value) for value in errors) / len(errors), 3),
        "rmse_mm": round(math.sqrt(sum(value * value for value in errors) / len(errors)), 3),
        "bias_mm": round(sum(errors) / len(errors), 3),
    }


def observation_index(history):
    seen, withdrawn = validate_history(history)
    return {key: row for key, row in seen.items() if key not in withdrawn}


def build_pairs(archive, historical, history):
    observations = observation_index(history)
    pairs = []

    for snapshot in archive.get("snapshots") or []:
        issued = dt(snapshot.get("generated_at"))
        for forecast_zone in snapshot.get("zones") or []:
            zone_id = forecast_zone.get("zone_id")
            method = forecast_zone.get("sampling_method")
            if PILOT_METHODS.get(zone_id) != method:
                continue
            by_day = defaultdict(list)
            for hour in forecast_zone.get("hourly") or []:
                when = dt(hour.get("valid_time"))
                value = hour.get("precip_mm")
                if when is not None and value is not None:
                    by_day[when.date().isoformat()].append((when, float(value)))
            for day, values in sorted(by_day.items()):
                observation = observations.get((zone_id, method, day))
                unique = {value[0].isoformat(): value[1] for value in values}
                if observation is None or len(unique) != 24:
                    continue
                day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                lead_hours = None if issued is None else (
                    day_start - issued
                ).total_seconds() / 3600
                if lead_hours is not None and lead_hours < 0:
                    continue
                pairs.append(make_pair(
                    zone_id, method, snapshot.get("generated_at"), day,
                    lead_hours, sum(unique.values()), observation,
                    forecast_record_kind="hourly_archive_snapshot",
                ))

    if historical.get("production_use") is False:
        for record in historical.get("records") or []:
            zone_id = record.get("zone_id")
            method = record.get("sampling_method")
            day = record.get("valid_date_utc")
            issued = dt(record.get("issue_time"))
            observation = observations.get((zone_id, method, day))
            if (
                PILOT_METHODS.get(zone_id) != method or not day or issued is None
                or int(record.get("hour_count", 0)) != 24 or observation is None
                or record.get("forecast_mm") is None
            ):
                continue
            day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            lead_hours = (day_start - issued).total_seconds() / 3600
            if lead_hours < 0:
                continue
            pair = make_pair(
                zone_id, method, record.get("issue_time"), day, lead_hours,
                float(record["forecast_mm"]), observation,
                forecast_record_kind="historical_daily_backfill",
            )
            pair["source_dataset"] = record.get("source_dataset")
            pairs.append(pair)

    deduplicated = {}
    for row in pairs:
        key = (
            row["zone_id"], row["sampling_method"], row["snapshot_generated_at"],
            row["valid_date_utc"], row["forecast_record_kind"],
        )
        deduplicated[key] = row
    return sorted(
        deduplicated.values(),
        key=lambda row: (
            row["valid_date_utc"], row["zone_id"],
            row["snapshot_generated_at"] or "", row["forecast_record_kind"],
        ),
    )


def make_pair(
    zone_id, method, issued_at, day, lead_hours, forecast_mm, observation,
    forecast_record_kind,
):
    forecast_value = round(float(forecast_mm), 3)
    observed_value = round(float(observation["observed_imerg_mm"]), 3)
    error = round(forecast_value - observed_value, 3)
    return {
        "zone_id": zone_id,
        "sampling_method": method,
        "snapshot_generated_at": issued_at,
        "valid_date_utc": day,
        "lead_hours_to_day_start": None if lead_hours is None else round(lead_hours, 2),
        "lead_bucket": lead_bucket(lead_hours),
        "forecast_mm": forecast_value,
        "observed_imerg_mm": observed_value,
        "error_mm": error,
        "absolute_error_mm": round(abs(error), 3),
        "forecast_record_kind": forecast_record_kind,
        "observation_evidence_id": observation["provenance_evidence_id"],
    }


def current_commit():
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def monotonicity_evidence(previous, pairs, by_zone, history):
    if previous is None:
        return {
            "status": "BASELINE_NOT_COMPARED",
            "silent_decrease_forbidden": True,
            "previous_verification_sha256": None,
        }
    previous_by_zone = previous.get("by_zone") or {}
    decreases = []
    if len(pairs) < int(previous.get("total_pairs", 0)):
        decreases.append({
            "scope": "total", "before": int(previous.get("total_pairs", 0)),
            "after": len(pairs),
        })
    for zone_id in PILOT_METHODS:
        before = int((previous_by_zone.get(zone_id) or {}).get("n", 0))
        after = int((by_zone.get(zone_id) or {}).get("n", 0))
        if after < before:
            decreases.append({"scope": zone_id, "before": before, "after": after})
    # La identidad estable omite ``forecast_record_kind`` porque la verificación
    # v1 publicada no lo declaraba. Exigimos unicidad con estos cuatro campos en
    # ambos lados; una futura colisión entre clases fallará cerrada.
    pair_fields = (
        "zone_id", "sampling_method", "snapshot_generated_at",
        "valid_date_utc",
    )

    def pair_key(row):
        return tuple(row.get(field) for field in pair_fields)

    previous_pairs = previous.get("pairs") or []
    previous_total = int(previous.get("total_pairs", 0))
    if previous_total != len(previous_pairs):
        raise VerificationError(
            "La verificación previa no permite auditar monotonicidad por identidad de par: "
            f"total_pairs={previous_total}, pairs={len(previous_pairs)}"
        )
    previous_keys = [pair_key(row) for row in previous_pairs]
    current_keys = [pair_key(row) for row in pairs]
    if len(previous_keys) != len(set(previous_keys)):
        raise VerificationError("La verificación previa contiene identidades de par duplicadas")
    if len(current_keys) != len(set(current_keys)):
        raise VerificationError("La verificación actual contiene identidades de par duplicadas")

    removed_keys = sorted(set(previous_keys) - set(current_keys))
    withdrawals = history.get("withdrawals") or []
    withdrawals_by_observation = {
        (row.get("zone_id"), row.get("sampling_method"), row.get("valid_date_utc")): row
        for row in withdrawals
    }
    unauthorized_removed = [
        key for key in removed_keys
        if (key[0], key[1], key[3]) not in withdrawals_by_observation
    ]
    if unauthorized_removed:
        raise VerificationError(
            "Pares históricos desaparecieron sin una retirada aprobada para su observación: "
            f"{unauthorized_removed}"
        )
    if decreases and not removed_keys:
        raise VerificationError(
            f"Disminución agregada sin identidades de par retiradas: {decreases}"
        )
    relevant_withdrawals = {
        withdrawals_by_observation[(key[0], key[1], key[3])]["withdrawal_id"]
        for key in removed_keys
    }
    return {
        "status": "EXPLICIT_WITHDRAWAL_RECORDED" if removed_keys else "NO_DECREASE",
        "silent_decrease_forbidden": True,
        "previous_total_pairs": previous_total,
        "current_total_pairs": len(pairs),
        "decreases": decreases,
        "removed_pair_count": len(removed_keys),
        "removed_pair_keys": [dict(zip(pair_fields, key)) for key in removed_keys],
        "authorized_withdrawal_ids": sorted(relevant_withdrawals),
    }


def build_report(archive, historical, history, previous=None, generated_at=None):
    pairs = build_pairs(archive, historical, history)
    by_zone = {}
    for zone_id in PILOT_METHODS:
        rows = [row for row in pairs if row["zone_id"] == zone_id]
        zone_metrics = metrics(rows)
        zone_metrics["assessment"] = (
            "sample_accumulation" if len(rows) < MIN_SAMPLES
            else "enough_samples_for_initial_bias_review"
        )
        zone_metrics["minimum_samples_for_initial_review"] = MIN_SAMPLES
        zone_metrics["by_lead"] = {
            bucket: metrics([row for row in rows if row["lead_bucket"] == bucket])
            for bucket in ("D+1", "D+2", "D+3", "D+4", "D+5")
        }
        by_zone[zone_id] = zone_metrics

    observations, withdrawn = validate_history(history)
    dates = sorted(key[2] for key in observations if key not in withdrawn)
    monotonicity = monotonicity_evidence(previous, pairs, by_zone, history)
    return {
        "version": "0.8-experimental-verification-v2",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "status": "verification_available" if pairs else "awaiting_mature_forecasts",
        "forecast_source": "NASA GMAO GEOS-CF v2",
        "observation_source": "NASA GPM IMERG Late Daily",
        "comparison_unit": "UTC calendar day with 24 complete GEOS hourly values",
        "minimum_samples_for_initial_review": MIN_SAMPLES,
        "pilot_zone_ids": list(PILOT_METHODS),
        "provenance": {
            "workflow_name": os.environ.get("GITHUB_WORKFLOW", "LOCAL_REPRODUCIBLE_BUILD"),
            "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
            "workflow_run_number": os.environ.get("GITHUB_RUN_NUMBER"),
            "main_commit": current_commit(),
            "acquisition_mode": "DEDICATED_APPEND_ONLY_IMERG_VERIFICATION_HISTORY_ONLY",
            "fallback_used": False,
            "retention_policy": history.get("retention_policy"),
            "minimum_valid_date_utc": dates[0] if dates else None,
            "maximum_valid_date_utc": dates[-1] if dates else None,
            "observation_count": len(observations) - len(withdrawn),
            "withdrawal_count": len(withdrawn),
            "inputs": [],
        },
        "monotonicity": monotonicity,
        "scientific_limitations": [
            "GEOS-CF e IMERG tienen resoluciones y errores propios; esta comparación mide consistencia, no verdad de terreno.",
            "San Ildefonso y Huaycoloro usan sus polígonos DEM; Catacaos conserva muestreo espacial provisional.",
            "No se corrige sesgo ni se cambia ningún umbral hasta acumular suficientes casos lluviosos y secos.",
        ],
        "forecast_inputs": {
            "live_archive_snapshots": len(archive.get("snapshots") or []),
            "historical_daily_records_available": len(historical.get("records") or []),
            "historical_daily_pairs_used": sum(
                row["forecast_record_kind"] == "historical_daily_backfill" for row in pairs
            ),
            "observed_history_records": len(observations) - len(withdrawn),
        },
        "total_pairs": len(pairs),
        "overall_metrics": metrics(pairs),
        "by_zone": by_zone,
        "pairs": pairs,
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-verification", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    archive = load_required(ARCHIVE)
    historical = load_required(HISTORICAL_DAILY)
    history = load_required(OBSERVATION_HISTORY)
    previous = load_required(args.previous_verification) if args.previous_verification else None
    report = build_report(archive, historical, history, previous=previous)
    report["provenance"]["inputs"] = [
        {"path": relative(path), "sha256": sha256_file(path)}
        for path in (ARCHIVE, HISTORICAL_DAILY, OBSERVATION_HISTORY)
    ]
    if args.previous_verification:
        report["monotonicity"]["previous_verification_path"] = relative(
            args.previous_verification
        )
        report["monotonicity"]["previous_verification_sha256"] = sha256_file(
            args.previous_verification
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "total_pairs": report["total_pairs"],
        "by_zone": {zone_id: row["n"] for zone_id, row in report["by_zone"].items()},
        "monotonicity": report["monotonicity"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
