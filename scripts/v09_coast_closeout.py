#!/usr/bin/env python3
"""IRFEN Tumbes-Tacna: audit and stage an offline, research-only closeout.

This tool reads archived satellite estimates already present in the repository.
It does not download, impute rainfall, issue forecasts, alter the operational
viewer, send notifications, or publish any map. An archive is not a forecast.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.v09_coastal_season_ledger import COAST, store  # noqa: E402

PREFIXES = {
    "TUM": "Tumbes", "PIU": "Piura", "LAM": "Lambayeque",
    "LIB": "La Libertad", "ANC": "Áncash", "LIM": "Lima",
    "CAL": "Callao", "ICA": "Ica", "ARE": "Arequipa",
    "MOQ": "Moquegua", "TAC": "Tacna",
}
HOURS = (1, 3, 6, 12, 24, 72)
THIRTY_MINUTES = timedelta(minutes=30)
MAX_STORED_AGE = timedelta(hours=12)  # Research freshness policy, not provider latency.
EXPECTED_GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "public_alerting": False,
    "notifications_enabled": False,
    "activation_gate": "BLOCKED",
    "map_publishable": False,
}


def parse_time(raw: str) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("timestamp must be a string with explicit UTC offset")
    d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone-free timestamp")
    return d.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj


def guards_are_closed(doc: dict) -> bool:
    return all(doc.get(k) == v for k, v in EXPECTED_GUARDS.items())


def valid_sample(g: dict, index: int, min_coverage: float = 80.0) -> bool:
    rates = g["rate_mm_hr"]
    cover = g["covered_pct"]
    v, pct = rates[index], cover[index]
    return (
        isinstance(v, (float, int)) and not isinstance(v, bool)
        and math.isfinite(v) and v >= 0
        and isinstance(pct, (float, int)) and not isinstance(pct, bool)
        and math.isfinite(pct) and min_coverage <= pct <= 100
    )


def inspect_rain(doc: dict, as_of: datetime) -> dict:
    """Strict half-hour and vector QA. A gap INVALIDATES every ending window crossing it."""
    if not guards_are_closed(doc):
        raise ValueError("rain archive safety guards are not closed")
    targets = doc.get("targets", [])
    granules = doc.get("granules", [])
    if not targets or not granules:
        raise ValueError("no targets or satellite observations")
    ids = [t.get("checkpoint_id") for t in targets]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) for i in ids):
        raise ValueError("duplicate / invalid checkpoint identifiers")
    depts = Counter()
    for cid in ids:
        dep = PREFIXES.get(cid.split("-")[0])
        if dep is None:
            raise ValueError("checkpoint outside coastal scope: " + cid)
        depts[dep] += 1
    times = []
    for g in granules:
        t = parse_time(g["time_utc"])
        if t.minute not in (0, 30) or t.second or t.microsecond:
            raise ValueError("misaligned IMERG half-hour timestamp")
        if t > as_of:
            raise ValueError("future granule")
        if any(not isinstance(g.get(k), list) or len(g[k]) != len(ids)
               for k in ("rate_mm_hr", "covered_pct")):
            raise ValueError("misaligned per-basin data vector")
        for v, cov in zip(g["rate_mm_hr"], g["covered_pct"]):
            if (v is not None and (isinstance(v, bool) or
                    not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0)):
                raise ValueError("negative / nonfinite / nonnumeric rainfall rate")
            if (not isinstance(cov, (int, float)) or isinstance(cov, bool) or
                    not math.isfinite(cov) or not 0 <= cov <= 100):
                raise ValueError("bad spatial coverage")
        times.append(t)
    missing = []
    for prev, nxt in zip(times, times[1:]):
        dt = nxt - prev
        if dt <= timedelta(0) or dt % THIRTY_MINUTES != timedelta(0):
            raise ValueError("out-of-order or off-cadence granule")
        if dt != THIRTY_MINUTES:
            cursor = prev + THIRTY_MINUTES
            while cursor < nxt:
                missing.append(utc_text(cursor))
                cursor += THIRTY_MINUTES
    windows = {}
    for h in HOURS:
        n = h * 2
        tail = granules[-n:]
        tail_times = times[-n:]
        continuous = (
            len(tail) == n and
            all(tail_times[i] - tail_times[i-1] == THIRTY_MINUTES
                for i in range(1, len(tail_times)))
        )
        eligible = sum(
            continuous and all(valid_sample(g, i) for g in tail)
            for i in range(len(ids))
        )
        windows[str(h) + "h"] = {
            "continuous": continuous,
            "eligible_catchments": eligible,
            "unknown_catchments": len(ids) - eligible,
            "status": "OBSERVATION_ONLY" if eligible else "INCOMPLETE_OR_MISSING",
        }
    raw_recency = as_of - (times[-1] + THIRTY_MINUTES)
    newest_age = raw_recency.total_seconds() / 3600
    return {
        "source": "NASA_GPM_3IMERGHHE_OBSERVED_NOT_FORECAST",
        "checkpoints": len(ids), "granules": len(granules),
        "from_utc": utc_text(times[0]), "last_granule_start_utc": utc_text(times[-1]),
        "archive_written_at_utc": doc.get("status", {}).get("written_at_utc"),
        "latest_data_age_hours_at_audit": round(newest_age, 3),
        "fresh_under_12h_research_policy": timedelta(0) <= raw_recency <= MAX_STORED_AGE,
        "missing_halfhours": missing, "n_missing_halfhours": len(missing),
        "windows_ending_at_latest": windows,
        "catchments_by_department": {name: depts[name] for name in COAST},
    }


def inspect_geometry(doc: dict | None) -> dict:
    """Discrepancies are review candidates, never automatic corrections."""
    if doc is None:
        return {"status": "NO_GEOGRAPHY_INPUT", "verified_hydrologically": 0}
    points = doc.get("checkpoints", [])
    if not isinstance(points, list) or not points:
        raise ValueError("geographic inventory empty")
    departments = Counter()
    counts = Counter()
    differences = []
    no_area = []
    for p in points:
        cid = p.get("id")
        if not isinstance(cid, str) or cid.split("-")[0] not in PREFIXES:
            raise ValueError("geographic point out of coastal scope")
        departments[PREFIXES[cid.split("-")[0]]] += 1
        counts[p.get("type")] += 1
        if p.get("type") != "rio":
            continue
        q = p.get("q3_contributing_area") or {}
        if q.get("status") != "APORTACION_DELIMITADA_EXPERIMENTAL":
            no_area.append(cid)
            continue
        ratio = q.get("hydrorivers_ratio")
        if isinstance(ratio, (int, float)) and math.isfinite(ratio):
            if abs(ratio - 1.0) > 0.01:
                differences.append({
                    "checkpoint_id": cid, "hydrorivers_ratio": round(ratio, 5),
                    "area_difference_percent": round(100 * (ratio - 1.0), 2),
                    "status": "REVIEW_REQUIRED_NOT_A_VALIDATION",
                })
    differences.sort(key=lambda p: abs(p["area_difference_percent"]), reverse=True)
    return {
        "status": "GEOGRAPHIC_REVIEW_REQUIRED",
        "points": len(points), "types": dict(counts),
        "points_by_department": {name: departments[name] for name in COAST},
        "areas_different_over_1pct": len(differences),
        "high_priority_differences_over_10pct": [
            x for x in differences if abs(x["area_difference_percent"]) > 10],
        "other_differences": [
            x for x in differences if abs(x["area_difference_percent"]) <= 10],
        "rivers_without_evaluable_catchment": no_area,
        "verified_hydrologically": 0,
        "note": "HydroSHEDS and HydroRIVERS share lineage; agreement does not verify discharge.",
    }


def evaluate_forecasts(rows: list[dict] | None) -> dict:
    """Only score independent, causally timed observed flows; never score rainfall as river events."""
    by_horizon = {}
    for h in (1, 3, 6, 12, 24):
        items = [r for r in (rows or []) if r.get("horizon_hours") == h]
        accepted = []
        rejected = 0
        for r in items:
            try:
                issue = parse_time(r["issue_time"])
                valid = parse_time(r["valid_time"])
                inputs = parse_time(r["last_input_available_at"])
                observed = parse_time(r["observed_at"])
                observed_known = parse_time(r["observed_available_at"])
                values = [r[k] for k in ("actual_flow", "model_flow", "baseline_flow")]
                if (valid - issue != timedelta(hours=h) or inputs > issue or
                        observed != valid or observed_known < valid or
                        r.get("independent_observation") is not True or
                        r.get("qc") != "VERIFIED" or
                        not all(isinstance(x, (float, int)) and not isinstance(x, bool)
                                and math.isfinite(x) and x >= 0 for x in values)):
                    raise ValueError("causality or independent quality")
                accepted.append(values)
            except (KeyError, TypeError, ValueError):
                rejected += 1
        if len(accepted) < 30:
            by_horizon[str(h) + "h"] = {
                "status": "NO_EVALUABLE_INSUFFICIENT_INDEPENDENT_SUBDAILY_TRUTH",
                "accepted_pairs": len(accepted), "rejected_pairs": rejected,
                "predictive_skill_demonstrated": False,
            }
            continue
        mae_model = sum(abs(a - m) for a, m, b in accepted) / len(accepted)
        mae_baseline = sum(abs(a - b) for a, m, b in accepted) / len(accepted)
        by_horizon[str(h) + "h"] = {
            "status": "DESCRIPTIVE_RESEARCH_ONLY_NOT_VALIDATED",
            "accepted_pairs": len(accepted), "rejected_pairs": rejected,
            "mae_model": round(mae_model, 5), "mae_persistence_or_reference": round(mae_baseline, 5),
            "model_beats_reference_on_this_sample": mae_model < mae_baseline,
            "predictive_skill_demonstrated": False,
            "limitations": "No independent event split, event thresholds or false-alarm audit.",
        }
    return by_horizon


def stage_latest_derived_observations(doc: dict, out: Path, as_of: datetime) -> dict:
    """Archive today's ingestion of existing NASA-derived values, never backdate ingestion.

    available_at uses a logged retrieval timestamp as a conservative *latest known*
    bound, NOT an official publication timestamp. These are UNCERTIFIED satellite
    estimates (QC UNVERIFIED), never eligible as hydraulic forecast truth.
    """
    if not guards_are_closed(doc):
        raise ValueError("cannot stage source without research guards")
    last = doc["granules"][-1]
    obs = parse_time(last["time_utc"])
    fetched = last.get("retrieved_at_utc")
    known_available = utc_text(parse_time(fetched)) if fetched else None
    if known_available and parse_time(known_available) > as_of:
        raise ValueError("retrieved_at is after actual ingestion")
    archived = 0
    for i, t in enumerate(doc["targets"]):
        cid = t["checkpoint_id"]
        dept = PREFIXES[cid.split("-")[0]]
        val = last["rate_mm_hr"][i]
        pct = last["covered_pct"][i]
        proper = valid_sample(last, i, min_coverage=0)
        meta = {
            "source": "NASA GPM IMERG Early via previously captured IRFEN archive",
            "product": "IMERG_EARLY", "department": dept,
            "basin": cid, "subbasin": cid,
            "observation_time": utc_text(obs), "available_at": known_available,
            "published_at": None, "unit": "mm/hr",
            "qc": "UNVERIFIED" if proper else "MISSING",
            "coverage": pct / 100 if proper else None,
            "expires_at": utc_text(obs + MAX_STORED_AGE),
            "value": val if proper else None, "forecast": False,
            "hydrology_note": "experimental HydroSHEDS catchment; not a validated river observation",
            "availability_basis": "archived_retrieved_at_utc_not_official_publication",
        }
        subset = {
            "archive_source": doc.get("source"),
            "archive_geometry_sha256": doc.get("geometry_sha256"),
            "granule_id": last.get("granule"),
            "granule_time_utc": last["time_utc"],
            "checkpoint_id": cid, "rate_mm_hr": val, "covered_pct": pct,
            "retrieved_at_utc": fetched,
        }
        source = (json.dumps(subset, sort_keys=True, ensure_ascii=False) + "\n").encode()
        _, created = store(out, meta, source, utc_text(as_of))
        archived += int(created)
    return {
        "derived_snapshots_created": archived,
        "snapshots_possible": len(doc["targets"]),
        "ledger_dir": str(out), "source_kind": "DERIVED_FROM_ARCHIVED_IME RG".replace(" ", ""),
        "prospective_hydrologic_skill_claimed": False,
        "source_raw_hdf5_preserved_by_this_step": False,
        "note": "No synthetic retrieval timestamp or inferred satellite publication time.",
    }


def closeout(archive: dict, geography: dict | None, as_of: datetime,
             forecasts: list[dict] | None = None, ledger_dir: Path | None = None) -> dict:
    rain = inspect_rain(archive, as_of)
    geo = inspect_geometry(geography)
    pred = evaluate_forecasts(forecasts)
    staged = stage_latest_derived_observations(archive, ledger_dir, as_of) if ledger_dir else None
    blockers = [
        "NO_VERIFIED_INDEPENDENT_SUBDAILY_DISCHARGE_OR_RAVINE_EVENT_TRUTH",
        "NO_VALIDATED_LEAD_TIME_OR_FALSE_ALARM_RESULTS",
        "PRIVATE_VIEWER_INTEGRATION_NOT_REVIEWED_AS_SINGLE_DELIVERY",
    ]
    if rain["n_missing_halfhours"]:
        blockers.append("HALF_HOURLY_RAIN_ARCHIVE_HAS_GAPS")
    if not rain["fresh_under_12h_research_policy"]:
        blockers.append("SATELLITE_RAIN_ARCHIVE_STALE")
    if geo.get("areas_different_over_1pct"):
        blockers.append("HYDROLOGIC_CATCHMENT_SECTION_REVIEW_REQUIRED")
    return {
        "schema": "irfen_v091_coastal_closeout_audit_v0_1",
        "audit_as_of_utc": utc_text(as_of),
        "coastal_scope": list(COAST),
        "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
        "activation_gate": "BLOCKED", "operational_alerting_enabled": False,
        "public_alerting": False, "production_ready": False,
        "rain_archived_observations": rain,
        "geography": geo, "prediction_by_horizon": pred,
        "prospective_evidence_staging": staged,
        "blockers": blockers,
        "closure": "RESEARCH_PROTOTYPE_ONLY_PREDICTIVE_CLOSURE_REJECTED",
        "do_not_use_for_public_warnings": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--hydrology", type=Path)
    ap.add_argument("--forecast-evaluation", type=Path)
    ap.add_argument("--ledger-dir", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--as-of", required=True, help="UTC with offset; never backdate ingestion")
    args = ap.parse_args()
    as_of = parse_time(args.as_of)
    forecasts = read_json(args.forecast_evaluation).get("predictions", []) if args.forecast_evaluation else None
    result = closeout(
        read_json(args.archive),
        read_json(args.hydrology) if args.hydrology else None,
        as_of, forecasts, args.ledger_dir,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "closure": result["closure"],
        "targets": result["rain_archived_observations"]["checkpoints"],
        "missing_intervals": result["rain_archived_observations"]["n_missing_halfhours"],
        "predictive_validated": False,
        "blockers": len(result["blockers"]),
        "ledger_created": (result["prospective_evidence_staging"] or {}).get("derived_snapshots_created"),
    }, ensure_ascii=False))
    if result["activation_gate"] != "BLOCKED" or result["public_alerting"]:
        raise SystemExit("CRITICAL: safety gate is open")


if __name__ == "__main__":
    main()
