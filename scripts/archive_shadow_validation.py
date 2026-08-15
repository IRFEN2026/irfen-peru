#!/usr/bin/env python3
"""Archiva una fotografía diaria del modo de prueba IRFEN v0.8.

El archivo sirve para la validación operacional en sombra: qué observó IRFEN,
qué pronosticó y qué recomendación TEST_* habría generado. No emite alertas,
no modifica umbrales y no etiqueta automáticamente impactos reales.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/validation/shadow_runs.json"


def fetch_json(base, path, required=True):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://irfen2026.github.io/irfen-peru")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
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
        "snapshot_date_utc": now.date().isoformat(),
        "archived_at": now.isoformat(),
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
    records = archive.get("records") or []
    previous_same_day = next((x for x in records if x.get("snapshot_date_utc") == entry["snapshot_date_utc"]), None)
    if previous_same_day:
        prev_outcome = previous_same_day.get("outcome_verification") or {}
        if prev_outcome.get("status") != "PENDING_REAL_WORLD_OUTCOME_REVIEW":
            entry["outcome_verification"] = prev_outcome
        records = [x for x in records if x.get("snapshot_date_utc") != entry["snapshot_date_utc"]]
    records.append(entry)
    records.sort(key=lambda x: x.get("snapshot_date_utc", ""))
    archive["records"] = records[-400:]
    archive["updated_at"] = now.isoformat()
    archive["record_count"] = len(archive["records"])
    archive["production_use"] = False
    archive["production_ready"] = False

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": archive["status"],
        "record_count": archive["record_count"],
        "snapshot_date_utc": entry["snapshot_date_utc"],
        "core": (state.get("core_test_status") or {}).get("code"),
        "recommendations": {z["zone_id"]: z["recommendation"]["code"] for z in entry["zones"]},
        "pedregal_shadow": entry["lima_east_local_shadow"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
