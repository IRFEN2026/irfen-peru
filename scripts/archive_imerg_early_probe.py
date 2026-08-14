#!/usr/bin/env python3
"""Archiva latencia, continuidad y acumulados subdiarios IMERG Early.

El archivo resultante es estrictamente experimental. Conserva los gránulos
muestreados sobre San Ildefonso, Huaycoloro y Pedregal y calcula ventanas
3 h / 6 h / 24 h solo cuando existe continuidad temporal suficiente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "site/data/calibration/imerg_early_live_probe.json"
ARCHIVE = ROOT / "site/data/calibration/imerg_early_live_archive.json"
MAX_PROBE_RECORDS = 240
MAX_GRANULE_RECORDS = 400  # > 7 días a resolución de 30 min.
WINDOWS = {"3h": 6, "6h": 12, "24h": 48}


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


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def compact_targets(sample):
    rows = []
    for row in sample.get("targets", []):
        rows.append({
            "target_id": row.get("target_id"),
            "name": row.get("name"),
            "rate_mm_hr": row.get("rate_mm_hr"),
            "accum_30min_mm": row.get("accum_30min_mm"),
            "valid_cells": (row.get("sampling") or {}).get("valid_cells"),
            "grid_resolution_deg": (row.get("sampling") or {}).get("grid_resolution_deg"),
        })
    return rows


def dedupe_granules(existing, samples):
    by_key = {}
    for row in existing:
        key = (row.get("time_utc"), row.get("granule"))
        by_key[key] = row
    for sample in samples:
        row = {
            "time_utc": sample.get("time_utc"),
            "granule": sample.get("granule"),
            "units": sample.get("units"),
            "targets": compact_targets(sample),
        }
        key = (row.get("time_utc"), row.get("granule"))
        by_key[key] = row
    rows = list(by_key.values())
    rows.sort(key=lambda r: parse_time(r.get("time_utc")) or datetime.min.replace(tzinfo=timezone.utc))
    return rows[-MAX_GRANULE_RECORDS:]


def rolling_for_target(granules, target_id, n):
    series = []
    for g in granules:
        t = parse_time(g.get("time_utc"))
        if t is None:
            continue
        target = next((x for x in g.get("targets", []) if x.get("target_id") == target_id), None)
        if not target or target.get("accum_30min_mm") is None:
            continue
        series.append((t, float(target["accum_30min_mm"])))
    series.sort(key=lambda x: x[0])

    if len(series) < n:
        return {
            "available": False,
            "required_samples": n,
            "available_samples": len(series),
            "continuous": False,
            "accum_mm": None,
        }

    window = series[-n:]
    gaps = [(window[i][0] - window[i - 1][0]).total_seconds() / 60.0 for i in range(1, len(window))]
    continuous = all(20 <= gap <= 40 for gap in gaps)
    span_minutes = (window[-1][0] - window[0][0]).total_seconds() / 60.0
    expected_span = (n - 1) * 30
    continuous = continuous and abs(span_minutes - expected_span) <= 10

    return {
        "available": bool(continuous),
        "required_samples": n,
        "available_samples": n,
        "continuous": bool(continuous),
        "start_utc": window[0][0].isoformat(),
        "end_utc": window[-1][0].isoformat(),
        "span_minutes": round(span_minutes, 1),
        "accum_mm": round(sum(v for _, v in window), 3) if continuous else None,
    }


def rolling_summary(granules):
    target_ids = []
    for g in granules:
        for target in g.get("targets", []):
            tid = target.get("target_id")
            if tid and tid not in target_ids:
                target_ids.append(tid)

    out = {}
    for tid in target_ids:
        out[tid] = {name: rolling_for_target(granules, tid, n) for name, n in WINDOWS.items()}
    return out


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
            "granules": [],
        }

    samples = latest.get("samples") or []
    latest_targets = compact_targets(samples[-1]) if samples else []
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
    records = records[-MAX_PROBE_RECORDS:]

    granules = dedupe_granules(archive.get("granules") or [], samples)
    rolling = rolling_summary(granules)

    latencies = [r.get("latency_hours") for r in records if r.get("latency_hours") is not None]
    available = [r for r in records if r.get("status") == "EARLY_HALFHOURLY_SOURCE_AVAILABLE"]
    granule_times = [parse_time(g.get("time_utc")) for g in granules]
    granule_times = [t for t in granule_times if t is not None]

    complete_24h_targets = [
        tid for tid, values in rolling.items()
        if (values.get("24h") or {}).get("available") is True
    ]

    archive.update({
        "version": "0.8-experimental",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "source": "GPM_3IMERGHHE V07 via Earthdata",
        "records": records,
        "granules": granules,
        "rolling_by_target": rolling,
        "summary": {
            "probe_record_count": len(records),
            "source_available_count": len(available),
            "source_available_pct": round(100.0 * len(available) / len(records), 1) if records else None,
            "granule_record_count": len(granules),
            "granule_time_min_utc": min(granule_times).isoformat() if granule_times else None,
            "granule_time_max_utc": max(granule_times).isoformat() if granule_times else None,
            "targets_with_continuous_24h": complete_24h_targets,
            "latency_min_hours": round(min(latencies), 2) if latencies else None,
            "latency_median_hours": percentile(latencies, 0.5),
            "latency_p90_hours": percentile(latencies, 0.9),
            "latency_max_hours": round(max(latencies), 2) if latencies else None,
            "initial_latency_review_min_records": 12,
            "initial_24h_continuity_goal": "48 consecutive half-hour samples per target",
        },
        "scientific_gate": {
            "status": "ACCUMULATING_LATENCY_AND_CONTINUITY_EVIDENCE",
            "production_use": False,
            "rule": "No promover IMERG Early a entrada de decisión en vivo por disponibilidad técnica únicamente; primero revisar continuidad, latencia y representatividad espacial.",
            "rolling_windows_are_test_only": True,
        },
    })
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "summary": archive["summary"],
        "rolling_by_target": archive["rolling_by_target"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
