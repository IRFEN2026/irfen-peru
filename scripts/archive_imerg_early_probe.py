#!/usr/bin/env python3
"""Archiva latencia, continuidad y acumulados subdiarios IMERG Early.

El archivo resultante es estrictamente experimental. Conserva los gránulos
muestreados sobre San Ildefonso, Huaycoloro, Pedregal y Catacaos/Bajo Piura;
calcula ventanas 3 h / 6 h / 24 h solo cuando existe continuidad temporal
suficiente y mantiene casos retrospectivos sin efecto operativo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "site/data/calibration/imerg_early_live_probe.json"
ARCHIVE = ROOT / "site/data/calibration/imerg_early_live_archive.json"
MAX_PROBE_RECORDS = 240
MAX_GRANULE_RECORDS = 400  # > 7 días a resolución de 30 min.
WINDOWS = {"3h": 6, "6h": 12, "24h": 48}
EVENT_CASES = [
    {
        "case_id": "PI-2026-08-14-LOCAL-RAIN",
        "zone_id": "catacaos",
        "target_id": "catacaos",
        "local_date": "2026-08-14",
        "timezone": "America/Lima",
        "start_utc": "2026-08-14T05:00:00+00:00",
        "end_utc": "2026-08-15T05:00:00+00:00",
        "purpose": "Contrastar una lluvia local reportada en Piura sin modificar umbrales ni emitir alertas.",
    }
]


def phase2_event_cases():
    cases = []
    intake_dir = ROOT / "site/data/validation/phase2_event_intake"
    for path in sorted(intake_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("status") != "VERIFIED_EVENT_RESEARCH_ONLY":
            continue
        if (row.get("analysis") or {}).get("status") != "READY_FOR_REANALYSIS":
            continue
        occurrence = parse_time((row.get("reported_event") or {}).get("occurrence_time_local"))
        if occurrence is None:
            continue
        occurrence = occurrence.astimezone(timezone.utc)
        event_id = row["event_id"]
        cases.append({
            "case_id": event_id,
            "zone_id": None,
            "target_id": f"phase2_event:{event_id}",
            "local_date": (row.get("reported_event") or {}).get("reported_date_local"),
            "timezone": "America/Lima",
            "start_utc": (occurrence - timedelta(hours=24)).isoformat(),
            "end_utc": occurrence.isoformat(),
            "purpose": "Reanalisis RESEARCH_ONLY de un impacto oficial; no activa zonas ni calibra umbrales.",
            "deployment_status": "RESEARCH_ONLY",
            "counts_toward_v08_closeout": False,
        })
    return cases


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
            "sampling_method": (row.get("sampling") or {}).get("sampling_method"),
            "sampling_areas": (row.get("sampling") or {}).get("sampling_areas"),
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


def validated_window_for_target(granules, target_id, n):
    """Return the newest historically validated continuous window for a target.

    Rolling availability can legitimately become false after a delayed probe or
    a temporary upstream gap.  That must not erase an earlier, auditable
    validation of the same window length.  This helper therefore searches the
    retained archive for the newest complete window while keeping the live
    rolling calculation separate.
    """
    by_time = {}
    for granule in granules:
        timestamp = parse_time(granule.get("time_utc"))
        if timestamp is None:
            continue
        target = next(
            (row for row in granule.get("targets", []) if row.get("target_id") == target_id),
            None,
        )
        if not target or target.get("accum_30min_mm") is None:
            continue
        by_time[timestamp] = float(target["accum_30min_mm"])

    series = sorted(by_time.items())
    for end_index in range(len(series) - 1, n - 2, -1):
        window = series[end_index - n + 1:end_index + 1]
        gaps = [
            (window[index][0] - window[index - 1][0]).total_seconds() / 60.0
            for index in range(1, len(window))
        ]
        span_minutes = (window[-1][0] - window[0][0]).total_seconds() / 60.0
        expected_span = (n - 1) * 30
        continuous = (
            all(20 <= gap <= 40 for gap in gaps)
            and abs(span_minutes - expected_span) <= 10
        )
        if continuous:
            return {
                "available": True,
                "required_samples": n,
                "available_samples": n,
                "continuous": True,
                "start_utc": window[0][0].isoformat(),
                "end_utc": window[-1][0].isoformat(),
                "span_minutes": round(span_minutes, 1),
                "accum_mm": round(sum(value for _, value in window), 3),
                "evidence_basis": "retained_historical_continuous_window",
            }

    return {
        "available": False,
        "required_samples": n,
        "available_samples": min(len(series), n),
        "continuous": False,
        "start_utc": None,
        "end_utc": None,
        "span_minutes": None,
        "accum_mm": None,
        "evidence_basis": "no_retained_historical_continuous_window",
    }


def validated_windows_summary(granules):
    """Preserve cumulative window-validation evidence independently of live state."""
    target_ids = []
    for granule in granules:
        for target in granule.get("targets", []):
            target_id = target.get("target_id")
            if target_id and target_id not in target_ids:
                target_ids.append(target_id)
    return {
        target_id: {
            name: validated_window_for_target(granules, target_id, count)
            for name, count in WINDOWS.items()
        }
        for target_id in target_ids
    }


def continuity_summary(granules):
    """Resume huecos de la serie sin confundir cantidad con continuidad."""
    times = sorted({
        t for t in (parse_time(g.get("time_utc")) for g in granules)
        if t is not None
    })
    if not times:
        return {
            "expected_interval_minutes": 30,
            "observed_unique_timestamps": 0,
            "expected_timestamps_within_span": 0,
            "missing_half_hour_slots_within_span": 0,
            "continuity_coverage_pct": None,
            "current_continuous_tail_samples": 0,
            "current_continuous_tail_hours": 0.0,
            "longest_continuous_run_samples": 0,
            "longest_continuous_run_hours": 0.0,
        }

    expected = int(round((times[-1] - times[0]).total_seconds() / 1800.0)) + 1
    missing = max(0, expected - len(times))
    runs = []
    current = 1
    for previous, observed in zip(times, times[1:]):
        gap_minutes = (observed - previous).total_seconds() / 60.0
        if 20 <= gap_minutes <= 40:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    longest = max(runs)
    tail = runs[-1]

    return {
        "expected_interval_minutes": 30,
        "observed_unique_timestamps": len(times),
        "expected_timestamps_within_span": expected,
        "missing_half_hour_slots_within_span": missing,
        "continuity_coverage_pct": round(100.0 * len(times) / expected, 1),
        "current_continuous_tail_samples": tail,
        "current_continuous_tail_hours": round(tail * 0.5, 1),
        "longest_continuous_run_samples": longest,
        "longest_continuous_run_hours": round(longest * 0.5, 1),
    }


def probe_cadence_summary(records):
    """Describe observed probe spacing without confusing it with data continuity."""
    times = sorted({
        timestamp
        for timestamp in (parse_time(row.get("probe_generated_at")) for row in records)
        if timestamp is not None
    })
    gaps = [
        (observed - previous).total_seconds() / 3600.0
        for previous, observed in zip(times, times[1:])
    ]
    return {
        "probe_timestamp_count": len(times),
        "probe_interval_count": len(gaps),
        "latest_probe_generated_at": times[-1].isoformat() if times else None,
        "probe_gap_median_hours": percentile(gaps, 0.5),
        "probe_gap_p90_hours": percentile(gaps, 0.9),
        "probe_gap_max_hours": round(max(gaps), 2) if gaps else None,
        "interpretation": (
            "Observed workflow cadence only; granule continuity is measured independently."
        ),
    }


def build_event_replays(granules, cases=None):
    replays = []
    for case in (EVENT_CASES + phase2_event_cases() if cases is None else cases):
        start = parse_time(case["start_utc"])
        end = parse_time(case["end_utc"])
        expected_samples = int((end - start).total_seconds() / 1800)
        samples = []
        for granule in granules:
            timestamp = parse_time(granule.get("time_utc"))
            if timestamp is None or not (start <= timestamp < end):
                continue
            target = next(
                (row for row in granule.get("targets", []) if row.get("target_id") == case["target_id"]),
                None,
            )
            if not target or target.get("accum_30min_mm") is None:
                continue
            samples.append((timestamp, float(target["accum_30min_mm"]), target.get("rate_mm_hr")))

        samples.sort(key=lambda row: row[0])
        unique = {row[0]: row for row in samples}
        samples = [unique[key] for key in sorted(unique)]
        gaps = [
            (samples[i][0] - samples[i - 1][0]).total_seconds() / 60.0
            for i in range(1, len(samples))
        ]
        continuous = (
            len(samples) == expected_samples
            and samples[0][0] == start
            and samples[-1][0] == end - timedelta(minutes=30)
            and all(20 <= gap <= 40 for gap in gaps)
        ) if samples else False
        partial_accum = round(sum(row[1] for row in samples), 3) if samples else None
        rates = [float(row[2]) for row in samples if row[2] is not None]
        replays.append({
            **case,
            "production_use": False,
            "decision_use": "TEST_ONLY",
            "status": "COMPLETE" if continuous else "ACCUMULATING",
            "expected_samples": expected_samples,
            "available_samples": len(samples),
            "coverage_pct": round(100.0 * len(samples) / expected_samples, 1),
            "continuous": continuous,
            "partial_accum_mm": partial_accum,
            "complete_accum_mm": partial_accum if continuous else None,
            "max_rate_mm_hr": round(max(rates), 4) if rates else None,
            "interpretation": (
                "Satellite accumulation complete; official station/event evidence is still required for local corroboration."
                if continuous else
                "Partial satellite accumulation only; absence or low values cannot be interpreted as absence of local rain."
            ),
        })
    return replays


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
    validated_windows = validated_windows_summary(granules)
    continuity = continuity_summary(granules)
    probe_cadence = probe_cadence_summary(records)
    event_replays = build_event_replays(granules)

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
        "validated_windows_by_target": validated_windows,
        "event_replays": event_replays,
        "summary": {
            "probe_record_count": len(records),
            "source_available_count": len(available),
            "source_available_pct": round(100.0 * len(available) / len(records), 1) if records else None,
            "granule_record_count": len(granules),
            "granule_time_min_utc": min(granule_times).isoformat() if granule_times else None,
            "granule_time_max_utc": max(granule_times).isoformat() if granule_times else None,
            **continuity,
            **probe_cadence,
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
            "historical_window_validation_is_test_only": True,
            "event_replays_are_test_only": True,
            "local_rain_requires_official_or_ground_control": True,
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
