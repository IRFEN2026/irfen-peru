#!/usr/bin/env python3
"""Fail-closed forecast/reference pairing for the Sep-2026 north-Peru rain episode.

Additive Phase-2 research utility. It does not read site/data/latest.json, does not
infer GEOS issue time from IRFEN generated_at, and cannot create activation,
hydraulic, threshold, risk or alert outputs.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
PERU = timezone(timedelta(hours=-5))
CONTRACT = ROOT / "config/phase2_north_rainfall_episode_20260923_v0_1.json"
FORECAST = ROOT / "site/data/validation/north_rainfall_20260923_geos_frozen.json"
OBS = ROOT / "site/data/validation/north_rainfall_20260923_observations.json"
OUT = ROOT / "site/data/validation/north_rainfall_20260923_forecast_reference.json"

GUARDS = {
    "research_mode": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}
REF_KINDS = {"SENAMHI_STATION", "IMERG_EARLY", "IMERG_LATE", "GOES_RRQPE"}
GEOS_DURATIONS = {1.0, 3.0, 6.0, 12.0, 24.0}
OBS_DURATIONS = {0.5, 1.0, 3.0, 6.0, 12.0, 24.0, 72.0}
BOUND_BASIS = {"EXPLICIT_DATASET_BOUNDS", "DOCUMENTED_PRODUCT_SPECIFICATION"}


class ValidationError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def record_sha256(row: dict[str, Any]) -> str:
    return canonical_sha256({k: v for k, v in row.items() if k != "record_sha256"})


def dt(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} missing")
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} invalid: {value}") from exc
    if out.tzinfo is None:
        raise ValidationError(f"{field} must include timezone")
    return out.astimezone(UTC)


def require_guards(obj: dict[str, Any], label: str) -> None:
    for key, expected in GUARDS.items():
        if obj.get(key) != expected:
            raise ValidationError(f"{label}: {key} must be {expected!r}")


def reject_demo(obj: dict[str, Any], path: str) -> None:
    normalized = path.replace("\\", "/").lower()
    if normalized.endswith("site/data/latest.json"):
        raise ValidationError("site/data/latest.json is DEMO/mutable and prohibited")
    markers = json.dumps(obj, ensure_ascii=False).upper()
    if "DEMO" in markers or "STATIC_FALLBACK" in markers:
        raise ValidationError("DEMO/static fallback cannot become scientific evidence")


def validate_contract(obj: dict[str, Any]) -> None:
    require_guards(obj, "contract")
    if obj.get("episode_id") != "north_peru_20260923_20260925":
        raise ValidationError("unexpected episode")
    if (obj.get("forecast_rules") or {}).get("generated_at_is_model_issue_time") is not False:
        raise ValidationError("generated_at cannot be model issue time")
    if (obj.get("forecast_rules") or {}).get("mutable_latest_is_historical_archive") is not False:
        raise ValidationError("mutable latest cannot be historical archive")
    if (obj.get("accumulation_rules") or {}).get("geos_30_min_comparison_allowed") is not False:
        raise ValidationError("GEOS 30-minute comparison prohibited")
    if (obj.get("pairing_rules") or {}).get("percent_error_denominator_min_observed_mm") != 0.1:
        raise ValidationError("percent-error denominator rule changed")


def validate_hashes(row: dict[str, Any], label: str) -> None:
    rh = row.get("record_sha256")
    ph = row.get("payload_sha256")
    if not isinstance(rh, str) or len(rh) != 64 or rh != record_sha256(row):
        raise ValidationError(f"{label}: invalid record_sha256")
    if not isinstance(ph, str) or len(ph) != 64:
        raise ValidationError(f"{label}: payload_sha256 required")
    try:
        int(ph, 16)
    except ValueError as exc:
        raise ValidationError(f"{label}: payload_sha256 not hexadecimal") from exc


def validate_common(row: dict[str, Any], label: str) -> tuple[datetime, datetime, float]:
    validate_hashes(row, label)
    start = dt(row.get("valid_start_utc"), label + ".valid_start_utc")
    end = dt(row.get("valid_end_utc"), label + ".valid_end_utc")
    if end <= start:
        raise ValidationError(f"{label}: invalid time bounds")
    duration = float(row.get("duration_hours"))
    if abs((end - start).total_seconds() / 3600.0 - duration) > 1e-6:
        raise ValidationError(f"{label}: duration does not match bounds")
    if row.get("units") != "mm":
        raise ValidationError(f"{label}: only accumulated mm is admissible")
    if row.get("accumulation_mm") is None or float(row["accumulation_mm"]) < 0:
        raise ValidationError(f"{label}: invalid accumulation")
    if row.get("temporal_coverage_complete") is not True:
        raise ValidationError(f"{label}: incomplete window")
    if row.get("time_bounds_basis") not in BOUND_BASIS:
        raise ValidationError(f"{label}: unsupported time-bound semantics")
    dt(row.get("retrieved_at_utc"), label + ".retrieved_at_utc")
    support = row.get("spatial_support")
    if not isinstance(support, dict):
        raise ValidationError(f"{label}: spatial_support required")
    for key in ("support_id", "support_kind", "comparison_support_id", "sampling_method", "comparison_basis"):
        if not support.get(key):
            raise ValidationError(f"{label}: spatial_support.{key} required")
    if support.get("interpolation_to_finer_resolution") is True:
        raise ValidationError(f"{label}: false spatial precision prohibited")
    return start, end, duration


def validate_forecasts(ledger: dict[str, Any], path: str) -> list[dict[str, Any]]:
    reject_demo(ledger, path)
    require_guards(ledger, "forecast ledger")
    if ledger.get("retention_mode") != "APPEND_ONLY":
        raise ValidationError("forecast ledger must be APPEND_ONLY")
    ids: set[str] = set()
    cycles: dict[tuple[Any, ...], str] = {}
    accepted = []
    for index, row in enumerate(ledger.get("records") or []):
        label = f"forecast[{index}]"
        if row.get("source_kind") != "NASA_GEOS_CF_V2_TPREC":
            raise ValidationError(f"{label}: wrong source")
        if not row.get("record_id") or row["record_id"] in ids:
            raise ValidationError(f"{label}: duplicate/missing record_id")
        ids.add(row["record_id"])
        start, end, duration = validate_common(row, label)
        if duration not in GEOS_DURATIONS:
            raise ValidationError(f"{label}: unsupported GEOS duration")
        if not all(row.get(k) for k in ("model", "model_version", "cycle_id")):
            raise ValidationError(f"{label}: model/version/cycle required")
        if row.get("issue_time_verified") is True:
            dt(row.get("issue_time_utc"), label + ".issue_time_utc")
        elif row.get("issue_time_utc") is not None:
            raise ValidationError(f"{label}: unverified issue time must be null")
        support = row["spatial_support"]
        key = (
            row["model"], row["model_version"], row["cycle_id"], start, end,
            duration, support["comparison_support_id"],
        )
        prior = cycles.get(key)
        if prior is not None and prior != row["record_sha256"]:
            raise ValidationError(f"{label}: conflicting same-cycle requery")
        if prior is None:
            cycles[key] = row["record_sha256"]
            accepted.append(row)
    return accepted


def validate_observations(ledger: dict[str, Any], path: str) -> list[dict[str, Any]]:
    reject_demo(ledger, path)
    require_guards(ledger, "observation ledger")
    if ledger.get("retention_mode") != "APPEND_ONLY":
        raise ValidationError("observation ledger must be APPEND_ONLY")
    ids: set[str] = set()
    revisions: set[tuple[Any, ...]] = set()
    accepted = []
    for index, row in enumerate(ledger.get("records") or []):
        label = f"observation[{index}]"
        if row.get("source_kind") not in REF_KINDS:
            raise ValidationError(f"{label}: unsupported reference source")
        if not row.get("record_id") or row["record_id"] in ids:
            raise ValidationError(f"{label}: duplicate/missing record_id")
        ids.add(row["record_id"])
        start, end, duration = validate_common(row, label)
        if duration not in OBS_DURATIONS:
            raise ValidationError(f"{label}: unsupported observation duration")
        if not row.get("revision_id"):
            raise ValidationError(f"{label}: revision_id required")
        support = row["spatial_support"]
        key = (
            row["source_kind"], row.get("product_version"), support["comparison_support_id"],
            start, end, duration, row["revision_id"],
        )
        if key in revisions:
            raise ValidationError(f"{label}: duplicate revision")
        revisions.add(key)
        if row["source_kind"] == "SENAMHI_STATION":
            if support["support_kind"] != "POINT_STATION" or row.get("station_is_basin_truth") is not False:
                raise ValidationError(f"{label}: station must remain point reference, not basin truth")
        accepted.append(row)
    return accepted


def anticipation(row: dict[str, Any], start: datetime) -> tuple[str, float | None]:
    if row.get("issue_time_verified") is not True:
        return "ISSUE_TIME_UNVERIFIED", None
    lead = (start - dt(row["issue_time_utc"], "issue_time_utc")).total_seconds() / 3600.0
    return ("PROSPECTIVE" if lead >= 0 else "ISSUED_AFTER_WINDOW_START"), lead


def lead_bucket(status: str, hours: float | None) -> str:
    if status != "PROSPECTIVE" or hours is None:
        return status
    for limit, name in ((6, "LT_6H"), (12, "6_TO_LT_12H"), (24, "12_TO_LT_24H"), (48, "24_TO_LT_48H")):
        if hours < limit:
            return name
    return "GE_48H"


def pairing_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["valid_start_utc"], row["valid_end_utc"], float(row["duration_hours"]),
        row["spatial_support"]["comparison_support_id"],
    )


def build_pairs(forecasts: list[dict[str, Any]], observations: list[dict[str, Any]], episode_id: str, pct_min: float) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_key[pairing_key(row)].append(row)
    pairs = []
    for forecast in forecasts:
        start = dt(forecast["valid_start_utc"], "forecast.valid_start_utc")
        end = dt(forecast["valid_end_utc"], "forecast.valid_end_utc")
        fs = forecast["spatial_support"]
        for obs in by_key.get(pairing_key(forecast), []):
            os = obs["spatial_support"]
            if fs["comparison_basis"] != os["comparison_basis"]:
                raise ValidationError("paired supports disagree on comparison_basis")
            fmm, omm = float(forecast["accumulation_mm"]), float(obs["accumulation_mm"])
            error = fmm - omm
            status, lead = anticipation(forecast, start)
            published = obs.get("published_at_utc")
            latency = None if not published else (dt(published, "published_at_utc") - end).total_seconds() / 3600.0
            row = {
                "episode_id": episode_id,
                "forecast_record_id": forecast["record_id"],
                "reference_record_id": obs["record_id"],
                "reference_revision_id": obs["revision_id"],
                "reference_source_kind": obs["source_kind"],
                "model": forecast["model"],
                "model_version": forecast["model_version"],
                "cycle_id": forecast["cycle_id"],
                "issue_time_utc": forecast.get("issue_time_utc"),
                "issue_time_verified": forecast.get("issue_time_verified") is True,
                "anticipation_status": status,
                "lead_to_window_start_hours": None if lead is None else round(lead, 3),
                "lead_bucket": lead_bucket(status, lead),
                "valid_start_utc": start.isoformat().replace("+00:00", "Z"),
                "valid_end_utc": end.isoformat().replace("+00:00", "Z"),
                "valid_start_peru": start.astimezone(PERU).isoformat(),
                "valid_end_peru": end.astimezone(PERU).isoformat(),
                "duration_hours": float(forecast["duration_hours"]),
                "comparison_support_id": fs["comparison_support_id"],
                "spatial_comparison_basis": fs["comparison_basis"],
                "forecast_support_kind": fs["support_kind"],
                "reference_support_kind": os["support_kind"],
                "forecast_mm": round(fmm, 6),
                "observed_mm": round(omm, 6),
                "error_forecast_minus_observed_mm": round(error, 6),
                "absolute_error_mm": round(abs(error), 6),
                "percent_error": None if omm < pct_min else round(100.0 * error / omm, 6),
                "percent_error_denominator_min_mm": pct_min,
                "observation_publication_latency_hours": None if latency is None else round(latency, 3),
                "forecast_payload_sha256": forecast["payload_sha256"],
                "reference_payload_sha256": obs["payload_sha256"],
                "comparison_semantics": "POINT_STATION_REFERENCE_WITH_REPRESENTATIVENESS_LIMITATION" if obs["source_kind"] == "SENAMHI_STATION" else "PRODUCT_DISCREPANCY_NOT_GROUND_TRUTH",
            }
            row["pair_sha256"] = canonical_sha256(row)
            pairs.append(row)
    return sorted(pairs, key=lambda r: (r["valid_start_utc"], r["comparison_support_id"], r["reference_source_kind"], r["reference_revision_id"]))


def metrics(pairs: list[dict[str, Any]], prospective_only: bool) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        if prospective_only and row["anticipation_status"] != "PROSPECTIVE":
            continue
        key = (row["comparison_support_id"], row["reference_source_kind"], row["duration_hours"], row["lead_bucket"], row["model_version"])
        groups[key].append(row)
    out = []
    for key, rows in sorted(groups.items(), key=lambda x: tuple(map(str, x[0]))):
        errors = [float(r["error_forecast_minus_observed_mm"]) for r in rows]
        n = len(errors)
        intervals = sorted((dt(r["valid_start_utc"], "start"), dt(r["valid_end_utc"], "end")) for r in rows)
        overlaps = sum(1 for i, (s, e) in enumerate(intervals) for ps, pe in intervals[:i] if s < pe and ps < e)
        out.append({
            "unit_or_support_id": key[0],
            "reference_source_kind": key[1],
            "duration_hours": key[2],
            "lead_bucket": key[3],
            "model_version": key[4],
            "n_periods": n,
            "n_unique_episodes": len({r["episode_id"] for r in rows}),
            "bias_mm": round(sum(errors) / n, 6),
            "mae_mm": round(sum(abs(v) for v in errors) / n, 6),
            "rmse_mm": round(math.sqrt(sum(v * v for v in errors) / n), 6),
            "overlapping_window_pair_count": overlaps,
            "interpretation_guard": "Overlapping windows are not independent; dry-zero hits do not prove skill for extremes."
        })
    return out


def build_output(contract: dict[str, Any], forecast_ledger: dict[str, Any], obs_ledger: dict[str, Any], forecast_path: str, obs_path: str) -> dict[str, Any]:
    validate_contract(contract)
    forecasts = validate_forecasts(forecast_ledger, forecast_path)
    observations = validate_observations(obs_ledger, obs_path)
    pct_min = float(contract["pairing_rules"]["percent_error_denominator_min_observed_mm"])
    pairs = build_pairs(forecasts, observations, contract["episode_id"], pct_min)
    return {
        "schema_version": "north-forecast-reference-experimental-v0.1",
        "episode_id": contract["episode_id"],
        **GUARDS,
        "contract_sha256": canonical_sha256(contract),
        "forecast_ledger_sha256": canonical_sha256(forecast_ledger),
        "observation_ledger_sha256": canonical_sha256(obs_ledger),
        "pair_count": len(pairs),
        "prospective_pair_count": sum(r["anticipation_status"] == "PROSPECTIVE" for r in pairs),
        "pairs": pairs,
        "metrics_all_discrepancies": metrics(pairs, False),
        "metrics_prospective_only": metrics(pairs, True),
        "interpretation": {
            "satellite_reference_is_ground_truth": False,
            "station_reference_is_basin_truth": False,
            "rainfall_confirms_activation": False,
            "forecast_skill_implies_activation_skill": False,
            "automatic_calibration_allowed": False
        }
    }


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--forecast-ledger", type=Path, default=FORECAST)
    parser.add_argument("--observation-ledger", type=Path, default=OBS)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = build_output(load(args.contract), load(args.forecast_ledger), load(args.observation_ledger), str(args.forecast_ledger), str(args.observation_ledger))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pair_count": result["pair_count"], "prospective_pair_count": result["prospective_pair_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
