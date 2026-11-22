#!/usr/bin/env python3
"""Offline fail-closed QA for IMERG coverage nulls. RESEARCH_ONLY / TEST_ONLY.

Input: JSON list of records, each with department, area_id, period_start_utc,
period_end_utc, expected_intervals, valid_intervals, coverage_fraction,
rain_mm and null_reason. No downloads, no imputation, no predictions.
"""
import argparse
import datetime as dt
import json
import math

COAST = frozenset(("Tumbes", "Piura", "Lambayeque", "La Libertad",
                   "Áncash", "Lima", "Ica", "Arequipa", "Moquegua", "Tacna",
                   "Callao"))
REASONS = frozenset(("insufficient_spatial_coverage", "missing_granule",
                     "missing_measurement", "invalid_source", "unknown"))

def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("UTC timestamp must end with Z")
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamp must be UTC")
    return parsed

def classify(row, threshold=0.8):
    """Return a verdict, never replace null precipitation with zero."""
    if not isinstance(row, dict):
        raise ValueError("record must be object")
    if row.get("department") not in COAST:
        raise ValueError("unknown or noncoastal department")
    if not isinstance(row.get("area_id"), str) or not row["area_id"].strip():
        raise ValueError("area_id required")
    start, end = utc(row.get("period_start_utc")), utc(row.get("period_end_utc"))
    seconds = (end - start).total_seconds()
    if seconds <= 0 or seconds % 1800:
        raise ValueError("period must contain whole half-hours")
    expected = row.get("expected_intervals")
    valid = row.get("valid_intervals")
    if type(expected) is not int or expected != seconds // 1800:
        raise ValueError("expected_intervals inconsistent with period")
    if type(valid) is not int or not 0 <= valid <= expected:
        raise ValueError("invalid valid_intervals")
    fraction = row.get("coverage_fraction")
    if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("coverage_fraction must be finite in [0,1]")
    if type(threshold) not in (int, float) or not 0 < threshold <= 1:
        raise ValueError("invalid threshold")
    rain = row.get("rain_mm")
    reason = row.get("null_reason")
    if rain is None:
        if reason not in REASONS:
            raise ValueError("null rain requires explicit recognized null_reason")
        return "NULL_COVERAGE" if reason == "insufficient_spatial_coverage" else "NULL_OTHER"
    if reason is not None:
        raise ValueError("non-null rain cannot carry null_reason")
    if type(rain) not in (int, float) or not math.isfinite(rain) or rain < 0:
        raise ValueError("rain_mm must be finite nonnegative number")
    if valid != expected or fraction < threshold:
        raise ValueError("rain cannot be accepted with incomplete temporal/spatial coverage")
    return "VALID_ZERO" if rain == 0 else "VALID_RAIN"

def audit(rows):
    if not isinstance(rows, list):
        raise ValueError("input must be JSON list")
    results, seen = [], set()
    for row in rows:
        verdict = classify(row)
        key = (row["department"], row["area_id"], row["period_start_utc"], row["period_end_utc"])
        if key in seen:
            raise ValueError("duplicate area/period")
        seen.add(key)
        results.append({"department": row["department"], "area_id": row["area_id"],
                        "period_start_utc": row["period_start_utc"],
                        "period_end_utc": row["period_end_utc"], "verdict": verdict})
    return {"mode": "RESEARCH_ONLY", "scientific_skill": "NO_EVALUABLE",
            "records": results, "count": len(results),
            "null_coverage": sum(x["verdict"] == "NULL_COVERAGE" for x in results),
            "departments_present": sorted({x["department"] for x in results}),
            "departments_missing": sorted(COAST - {x["department"] for x in results})}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json")
    args = parser.parse_args()
    with open(args.input_json, encoding="utf-8") as source:
        data = json.load(source)
    print(json.dumps(audit(data), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
