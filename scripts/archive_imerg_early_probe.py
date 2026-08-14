#!/usr/bin/env python3
"""Archiva evidencia compacta de latencia/continuidad del probe IMERG Early."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "site/data/calibration/imerg_early_live_probe.json"
ARCHIVE = ROOT / "site/data/calibration/imerg_early_live_archive.json"
MAX_RECORDS = 240


def percentile(values, q):
    vals = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not vals:
        return None
    if len(vals) == 1:
        return round(vals[0], 2)
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return round(vals[lo] * (1 - frac) + vals[hi] * frac, 2)


def main():
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    if ARCHIVE.exists():
        archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    else:
        archive = {
            "version": "0.8-experimental",
            "production_use": False,
            "production_ready": False,
            "source": "GPM_3IMERGHHE V07 via Earthdata",
            "records": [],
        }

    latest_targets = []
    samples = latest.get("samples") or []
    if samples:
        for row in samples[-1].get("targets", []):
            latest_targets.append({
                "target_id": row.get("target_id"),
                "rate_mm_hr": row.get("rate_mm_hr"),
                "accum_30min_mm": row.get("accum_30min_mm"),
                "valid_cells": (row.get("sampling") or {}).get("valid_cells"),
            })

    record = {
        "probe_generated_at": latest.get("generated_at"),
        "status": latest.get("status"),
        "latest_granule_time_utc": latest.get("latest_granule_time_utc"),
        "latency_hours": latest.get("observed_latency_hours_at_probe"),
        "granules_found": latest.get("granules_found"),
        "granules_downloaded": latest.get("granules_downloaded"),
        "latest_targets": latest_targets,
    }
    records = archive.get("records") or []
    key = (record.get("probe_generated_at"), record.get("latest_granule_time_utc"))
    if not any((r.get("probe_generated_at"), r.get("latest_granule_time_utc")) == key for r in records):
        records.append(record)
    records = records[-MAX_RECORDS:]

    latencies = [r.get("latency_hours") for r in records if r.get("latency_hours") is not None]
    available = [r for r in records if r.get("status") == "EARLY_HALFHOURLY_SOURCE_AVAILABLE"]
    archive.update({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
        "summary": {
            "record_count": len(records),
            "source_available_count": len(available),
            "source_available_pct": round(100.0 * len(available) / len(records), 1) if records else None,
            "latency_min_hours": round(min(latencies), 2) if latencies else None,
            "latency_median_hours": percentile(latencies, 0.5),
            "latency_p90_hours": percentile(latencies, 0.9),
            "latency_max_hours": round(max(latencies), 2) if latencies else None,
            "initial_review_min_records": 12,
        },
        "scientific_gate": {
            "status": "ACCUMULATING_LATENCY_AND_CONTINUITY_EVIDENCE",
            "production_use": False,
            "rule": "No promote IMERG Early to a live decision input solely from source availability; review continuity, latency and representativeness first.",
        },
    })
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(archive["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
