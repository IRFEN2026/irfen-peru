#!/usr/bin/env python3
"""IRFEN Piura station-gauge vs. pixel IMERG calibration (offline, TEST_ONLY).

No network, no credentials, no writes. Expects scientifically pre-collocated,
hourly pairs; NEVER accepts provincial means as if they were rain at a gauge.
This is a feasibility scorer, not an operational rainfall product.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from statistics import mean

REQUIRED = (
    "station_id", "gauge_source", "gauge_observation_id",
    "station_lat", "station_lon",
    "cell_lat_min", "cell_lat_max", "cell_lon_min", "cell_lon_max",
    "start_utc", "end_utc", "gauge_mm", "imerg_cell_mm",
    "imerg_granule_ids", "imerg_product_version", "gauge_provenance_url",
)
MIN_TRAIN_RAIN = 20
MIN_TEST_RAIN = 10
MIN_TEST_DAYS = 14


def utc(s: str) -> datetime:
    if not s or not s.endswith("Z"):
        raise ValueError(f"UTC timestamp must end in Z: {s!r}")
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.utcoffset() != timedelta(0):
        raise ValueError("UTC offset mismatch")
    return d


def finite_rain(s: str, field: str) -> float:
    if not s or s.strip().lower() in {"missing", "na", "null"}:
        raise ValueError(f"{field} MISSING; do not replace missing by zero")
    v = float(s)
    if not math.isfinite(v) or v < 0 or v > 1000:
        raise ValueError(f"{field} must be a finite, physical 0..1000 mm accumulation")
    return v


def validate_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        raise ValueError("No observation pairs supplied")
    seen: set[tuple[str, datetime]] = set()
    out = []
    for n, row in enumerate(rows, start=2):
        if any(not row.get(k) for k in REQUIRED):
            missing = [k for k in REQUIRED if not row.get(k)]
            raise ValueError(f"row {n}: required field(s) blank: {missing}")
        start, end = utc(row["start_utc"]), utc(row["end_utc"])
        if end - start != timedelta(hours=1):
            raise ValueError(f"row {n}: need EXACTLY 1h gauge and pixel interval")
        lat, lon = float(row["station_lat"]), float(row["station_lon"])
        lo_lat, hi_lat = float(row["cell_lat_min"]), float(row["cell_lat_max"])
        lo_lon, hi_lon = float(row["cell_lon_min"]), float(row["cell_lon_max"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"row {n}: invalid station position")
        if not (lo_lat <= lat <= hi_lat and lo_lon <= lon <= hi_lon):
            raise ValueError(f"row {n}: station is outside stated IMERG cell")
        if not (0 < hi_lat - lo_lat <= 0.11 and 0 < hi_lon - lo_lon <= 0.11):
            raise ValueError(f"row {n}: cell should match IMERG native ~0.1 degree")
        granules = [g.strip() for g in row["imerg_granule_ids"].split(";") if g.strip()]
        if len(set(granules)) != 2:
            raise ValueError(f"row {n}: hourly IMERG requires TWO distinct half-hour granules")
        if not row["imerg_product_version"].startswith("V07"):
            raise ValueError(f"row {n}: unsupported/unverified IMERG product version")
        if not row["gauge_provenance_url"].startswith("https://"):
            raise ValueError(f"row {n}: gauge provenance must be a verifiable HTTPS reference")
        key = (row["station_id"], start)
        if key in seen:
            raise ValueError(f"row {n}: duplicated gauge/time observation")
        seen.add(key)
        out.append({
            "station_id": row["station_id"], "start": start, "end": end,
            "gauge": finite_rain(row["gauge_mm"], "gauge_mm"),
            "sat": finite_rain(row["imerg_cell_mm"], "imerg_cell_mm"),
        })
    out.sort(key=lambda z: (z["start"], z["station_id"]))
    return out


def metrics(rows: list[dict], factor: float = 1.0) -> dict:
    if not rows:
        return {"pairs": 0}
    obs = [x["gauge"] for x in rows]
    est = [x["sat"] * factor for x in rows]
    n = len(rows)
    errs = [p - y for p, y in zip(est, obs)]
    xm, ym = mean(est), mean(obs)
    sx = sum((x - xm)**2 for x in est)
    sy = sum((y - ym)**2 for y in obs)
    r = (
        sum((x - xm)*(y - ym) for x, y in zip(est, obs)) / math.sqrt(sx*sy)
        if sx > 0 and sy > 0 else None
    )
    by_threshold = {}
    for threshold in (1., 10., 25., 50.):
        hits = sum(y >= threshold and p >= threshold for y,p in zip(obs,est))
        false_alarms = sum(y < threshold and p >= threshold for y,p in zip(obs,est))
        misses = sum(y >= threshold and p < threshold for y,p in zip(obs,est))
        by_threshold[str(int(threshold))] = {
            "events": hits+misses,
            "hits": hits, "false_alarms": false_alarms, "misses": misses,
            "POD": round(hits/(hits+misses),4) if hits+misses else None,
            "FAR": round(false_alarms/(hits+false_alarms),4) if hits+false_alarms else None,
        }
    return {
        "pairs": n,
        "rain_hours_gauge_gt_0_1mm": sum(y > 0.1 for y in obs),
        "bias_mm": round(mean(errs),4),
        "MAE_mm": round(mean([abs(e) for e in errs]),4),
        "RMSE_mm": round(math.sqrt(mean([e*e for e in errs])),4),
        "pearson_r": round(r,4) if r is not None else None,
        "thresholds": by_threshold,
    }


def report(rows: list[dict]) -> dict:
    rows = validate_rows(rows)
    days = sorted({r["start"].date() for r in rows})
    n = len(rows)
    descriptive = metrics(rows)
    out = {
        "schema_version": "0.1", "status": "NOT_VALIDATED",
        "research_only": True, "alerting_enabled": False, "publication_enabled": False,
        "n_total_pairs": n, "n_stations": len({r["station_id"] for r in rows}),
        "n_unique_days": len(days), "raw_all_pairs_descriptive_ONLY": descriptive,
        "warning": "No calibrated results until temporally independent and rainy evaluation samples exist",
    }
    if len(days) < MIN_TEST_DAYS + 30:
        out["blocker"] = "INSUFFICIENT_DISTINCT_DAYS"
        return out
    cut = max(1, int(len(days)*0.7))
    train_days = set(days[:cut])
    tr = [r for r in rows if r["start"].date() in train_days]
    te = [r for r in rows if r["start"].date() not in train_days]
    nr_train = sum(r["gauge"] > 0.1 for r in tr)
    nr_test = sum(r["gauge"] > 0.1 for r in te)
    out["split"] = {
        "train_end_date": str(days[cut-1]), "test_start_date": str(days[cut]),
        "training_pairs": len(tr), "test_pairs": len(te),
        "training_rain_hours": nr_train, "test_rain_hours": nr_test
    }
    if nr_train < MIN_TRAIN_RAIN or nr_test < MIN_TEST_RAIN:
        out["blocker"] = "INSUFFICIENT_INDEPENDENT_RAIN_HOURS"
        return out
    rainy_pixel = [r for r in tr if r["sat"] > 0.1]
    if len(rainy_pixel) < MIN_TRAIN_RAIN or sum(r["sat"] for r in rainy_pixel) == 0:
        out["blocker"] = "PIXEL_RAIN_EVENTS_INSUFFICIENT_FOR_BIAS_FIT"
        return out
    factor = max(0.25,min(4.0,
        sum(r["gauge"] for r in rainy_pixel)/sum(r["sat"] for r in rainy_pixel)))
    out["candidate"] = {"name": "train-only capped multiplicative bias", "factor": round(factor,4)}
    out["test_imerg_raw"] = metrics(te)
    out["test_candidate"] = metrics(te, factor)
    out["delta_test_MAE_mm"] = round(
        out["test_imerg_raw"]["MAE_mm"] - out["test_candidate"]["MAE_mm"],4)
    out["status"] = "EXPLORATORY_TEMPORAL_TEST_NOT_PRODUCTION_VALIDATED"
    out["warning"] = ("Positive MAE delta only describes this held-out period. "
                      "Check independent rainy seasons/stations, uncertainty and "
                      "rainfall-event skill before recommending a model.")
    return out


def self_test() -> None:
    def make(day: int, rain: bool) -> dict:
        st = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
        x = 5.0 if rain else 0.0
        return {
            "station_id": "SYNTHETIC_PIURA_TEST", "gauge_source": "SYNTHETIC",
            "gauge_observation_id": f"SYNTH_{day}",
            "station_lat": "-5.2", "station_lon": "-80.6",
            "cell_lat_min": "-5.25", "cell_lat_max": "-5.15",
            "cell_lon_min": "-80.65", "cell_lon_max": "-80.55",
            "start_utc": st.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_utc": (st+timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gauge_mm": str(x*2), "imerg_cell_mm": str(x),
            "imerg_granule_ids": f"SYNTH_GRANULE_A_{day};SYNTH_GRANULE_B_{day}",
            "imerg_product_version": "V07-SYNTHETIC",
            "gauge_provenance_url": "https://example.org/SYNTHETIC-NOT-ACTUAL-MEASUREMENT",
        }
    data = [make(i, i%3 != 0) for i in range(90)]
    out = report(data)
    assert out["status"] == "EXPLORATORY_TEMPORAL_TEST_NOT_PRODUCTION_VALIDATED"
    assert out["delta_test_MAE_mm"] > 0
    assert out["candidate"]["factor"] == 2
    try:
        report(data + [data[0]])
        raise AssertionError("duplicate accepted")
    except ValueError as e:
        assert "duplicated" in str(e)
    broken = [dict(data[0], gauge_mm="MISSING")]
    try:
        report(broken)
        raise AssertionError("missing gauge accepted")
    except ValueError as e:
        assert "MISSING" in str(e)
    print("SELF-TEST PASS (synthetic only; ZERO real observation pairs)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("collocated_csv", type=Path, nargs="?")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.collocated_csv:
        p.error("collocated_csv required unless --self-test")
    with args.collocated_csv.open(encoding="utf-8-sig",newline="") as stream:
        data = list(csv.DictReader(stream))
    print(json.dumps(report(data), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
