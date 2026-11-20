"""Offline, dependency-free UTC/PET window and interval audit for IRFEN #496.

RESEARCH_ONLY: never fetches data, calibrates rain, or emits alerts.
"""
from datetime import datetime, timedelta, timezone

PET = timezone(timedelta(hours=-5))
UTC = timezone.utc

def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError("explicit UTC timestamp required")
    return dt.astimezone(UTC)

def audit_window(start_utc: str, end_utc: str, observations: list[str], minutes: int = 30) -> dict:
    """Require half-open [start,end) interval starts; report missing/duplicate/outside, never fill zeros."""
    start, end = parse_utc(start_utc), parse_utc(end_utc)
    if minutes <= 0 or 1440 % minutes or end <= start:
        raise ValueError("invalid cadence or window")
    step = timedelta(minutes=minutes)
    if (end - start) % step:
        raise ValueError("window not aligned to cadence")
    expected = [start + i * step for i in range((end - start) // step)]
    actual = [parse_utc(v) for v in observations]
    seen = set(actual)
    missing = sorted(set(expected) - seen)
    duplicates = sorted({x for x in actual if actual.count(x) > 1})
    outside = sorted({x for x in actual if x < start or x >= end or (x-start) % step})
    fmt = lambda xs: [x.isoformat().replace("+00:00", "Z") for x in xs]
    return {
        "start_utc": fmt([start])[0], "end_utc_exclusive": fmt([end])[0],
        "start_pet": start.astimezone(PET).isoformat(),
        "end_pet_exclusive": end.astimezone(PET).isoformat(),
        "expected_intervals": len(expected), "received_records": len(actual),
        "missing_interval_starts_utc": fmt(missing),
        "duplicate_interval_starts_utc": fmt(duplicates),
        "outside_or_misaligned_utc": fmt(outside),
        "complete": not (missing or duplicates or outside),
        "missing_is_zero": False,
    }
