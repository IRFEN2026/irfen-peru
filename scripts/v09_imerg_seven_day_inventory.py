"""Offline seven-day historical IMERG granule inventory (UTC).

Research only: inventory timestamps, never infer rain values or station matches.
Expected window: 2026-10-30 00:00Z inclusive to 2026-11-06 00:00Z exclusive.
Input JSON: {"granules": [{"observation_time": "...Z", "sha256": "..."}]}.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

START = datetime(2026, 10, 30, tzinfo=timezone.utc)
END = datetime(2026, 11, 6, tzinfo=timezone.utc)
STEP = timedelta(minutes=30)

def parse_utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("observation_time must be explicit UTC Z")
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.second or dt.microsecond or dt.minute not in (0, 30):
        raise ValueError("not aligned to 30-minute UTC granule")
    return dt

def inventory(records):
    expected = []
    t = START
    while t < END:
        expected.append(t)
        t += STEP
    seen, duplicate, malformed, out_of_window = set(), [], [], []
    for item in records:
        try:
            dt = parse_utc(item["observation_time"])
            sha = item["sha256"]
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise ValueError("invalid sha256")
            if dt < START or dt >= END:
                out_of_window.append(dt.isoformat())
                continue
            if dt in seen:
                duplicate.append(dt.isoformat())
            seen.add(dt)
        except (KeyError, ValueError, TypeError) as exc:
            malformed.append(str(exc))
    missing = [t.isoformat() for t in expected if t not in seen]
    return {
        "status": "COMPLETE" if not missing and not duplicate and not malformed and not out_of_window else "INCOMPLETE",
        "window_start": START.isoformat(), "window_end_exclusive": END.isoformat(),
        "expected_half_hours": len(expected),
        "present_half_hours": len(set(expected) & seen),
        "missing_half_hours": missing, "duplicate_half_hours": duplicate,
        "invalid_records": malformed, "out_of_window": out_of_window,
        "note": "Completeness of metadata only; does not validate HDF5 values, spatial coverage or rain accuracy"
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(inventory(json.loads(args.manifest.read_text())["granules"]), indent=2))
