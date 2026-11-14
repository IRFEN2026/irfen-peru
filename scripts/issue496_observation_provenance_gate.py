"""Fail-closed provenance gate for independent rainfall station observations.

RESEARCH_ONLY / TEST_ONLY. No network calls or calibration.
A press/COEN transcription is documentary evidence, never an instrumental pair.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

REQUIRED = (
    "station_id", "observed_mm", "period_start_utc", "period_end_utc",
    "observed_at_utc", "available_at_utc", "source_kind",
    "source_sha256", "latitude", "longitude", "datum", "unit",
    "instrument_qc", "product_version",
)
INSTRUMENTAL = {"instrumental_original", "official_instrumental_export"}


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("timestamps must be explicit UTC")
    return dt


def evaluate(row, source_bytes=None, issue_time_utc=None):
    """Return (status, reasons); never impute nulls or infer release time."""
    reasons = []
    if not isinstance(row, dict):
        return "NO_EVALUABLE", ["not_an_object"]
    for key in REQUIRED:
        if row.get(key) is None or row.get(key) == "":
            reasons.append("missing:" + key)
    if row.get("source_kind") not in INSTRUMENTAL:
        reasons.append("not_instrumental_original")
    if row.get("unit") != "mm":
        reasons.append("unit_not_mm")
    if row.get("datum") != "WGS84":
        reasons.append("datum_unverified")
    if row.get("instrument_qc") != "PASS":
        reasons.append("instrument_qc_not_pass")
    if isinstance(row.get("observed_mm"), bool):
        reasons.append("invalid_rainfall")
    try:
        amount = float(row["observed_mm"])
        if not math.isfinite(amount) or amount < 0:
            reasons.append("invalid_rainfall")
    except (ValueError, TypeError, KeyError):
        reasons.append("invalid_rainfall")
    if isinstance(row.get("latitude"), bool) or isinstance(row.get("longitude"), bool):
        reasons.append("invalid_coordinates")
    try:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            reasons.append("invalid_coordinates")
    except (ValueError, TypeError, KeyError):
        reasons.append("invalid_coordinates")
    try:
        start, end = _utc(row["period_start_utc"]), _utc(row["period_end_utc"])
        observed, available = _utc(row["observed_at_utc"]), _utc(row["available_at_utc"])
        if not start < end or not start <= observed <= end:
            reasons.append("invalid_observation_window")
        if available < end:
            reasons.append("available_before_period_end")
        if issue_time_utc is not None and available > _utc(issue_time_utc):
            reasons.append("future_data_leakage")
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append("invalid_timestamps")
    sha = row.get("source_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        reasons.append("invalid_sha256")
    if source_bytes is None:
        reasons.append("original_bytes_not_verified")
    elif not isinstance(source_bytes, bytes) or hashlib.sha256(source_bytes).hexdigest() != sha:
        reasons.append("original_sha256_mismatch")
    return ("NO_EVALUABLE", sorted(set(reasons))) if reasons else ("PAIR_CANDIDATE", [])


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--issue-time-utc")
    args = p.parse_args()
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("Expected JSON array")
    source_bytes = args.original.read_bytes()
    print(json.dumps([dict(station_id=r.get("station_id"), status=s, reasons=why)
        for r in rows for s, why in [evaluate(r, source_bytes, args.issue_time_utc)]],
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
