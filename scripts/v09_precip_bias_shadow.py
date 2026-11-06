"""Experimental, fail-closed station/pixel precipitation bias evaluation.

No alert thresholds, deployment or operational calibration. Standard library only.
Inputs are verified *collocated* event pairs with independent provenance.
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
from pathlib import Path

HORIZONS = (1, 3, 6, 12, 24)
REQUIRED = ("station_id", "event_id", "department", "observation_start",
            "observation_end", "available_at", "station_source_sha256",
            "imerg_source_sha256", "station_mm", "pixel_mm", "qc")

def _finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0

def validate(row):
    missing = [key for key in REQUIRED if key not in row or row[key] is None]
    if missing:
        raise ValueError("missing required original evidence: " + ",".join(missing))
    for key in ("station_mm", "pixel_mm"):
        if not _finite_nonnegative(row[key]):
            raise ValueError("invalid precipitation " + key)
    if row["qc"] != "VERIFIED":
        raise ValueError("unverified station/pixel pair")
    for key in ("station_source_sha256", "imerg_source_sha256"):
        if len(row[key]) != 64 or any(c not in "0123456789abcdef" for c in row[key]):
            raise ValueError("invalid SHA256 " + key)
    if row["observation_start"] >= row["observation_end"]:
        raise ValueError("invalid time window")
    if row["available_at"] < row["observation_end"]:
        raise ValueError("availability predates observation end")
    if row.get("spatial_match") != "STATION_PIXEL":
        raise ValueError("station must be compared with its pixel, not a basin mean")
    if row.get("window_complete") is not True:
        raise ValueError("incomplete satellite interval")
    if row.get("units") != "mm":
        raise ValueError("units must be accumulated mm")
    return row

def metrics(rows, predictions):
    errors = [p - r["station_mm"] for r, p in zip(rows, predictions)]
    return {
        "n": len(rows),
        "mae_mm": sum(map(abs, errors)) / len(errors),
        "bias_mm": sum(errors) / len(errors),
        "rmse_mm": math.sqrt(sum(e * e for e in errors) / len(errors)),
    }

def evaluate(pairs, min_training_events=3, min_test_events=2):
    """Leave-one-event-out; no record of held-out event used to fit its factor.

    Event-level split prevents station observations from the same storm leaking
    into training. For now, only a scalar training-only ratio is considered;
    evaluation is a research diagnostic, NOT a deployable correction.
    """
    try:
        rows = [validate(dict(r)) for r in pairs]
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "NO_EVALUABLE", "reason": str(exc), "n": 0}
    events = sorted({r["event_id"] for r in rows})
    if len(events) < min_training_events + min_test_events:
        return {"status": "NO_EVALUABLE", "reason": "insufficient independent events",
                "events": len(events), "n": len(rows)}
    original, corrected, held = [], [], []
    for event in events:
        training = [r for r in rows if r["event_id"] != event]
        test = [r for r in rows if r["event_id"] == event]
        if len({r["event_id"] for r in training}) < min_training_events:
            continue
        denominator = sum(r["pixel_mm"] for r in training)
        if denominator <= 0:
            return {"status": "NO_EVALUABLE", "reason": "zero satellite training rain",
                    "events": len(events), "n": len(rows)}
        factor = sum(r["station_mm"] for r in training) / denominator
        if not math.isfinite(factor):
            return {"status": "NO_EVALUABLE", "reason": "nonfinite factor"}
        for row in test:
            held.append(row)
            original.append(row["pixel_mm"])
            corrected.append(row["pixel_mm"] * factor)
    if len({r["event_id"] for r in held}) < min_test_events:
        return {"status": "NO_EVALUABLE", "reason": "insufficient held-out events"}
    raw = metrics(held, original)
    experimental = metrics(held, corrected)
    return {"status": "EVALUATED_RESEARCH_ONLY", "events": len(events),
            "n": len(held), "raw": raw, "shadow": experimental,
            "mae_improvement_mm": raw["mae_mm"] - experimental["mae_mm"],
            "warning": "No operational factor; independent prospective validation required"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    pairs = json.loads(args.pairs_json.read_text(encoding="utf-8"))
    result = evaluate(pairs)
    rendered = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("refusing to overwrite frozen report")
        args.output.open("x", encoding="utf-8").write(rendered)
    else:
        print(rendered, end="")

if __name__ == "__main__":
    main()
