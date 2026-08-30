#!/usr/bin/env python3
"""Execute the preregistered IBVF meteorological stratification contract.

Input contains only blind A3 daily meteorological features. The script rejects
outcome-like fields, verifies the exhaustive A0 calendar, computes within-track
within-season empirical midrank percentiles, and deterministically selects the
six preregistered strata with the frozen 9-day separation. It does not inspect
sensor availability, territorial evidence, case/control role, risk, or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

FEATURES = ("P3H_MAX", "P24H_LOCAL", "ANTECEDENT_7D")
FORBIDDEN_KEY_FRAGMENTS = (
    "outcome", "event", "activation", "damage", "incident", "case_control",
    "case_role", "control_role", "label", "risk", "alert", "priority",
)


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dates_inclusive(start: str, end: str) -> list[str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    out: list[str] = []
    while a <= b:
        out.append(a.isoformat())
        a += timedelta(days=1)
    return out


def finite_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def midrank_percentiles(values: dict[str, float]) -> dict[str, float]:
    """Empirical average-rank percentile on [0,1]; singleton maps to 0.5."""
    items = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(items)
    if not n:
        return {}
    if n == 1:
        return {items[0][0]: 0.5}
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and items[j][1] == items[i][1]:
            j += 1
        # one-based ranks i+1...j; average rank then map rank 1 -> 0, rank n -> 1.
        avg_rank = ((i + 1) + j) / 2.0
        pct = (avg_rank - 1.0) / (n - 1.0)
        for k in range(i, j):
            out[items[k][0]] = pct
        i = j
    return out


def reject_forbidden_fields(rows: Iterable[dict[str, Any]]) -> None:
    for idx, row in enumerate(rows):
        for key in row:
            low = str(key).lower()
            if any(fragment in low for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError(f"forbidden outcome/risk-like field in A3 input row {idx}: {key}")


def validate_guards(doc: dict[str, Any]) -> None:
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["production_use"] is False and doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["uses_operational_event_none_labels"] is False
    assert doc["territorial_activation_evidence_blinded"] is True


def select_group(rows: list[dict[str, Any]], contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_date = {r["date_local"]: r for r in rows}
    known_dates = [d for d, r in by_date.items() if all(finite_number(r.get(f)) for f in FEATURES)]
    feature_pct: dict[str, dict[str, float]] = {}
    for feature in FEATURES:
        feature_pct[feature] = midrank_percentiles({d: float(by_date[d][feature]) for d in known_dates})

    composites: dict[str, float] = {}
    for d in known_dates:
        composites[d] = sum(feature_pct[f][d] for f in FEATURES) / 3.0
    composite_pct = midrank_percentiles(composites)

    enriched: list[dict[str, Any]] = []
    for d in sorted(by_date):
        r = by_date[d]
        e = {
            "unit_id": r["unit_id"],
            "season_id": r["season_id"],
            "date_local": d,
            "P3H_MAX": r.get("P3H_MAX"),
            "P24H_LOCAL": r.get("P24H_LOCAL"),
            "ANTECEDENT_7D": r.get("ANTECEDENT_7D"),
            "PCT_P3H_MAX": feature_pct["P3H_MAX"].get(d),
            "PCT_P24H_LOCAL": feature_pct["P24H_LOCAL"].get(d),
            "PCT_ANTECEDENT_7D": feature_pct["ANTECEDENT_7D"].get(d),
            "MET_COMPOSITE_SCORE": composites.get(d),
            "MET_COMPOSITE_PERCENTILE": composite_pct.get(d),
            "rank_status": "KNOWN" if d in composites else "UNKNOWN_MISSING_FEATURE_NO_IMPUTATION",
            "selected": False,
            "selected_target_percentile": None,
            "selected_target_order": None,
            "case_control_role": "UNASSIGNED",
        }
        enriched.append(e)

    targets = [float(x) for x in contract["primary_selection"]["target_order"]]
    min_sep = int(contract["primary_selection"]["minimum_anchor_separation_days"])
    selected_dates: list[date] = []
    selected: list[dict[str, Any]] = []
    enriched_by_date = {e["date_local"]: e for e in enriched}
    for order, target in enumerate(targets, start=1):
        candidates: list[tuple[float, str]] = []
        for d, pct in composite_pct.items():
            dd = date.fromisoformat(d)
            if any(abs((dd - s).days) < min_sep for s in selected_dates):
                continue
            candidates.append((abs(float(pct) - target), d))
        if not candidates:
            selected.append({
                "target_percentile": target,
                "target_order": order,
                "status": "STRATUM_UNAVAILABLE_NO_REPLACEMENT_FROM_OTHER_SEASON",
                "date_local": None,
            })
            continue
        _, chosen = min(candidates, key=lambda x: (x[0], x[1]))
        chosen_date = date.fromisoformat(chosen)
        selected_dates.append(chosen_date)
        e = enriched_by_date[chosen]
        e["selected"] = True
        e["selected_target_percentile"] = target
        e["selected_target_order"] = order
        selected.append({
            "target_percentile": target,
            "target_order": order,
            "status": "SELECTED_BLIND_METEOROLOGICAL_STRATUM",
            "date_local": chosen,
            "composite_score": e["MET_COMPOSITE_SCORE"],
            "composite_percentile": e["MET_COMPOSITE_PERCENTILE"],
            "absolute_target_distance": abs(float(e["MET_COMPOSITE_PERCENTILE"]) - target),
            "case_control_role": "UNASSIGNED",
        })
    return enriched, selected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a0-pool", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--a3-daily", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    pool = json.loads(args.a0_pool.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    a3 = json.loads(args.a3_daily.read_text(encoding="utf-8"))
    for d in (pool, contract, a3):
        validate_guards(d)
    assert pool["meteorological_ranking_status"] == "PREREGISTERED_NOT_YET_EXECUTED_NO_WINDOW_SELECTED"
    assert contract["execution_status"] == "PREREGISTERED_NOT_YET_EXECUTED"
    assert contract["inputs_allowed"]["territorial_outcomes"] is False
    assert contract["inputs_allowed"]["known_event_dates"] is False
    assert contract["normalization"]["scope"] == "WITHIN_TRACK_WITHIN_SEASON"
    assert contract["normalization"]["method"] == "EMPIRICAL_MIDRANK_PERCENTILE"
    assert contract["composite_score"]["formula"] == "MEAN(PCT_P3H_MAX,PCT_P24H_LOCAL,PCT_ANTECEDENT_7D)"
    assert contract["primary_selection"]["minimum_anchor_separation_days"] == 9

    rows = a3.get("rows")
    if not isinstance(rows, list):
        raise ValueError("A3 daily input must contain list field 'rows'")
    reject_forbidden_fields(rows)
    allowed_row_keys = {"unit_id", "season_id", "date_local", *FEATURES}
    for i, r in enumerate(rows):
        extras = set(r) - allowed_row_keys
        if extras:
            raise ValueError(f"A3 input row {i} has non-preregistered fields: {sorted(extras)}")

    expected_tracks = list(pool["tracks"])
    seasons = {s["season_id"]: s for s in pool["seasons"]}
    expected: set[tuple[str, str, str]] = set()
    for track in expected_tracks:
        for sid, season in seasons.items():
            days = dates_inclusive(season["start_local"], season["end_local_inclusive"])
            if len(days) != int(season["day_count"]):
                raise ValueError(f"A0 season day_count mismatch {sid}")
            expected.update((track, sid, d) for d in days)
    observed = [(r.get("unit_id"), r.get("season_id"), r.get("date_local")) for r in rows]
    if len(observed) != len(set(observed)):
        raise ValueError("A3 input contains duplicate track-season-date keys")
    observed_set = set(observed)
    if observed_set != expected:
        missing = sorted(expected - observed_set)[:10]
        extra = sorted(observed_set - expected)[:10]
        raise ValueError(f"A3 input is not the exhaustive frozen A0 pool; missing sample={missing}, extra sample={extra}")
    if len(rows) != int(pool["summary"]["track_day_windows"]):
        raise ValueError("A3 row count differs from frozen A0 track_day_windows")

    all_enriched: list[dict[str, Any]] = []
    all_selected: list[dict[str, Any]] = []
    for track in expected_tracks:
        for sid in seasons:
            group = [r for r in rows if r["unit_id"] == track and r["season_id"] == sid]
            enriched, selected = select_group(group, contract)
            all_enriched.extend(enriched)
            all_selected.append({"unit_id": track, "season_id": sid, "strata": selected})

    selected_count = sum(1 for r in all_enriched if r["selected"])
    unknown_count = sum(1 for r in all_enriched if r["rank_status"] != "KNOWN")
    result = {
        "schema_version": "irfen-ibvf-meteorological-ranking-execution-v0.1",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "source_a0_pool_sha256": sha256_file(args.a0_pool),
        "source_ranking_contract_sha256": sha256_file(args.contract),
        "source_a3_daily_sha256": sha256_file(args.a3_daily),
        "input_track_day_count": len(rows),
        "selected_primary_window_count": selected_count,
        "maximum_primary_windows": int(contract["primary_selection"]["maximum_primary_windows"]),
        "rank_unknown_window_count": unknown_count,
        "sensor_fields_read": False,
        "territorial_outcome_fields_read": False,
        "case_control_assignment_performed": False,
        "all_selected_roles": "UNASSIGNED_BLIND_METEOROLOGICAL_STRATUM",
        "groups": all_selected,
        "rows": all_enriched,
        "rows_canonical_sha256": canonical_sha(all_enriched),
        "selection_canonical_sha256": canonical_sha(all_selected),
        "status": "BLIND_METEOROLOGICAL_RANKING_EXECUTED_NO_OUTCOME_NO_CASE_CONTROL",
        "next_gate": "FREEZE_A1_A4_REMOTE_FEATURES_FOR_SELECTED_WINDOWS_WITHOUT_REPLACING_MISSING_SENSOR_WINDOWS"
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "track_day_count": len(rows),
        "selected_count": selected_count,
        "unknown_count": unknown_count,
        "selection_sha256": result["selection_canonical_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
