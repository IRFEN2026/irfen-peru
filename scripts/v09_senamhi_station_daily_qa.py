#!/usr/bin/env python3
"""IRFEN v0.9: offline, research-only quality checks for SENAMHI qc station TXT files.

Columns: year month day rainfall_mm tmax_C tmin_C.
No network, no live alerting, no inferred station-basin links or rainfall thresholds.
Example:
    python scripts/v09_senamhi_station_daily_qa.py \
        --station 000135=/path/qc00000135.txt \
        --event-date 1998-02-08 --output /tmp/station-qa.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

MISSING = -99.9
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
              production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)


def parse_rows(source: str) -> list[tuple[date, float, float, float]]:
    """Reject bad/duplicate dates and malformed rows, rather than silently patching."""
    rows, seen = [], set()
    for line_no, line in enumerate(source.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 6:
            raise ValueError(f"Line {line_no}: expected six fields, got {len(fields)}")
        try:
            day = date(*(int(v) for v in fields[:3]))
            rain, tmax, tmin = (float(v) for v in fields[3:])
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Line {line_no}: invalid date or numeric value") from exc
        if not all(math.isfinite(v) for v in (rain, tmax, tmin)):
            raise ValueError(f"Line {line_no}: non-finite numeric value")
        if day in seen:
            raise ValueError(f"Line {line_no}: duplicate date {day}")
        seen.add(day)
        rows.append((day, rain, tmax, tmin))
    if not rows:
        raise ValueError("No valid daily rows")
    return sorted(rows, key=lambda r: r[0])


def report_station(station_id: str, raw: bytes, event_day: date | None = None) -> dict:
    rows = parse_rows(raw.decode("utf-8-sig"))
    days = [r[0] for r in rows]
    span_days = (days[-1] - days[0]).days + 1
    valid = [r for r in rows if r[1] >= 0]
    absent = [r for r in rows if r[1] == MISSING]
    invalid = [r for r in rows if r[1] < 0 and r[1] != MISSING]
    october = [r for r in valid if r[0].month == 10]
    october_max = max(october, key=lambda r: r[1]) if october else None
    top = sorted(valid, key=lambda r: (-r[1], r[0]))[:10]
    year_counts = Counter(day.year for day, *_ in valid)
    month_counts = Counter((day.year, day.month) for day, *_ in valid)
    reversed_temp = [str(d) for d, _, tmax, tmin in rows
                     if tmax != MISSING and tmin != MISSING and tmax < tmin]
    event = next((r for r in rows if r[0] == event_day), None) if event_day else None
    if event_day and event is None:
        event_state = dict(date=str(event_day), status="DATA_ABSENT")
    elif event and event[1] < 0:
        event_state = dict(date=str(event_day), status="MISSING_NOT_ZERO")
    elif event:
        event_state = dict(date=str(event_day), status="VALID", daily_precip_mm=event[1])
    else:
        event_state = None
    return dict(
        station_code=station_id, original_sha256=hashlib.sha256(raw).hexdigest(),
        original_bytes=len(raw), raw_archive_included=False,
        first_date=str(days[0]), last_date=str(days[-1]),
        total_rows=len(rows), calendar_days_in_span=span_days,
        missing_calendar_dates=span_days-len(rows),
        precipitation=dict(valid_days=len(valid), missing_sentinel_days=len(absent),
                           invalid_negative_days=len(invalid),
                           explicit_zero_days=sum(r[1] == 0 for r in valid),
                           positive_days=sum(r[1] > 0 for r in valid),
                           top_daily_mm=[dict(date=str(r[0]), mm=r[1]) for r in top],
                           october_valid_days=len(october),
                           october_max_daily_mm=(dict(date=str(october_max[0]), mm=october_max[1])
                                                 if october_max else None),
                           valid_days_by_year={str(y): n for y, n in sorted(year_counts.items())},
                           valid_days_by_year_month={f"{y:04d}-{m:02d}": n
                                                     for (y, m), n in sorted(month_counts.items())}),
        temperature=dict(tmax_valid_days=sum(r[2] != MISSING for r in rows),
                         tmin_valid_days=sum(r[3] != MISSING for r in rows),
                         max_below_min_dates=reversed_temp),
        event_date_observation=event_state,
        quality_notes=["Station coordinates and daily accumulation clock unverified.",
                       "Point rain is not the same variable as an IMERG province-area mean.",
                       "Low or absent rain data never implies low hydrologic risk."])


def station_arg(value: str) -> tuple[str, Path]:
    code, marker, filename = value.partition("=")
    if not marker or not code.isascii() or not code.isdigit() or not filename:
        raise argparse.ArgumentTypeError("Use --station SENAMHI_CODE=/path/qcXXXX.txt")
    return code, Path(filename)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", type=station_arg, action="append", required=True)
    parser.add_argument("--event-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    codes = [code for code, _ in args.station]
    if len(codes) != len(set(codes)):
        parser.error("Duplicate station code")
    stations = [report_station(code, path.read_bytes(), args.event_date)
                for code, path in args.station]
    result = dict(schema_version="0.1",
                  profile_id="irfen-v09-senamhi-station-daily-offline-qa",
                  purpose="Evidence-only SENAMHI station history QA", **GUARDS,
                  map_publishable=False,
                  observation_date=str(args.event_date) if args.event_date else None,
                  observations_are_daily_not_hourly=True,
                  station_to_basin_crosswalk="UNVERIFIED",
                  daily_accumulation_hour="UNVERIFIED",
                  station_to_imerg_point_match="NOT_PERFORMED",
                  stations=stations)
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
