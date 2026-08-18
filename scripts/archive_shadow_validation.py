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
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/validation/shadow_runs.json"
LATEST_ELIGIBLE_CAPTURE_DELAY_MINUTES = 120


def capture_window(snapshot_date: str, latest_delay_minutes: int = LATEST_ELIGIBLE_CAPTURE_DELAY_MINUTES):
    """Return the bounded UTC window for a genuinely pre-outcome snapshot."""
    day_start = datetime.combine(date.fromisoformat(snapshot_date), datetime.min.time(), tzinfo=timezone.utc)
    return day_start, day_start + timedelta(minutes=latest_delay_minutes)


def capture_is_within_pre_outcome_window(
    captured_at: datetime,
    snapshot_date: str,
    latest_delay_minutes: int = LATEST_ELIGIBLE_CAPTURE_DELAY_MINUTES,
):
    if captured_at.tzinfo is None:
        raise ValueError("captured_at requiere zona horaria explícita")
    start, end = capture_window(snapshot_date, latest_delay_minutes)
    captured_utc = captured_at.astimezone(timezone.utc)
    return start <= captured_utc <= end


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


def append_immutable_daily_snapshot(archive, entry, now):
    """Append the first snapshot for a UTC day and never rewrite it later.

    A rerun may happen after the real-world outcome has started to become
    visible. Replacing the same day's inputs at that point would contaminate
    the pre-outcome evidence, even if the existing review annotation were
    preserved. Keeping the first capture also makes workflow reruns
    idempotent.
    """
    records = archive.get("records") or []
    snapshot_date = entry.get("snapshot_date_utc")
    if any(row.get("snapshot_date_utc") == snapshot_date for row in records):
        return False

    records.append(entry)
    records.sort(key=lambda row: row.get("snapshot_date_utc", ""))
    archive["records"] = records[-400:]
    archive["updated_at"] = now.isoformat()
    archive["record_count"] = len(archive["records"])
    archive["production_use"] = False
    archive["production_ready"] = False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://irfen2026.github.io/irfen-peru")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    snapshot_date = now.date().isoformat()
    window_start, window_end = capture_window(snapshot_date)
    if not capture_is_within_pre_outcome_window(now, snapshot_date):
        print(json.dumps({
            "status": "SKIPPED_OUTSIDE_PRE_OUTCOME_WINDOW",
            "snapshot_date_utc": snapshot_date,
            "captured_at": now.isoformat(),
            "eligible_window_start_utc": window_start.isoformat(),
            "eligible_window_end_utc": window_end.isoformat(),
            "safety_rule": "A late workflow run cannot create or replace a daily shadow snapshot.",
        }, ensure_ascii=False, indent=2))
        return 0

    state = fetch_json(args.base_url, "data/experimental_state.json")
    latest = fetch_json(args.base_url, "data/latest.json")
    forecast = fetch_json(args.base_url, "data/forecast/latest.json", required=False)
    verification = fetch_json(args.base_url, "data/forecast/verification.json", required=False)
    early = fetch_json(args.base_url, "data/calibration/imerg_early_live_probe.json", required=False)
    test_report = fetch_json(args.base_url, "data/test_report.json", required=False)

    if state.get("production_use") is not False:
        raise RuntimeError("experimental_state no conserva production_use=false")
    if not all(str((z.get("test_recommendation") or {}).get("code", "")).startswith("TEST_") for z in state.get("zones", [])):
        raise RuntimeError("Existe una recomendación fuera del contrato TEST_*")

    lima = state.get("lima_east_submodels") or {}
    ped = lima.get("chosica_local_debris_flows") or {}
    iv = ped.get("official_manual_verification") or {}
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
        },
        "operational_dataset_status": latest.get("operational_status") or "unknown",
        "core_test_status": state.get("core_test_status"),
        "zones": [compact_zone(z) for z in state.get("zones", [])],
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
        "source_health": {
            "forecast_available": (forecast or {}).get("status") == "experimental_forecast_available",
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
