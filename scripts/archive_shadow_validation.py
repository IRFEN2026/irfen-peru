#!/usr/bin/env python3
"""Archiva una fotografía diaria del modo de prueba IRFEN v0.8.

El archivo sirve para la validación operacional en sombra: qué observó IRFEN,
qué pronosticó y qué recomendación TEST_* habría generado. No emite alertas,
no modifica umbrales y no etiqueta automáticamente impactos reales.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/validation/shadow_runs.json"
EARLIEST_ELIGIBLE_CAPTURE_LEAD_MINUTES = 12 * 60
LATEST_ELIGIBLE_CAPTURE_DELAY_MINUTES = 120
CENDEHUA_MAX_AGE_SECONDS_AT_SHADOW_CAPTURE = 90 * 60
SHADOW_INTEGRITY_EFFECTIVE_DATE = "2026-08-21"
MUTABLE_REVIEW_FIELDS = {
    "outcome_verification",
    "outcome_verification_history",
    "integrity",
}


def immutable_snapshot_payload(record: dict):
    """Return only the pre-outcome evidence that later reviews may not alter."""
    return {
        key: value
        for key, value in record.items()
        if key not in MUTABLE_REVIEW_FIELDS
    }


def snapshot_payload_sha256(record: dict):
    canonical = json.dumps(
        immutable_snapshot_payload(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def integrity_chain_sha256(payload_sha256: str, previous_chain_sha256: str | None):
    canonical = json.dumps(
        {
            "previous_chain_sha256": previous_chain_sha256,
            "snapshot_payload_sha256": payload_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def seal_snapshot_integrity(record: dict, previous_chain_sha256: str | None):
    payload_sha256 = snapshot_payload_sha256(record)
    record["integrity"] = {
        "algorithm": "SHA-256",
        "canonicalization": "JSON_SORT_KEYS_UTF8_COMPACT",
        "scope": "PRE_OUTCOME_SNAPSHOT_EXCLUDING_HUMAN_REVIEW_ANNOTATIONS",
        "snapshot_payload_sha256": payload_sha256,
        "previous_chain_sha256": previous_chain_sha256,
        "chain_sha256": integrity_chain_sha256(payload_sha256, previous_chain_sha256),
    }
    return record["integrity"]


def validate_shadow_integrity(records: list[dict]):
    """Validate the prospective hash chain while leaving legacy records untouched."""
    errors = []
    previous_chain_sha256 = None
    sealed_record_count = 0
    dates = [str(record.get("snapshot_date_utc") or "") for record in records]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        errors.append("snapshot_dates_must_be_unique_and_sorted")
    for record in records:
        snapshot_date = str(record.get("snapshot_date_utc") or "")
        integrity = record.get("integrity") or {}
        if snapshot_date < SHADOW_INTEGRITY_EFFECTIVE_DATE:
            if integrity:
                errors.append(f"{snapshot_date}:legacy_record_must_remain_unsealed")
            continue
        if not integrity:
            errors.append(f"{snapshot_date}:missing_integrity")
            continue
        sealed_record_count += 1
        payload_sha256 = snapshot_payload_sha256(record)
        expected_chain_sha256 = integrity_chain_sha256(
            payload_sha256, previous_chain_sha256
        )
        if integrity.get("algorithm") != "SHA-256":
            errors.append(f"{snapshot_date}:invalid_algorithm")
        if integrity.get("snapshot_payload_sha256") != payload_sha256:
            errors.append(f"{snapshot_date}:payload_hash_mismatch")
        if integrity.get("previous_chain_sha256") != previous_chain_sha256:
            errors.append(f"{snapshot_date}:previous_chain_mismatch")
        if integrity.get("chain_sha256") != expected_chain_sha256:
            errors.append(f"{snapshot_date}:chain_hash_mismatch")
        previous_chain_sha256 = integrity.get("chain_sha256")
    return {
        "valid": not errors,
        "effective_snapshot_date_utc": SHADOW_INTEGRITY_EFFECTIVE_DATE,
        "sealed_record_count": sealed_record_count,
        "last_chain_sha256": previous_chain_sha256,
        "errors": errors,
    }


def capture_window(
    snapshot_date: str,
    earliest_lead_minutes: int = EARLIEST_ELIGIBLE_CAPTURE_LEAD_MINUTES,
    latest_delay_minutes: int = LATEST_ELIGIBLE_CAPTURE_DELAY_MINUTES,
):
    """Return the bounded UTC window for a genuinely pre-outcome snapshot."""
    day_start = datetime.combine(date.fromisoformat(snapshot_date), datetime.min.time(), tzinfo=timezone.utc)
    return (
        day_start - timedelta(minutes=earliest_lead_minutes),
        day_start + timedelta(minutes=latest_delay_minutes),
    )


def capture_is_within_pre_outcome_window(
    captured_at: datetime,
    snapshot_date: str,
    earliest_lead_minutes: int = EARLIEST_ELIGIBLE_CAPTURE_LEAD_MINUTES,
    latest_delay_minutes: int = LATEST_ELIGIBLE_CAPTURE_DELAY_MINUTES,
):
    if captured_at.tzinfo is None:
        raise ValueError("captured_at requiere zona horaria explícita")
    start, end = capture_window(
        snapshot_date,
        earliest_lead_minutes,
        latest_delay_minutes,
    )
    captured_utc = captured_at.astimezone(timezone.utc)
    return start <= captured_utc <= end


def resolve_snapshot_date(captured_at: datetime):
    """Choose today or tomorrow only when capture time is genuinely pre-outcome."""
    if captured_at.tzinfo is None:
        raise ValueError("captured_at requiere zona horaria explícita")
    captured_utc = captured_at.astimezone(timezone.utc)
    for candidate in (captured_utc.date(), captured_utc.date() + timedelta(days=1)):
        candidate_iso = candidate.isoformat()
        if capture_is_within_pre_outcome_window(captured_utc, candidate_iso):
            return candidate_iso
    return None


def required_forecast_hours_to_target_day_end(captured_at: datetime, snapshot_date: str):
    """Return forecast horizon required to cover the complete target UTC day."""
    target_end = datetime.combine(
        date.fromisoformat(snapshot_date) + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return max(0.0, (target_end - captured_at.astimezone(timezone.utc)).total_seconds() / 3600)


def zones_cover_target_day(zones: list[dict], required_future_hours: float):
    """Require every pilot forecast to extend through the target-day close."""
    if not zones:
        return False
    for zone in zones:
        available = (zone.get("forecast_mm") or {}).get("available_future_hours")
        try:
            if float(available) < required_future_hours:
                return False
        except (TypeError, ValueError):
            return False
    return True


def fetch_json(base, path, required=True):
    import requests

    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    try:
        r = requests.get(url, params={"t": int(datetime.now(timezone.utc).timestamp())}, timeout=(8, 30))
        r.raise_for_status()
        return r.json()
    except Exception:
        if required:
            raise
        return None


def load_archive():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": "0.8-experimental",
            "production_use": False,
            "production_ready": False,
            "status": "SHADOW_VALIDATION_ARCHIVE",
            "purpose": "Daily evidence for false-alarm, miss, latency and lead-time validation before any production consideration.",
            "outcome_labels": {
                "NONE": "No verified relevant impact/event",
                "EVENT": "Verified relevant hydrometeorological event/impact",
                "UNCERTAIN": "Evidence insufficient or conflicting"
            },
            "integrity_contract": {
                "effective_snapshot_date_utc": SHADOW_INTEGRITY_EFFECTIVE_DATE,
                "algorithm": "SHA-256",
                "scope": "PRE_OUTCOME_SNAPSHOT_EXCLUDING_HUMAN_REVIEW_ANNOTATIONS",
                "legacy_records_preserved_unmodified": True,
            },
            "records": [],
        }


def compact_zone(z):
    o = z.get("observation") or {}
    f = z.get("forecast") or {}
    r = z.get("river_state") or {}
    rec = z.get("test_recommendation") or {}
    return {
        "zone_id": z.get("zone_id"),
        "test_ready": z.get("test_ready"),
        "readiness": z.get("readiness"),
        "observed_mm": {
            "rain24": o.get("rain24"),
            "rain72": o.get("rain72"),
            "rain7d": o.get("rain7d"),
            "method": o.get("method"),
        },
        "forecast_mm": {
            "forecast24": f.get("forecast24_mm"),
            "forecast72": f.get("forecast72_mm"),
            "available_future_hours": f.get("available_future_hours"),
        },
        "observed_threshold_crossings": z.get("observed_threshold_crossings") or [],
        "forecast_threshold_crossings": f.get("threshold_crossings") or [],
        "river_state": {
            "available": r.get("available"),
            "role": r.get("role"),
            "proxy_class": r.get("proxy_class"),
            "value": r.get("value"),
            "unit": r.get("unit"),
        } if z.get("zone_id") == "catacaos" else None,
        "recommendation": {
            "code": rec.get("code"),
            "mode": rec.get("mode"),
            "operational_alert": rec.get("operational_alert"),
        },
        "blockers": z.get("blockers") or [],
    }


def compact_cendehua_signal(probe, captured_at: datetime):
    """Conserva la señal terrestre sin convertirla en resultado real."""
    signal = probe.get("huaycoloro_ground_signal") if isinstance(probe, dict) else None
    signal = signal if isinstance(signal, dict) else {}
    observations = []
    for row in signal.get("observations") or []:
        if not isinstance(row, dict):
            continue
        try:
            observed_at = datetime.fromisoformat(
                str(row.get("last_alert_update")).replace("Z", "+00:00")
            )
            if observed_at.tzinfo is None:
                raise ValueError("timestamp without timezone")
            age_seconds = round(
                (captured_at.astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds(),
                3,
            )
        except (TypeError, ValueError):
            age_seconds = None
        observations.append({
            "station_id": row.get("station_id"),
            "last_alert_update": row.get("last_alert_update"),
            "last_image_update": row.get("last_image_update"),
            "age_seconds_at_shadow_capture": age_seconds,
            "recent_at_shadow_capture": age_seconds is not None
            and -300 <= age_seconds <= CENDEHUA_MAX_AGE_SECONDS_AT_SHADOW_CAPTURE,
            "provider_activity_flag_raw": row.get("provider_activity_flag_raw")
            if isinstance(row.get("provider_activity_flag_raw"), bool)
            else None,
            "irfen_outcome_label": None,
        })
    recent_count = sum(row["recent_at_shadow_capture"] for row in observations)
    return {
        "provider": "IGP/CENDEHUA",
        "pilot": "Huaycoloro/Chosica",
        "source_generated_at": probe.get("generated_at") if isinstance(probe, dict) else None,
        "source_status": probe.get("status") if isinstance(probe, dict) else "MISSING_OR_UNAVAILABLE",
        "station_count": len(observations),
        "recent_station_count_at_shadow_capture": recent_count,
        "observations": observations,
        "automatic_outcome_label": None,
        "can_support_none_classification_by_itself": False,
        "human_review_required": True,
        "missing_or_stale_data_rule": "UNCERTAIN; never low risk or NONE",
    }


def append_immutable_daily_snapshot(archive, entry, now):
    """Append the first snapshot for a UTC day and never rewrite it later.

    A rerun may happen after the real-world outcome has started to become
    visible. Replacing the same day's inputs at that point would contaminate
    the pre-outcome evidence, even if the existing review annotation were
    preserved. Keeping the first capture also makes workflow reruns
    idempotent.
    """
    records = archive.get("records") or []
    integrity_before = validate_shadow_integrity(records)
    if not integrity_before["valid"]:
        raise ValueError(
            "El archivo en sombra incumple su cadena de integridad: "
            + ", ".join(integrity_before["errors"])
        )
    snapshot_date = entry.get("snapshot_date_utc")
    if any(row.get("snapshot_date_utc") == snapshot_date for row in records):
        return False

    if str(snapshot_date) >= SHADOW_INTEGRITY_EFFECTIVE_DATE:
        seal_snapshot_integrity(entry, integrity_before.get("last_chain_sha256"))
    records.append(entry)
    records.sort(key=lambda row: row.get("snapshot_date_utc", ""))
    archive["records"] = records[-400:]
    archive["updated_at"] = now.isoformat()
    archive["record_count"] = len(archive["records"])
    archive["production_use"] = False
    archive["production_ready"] = False
    archive["integrity_contract"] = {
        "effective_snapshot_date_utc": SHADOW_INTEGRITY_EFFECTIVE_DATE,
        "algorithm": "SHA-256",
        "scope": "PRE_OUTCOME_SNAPSHOT_EXCLUDING_HUMAN_REVIEW_ANNOTATIONS",
        "legacy_records_preserved_unmodified": True,
    }
    integrity_after = validate_shadow_integrity(archive["records"])
    if not integrity_after["valid"]:
        raise ValueError(
            "La nueva fotografía no cerró una cadena de integridad válida: "
            + ", ".join(integrity_after["errors"])
        )
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://irfen2026.github.io/irfen-peru")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    snapshot_date = resolve_snapshot_date(now)
    if snapshot_date is None:
        print(json.dumps({
            "status": "SKIPPED_OUTSIDE_PRE_OUTCOME_WINDOW",
            "snapshot_date_utc": None,
            "captured_at": now.isoformat(),
            "eligible_windows": [
                {
                    "snapshot_date_utc": candidate.isoformat(),
                    "start_utc": capture_window(candidate.isoformat())[0].isoformat(),
                    "end_utc": capture_window(candidate.isoformat())[1].isoformat(),
                }
                for candidate in (now.date(), now.date() + timedelta(days=1))
            ],
            "safety_rule": "An out-of-window run cannot create or replace a daily shadow snapshot.",
        }, ensure_ascii=False, indent=2))
        return 0
    window_start, window_end = capture_window(snapshot_date)

    state = fetch_json(args.base_url, "data/experimental_state.json")
    latest = fetch_json(args.base_url, "data/latest.json")
    forecast = fetch_json(args.base_url, "data/forecast/latest.json", required=False)
    verification = fetch_json(args.base_url, "data/forecast/verification.json", required=False)
    early = fetch_json(args.base_url, "data/calibration/imerg_early_live_probe.json", required=False)
    test_report = fetch_json(args.base_url, "data/test_report.json", required=False)
    cendehua = fetch_json(
        args.base_url, "data/stations/igp_cendehua_access_probe.json", required=False
    )

    if state.get("production_use") is not False:
        raise RuntimeError("experimental_state no conserva production_use=false")
    if not all(str((z.get("test_recommendation") or {}).get("code", "")).startswith("TEST_") for z in state.get("zones", [])):
        raise RuntimeError("Existe una recomendación fuera del contrato TEST_*")

    lima = state.get("lima_east_submodels") or {}
    ped = lima.get("chosica_local_debris_flows") or {}
    iv = ped.get("official_manual_verification") or {}
    zones = [compact_zone(z) for z in state.get("zones", [])]
    required_forecast_hours = required_forecast_hours_to_target_day_end(now, snapshot_date)
    if not zones_cover_target_day(zones, required_forecast_hours):
        print(json.dumps({
            "status": "SKIPPED_FORECAST_DOES_NOT_COVER_TARGET_DAY",
            "snapshot_date_utc": snapshot_date,
            "captured_at": now.isoformat(),
            "required_future_hours": round(required_forecast_hours, 3),
            "available_future_hours_by_zone": {
                zone.get("zone_id"): (zone.get("forecast_mm") or {}).get("available_future_hours")
                for zone in zones
            },
            "safety_rule": "An incomplete target-day forecast cannot become immutable shadow evidence.",
        }, ensure_ascii=False, indent=2))
        return 0

    entry = {
        "snapshot_date_utc": snapshot_date,
        "archived_at": now.isoformat(),
        "pre_outcome_capture_window": {
            "start_utc": window_start.isoformat(),
            "end_utc": window_end.isoformat(),
            "captured_within_window": True,
        },
        "source_timestamps": {
            "experimental_state": state.get("generated_at"),
            "latest_observation": latest.get("last_update_attempt") or latest.get("generated_at"),
            "forecast": (forecast or {}).get("generated_at"),
            "imerg_early": (early or {}).get("generated_at"),
            "igp_cendehua": (cendehua or {}).get("generated_at"),
        },
        "operational_dataset_status": latest.get("operational_status") or "unknown",
        "core_test_status": state.get("core_test_status"),
        "zones": zones,
        "lima_east_local_shadow": {
            "status": ped.get("status"),
            "shadow_test_ready_with_manual_official_verification": ped.get("shadow_test_ready_with_manual_official_verification"),
            "automatic_live_test_ready": ped.get("live_test_ready"),
            "isaac": {
                "available": iv.get("available"),
                "station": iv.get("station"),
                "machine_readable_channel": iv.get("machine_readable_channel"),
                "role": iv.get("role"),
            },
        },
        "ground_signals": {
            "huaycoloro_cendehua": compact_cendehua_signal(cendehua or {}, now),
        },
        "source_health": {
            "forecast_available": (forecast or {}).get("status") == "experimental_forecast_available",
            "forecast_covers_target_day": True,
            "required_forecast_hours_to_target_day_end": round(required_forecast_hours, 3),
            "forecast_verification_pairs": (verification or {}).get("total_pairs"),
            "forecast_verification_pairs_by_zone": {
                zone_id: int(((verification or {}).get("by_zone") or {}).get(zone_id, {}).get("n", 0))
                for zone_id in ("san_ildefonso", "chosica", "catacaos")
            },
            "imerg_early_status": (early or {}).get("status"),
            "imerg_early_latency_hours": (early or {}).get("observed_latency_hours_at_probe"),
            "regression_status": (test_report or {}).get("status"),
        },
        "outcome_verification": {
            "status": "PENDING_REAL_WORLD_OUTCOME_REVIEW",
            "label": None,
            "verified_event": None,
            "official_source": None,
            "notes": None,
        },
        "production_use": False,
    }

    archive = load_archive()
    created = append_immutable_daily_snapshot(archive, entry, now)
    if created:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": archive["status"],
        "record_count": archive["record_count"],
        "snapshot_date_utc": entry["snapshot_date_utc"],
        "snapshot_action": "CREATED" if created else "ALREADY_PRESENT_IMMUTABLE",
        "core": (state.get("core_test_status") or {}).get("code"),
        "recommendations": {z["zone_id"]: z["recommendation"]["code"] for z in entry["zones"]},
        "pedregal_shadow": entry["lima_east_local_shadow"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
