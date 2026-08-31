#!/usr/bin/env python3
"""Freeze deterministic, outcome-blind execution partitions for PRIMARY6 Sentinel-1.

RESEARCH_ONLY / TEST_ONLY.

This is a computational scheduling layer only. It consumes the already-frozen
PRIMARY6 Sentinel-1 bulk execution manifest and assigns all 108 selected windows
to exactly 18 immutable shards defined ONLY by (unit_id, season_id): three
tracks x six chronological PRIMARY6 seasons. Compatible pairs remain eligible
for R1-R4 execution; the four MISSING_COMPATIBLE_PAIR windows remain explicit
inside their original shards and are never replaced or imputed.

Partition membership does not use rainfall magnitudes, SAR response values,
selected percentile/rank, known event dates, territorial outcomes, or
case/control roles. Within a shard, records are ordered by date only to provide
stable execution identity. The ordering carries no scientific priority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACKS = ("huaycoloro", "shingolay", "san_ildefonso")
SEASONS = (
    "2014-2015",
    "2015-2016",
    "2016-2017",
    "2017-2018",
    "2018-2019",
    "2019-2020",
)
FROZEN_SOURCE_EXECUTION_IDENTITY = "57f4bfa801b599b400ec155ca6f26abffc05a1b2303a1c052e65c94ae2543c86"
COMPATIBLE = "COMPATIBLE_PAIR_FROZEN_PENDING_R1_R4"
MISSING = "MISSING_COMPATIBLE_PAIR_RETAIN_WINDOW_NO_REPLACEMENT_NO_IMPUTATION"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(raw)


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True


def execution_identity(w: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": w["unit_id"],
        "season_id": w["season_id"],
        "date_local": w["date_local"],
        "sar_execution_status": w["sar_execution_status"],
        "pre_item_id": w.get("pre_item_id"),
        "post_item_id": w.get("post_item_id"),
        "projection": w["projection"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    raw = args.manifest.read_bytes()
    src = json.loads(raw)
    guards(src)

    if src.get("cohort_id") != "PRIMARY6_CHRONOLOGICAL":
        raise ValueError("Only PRIMARY6_CHRONOLOGICAL is allowed")
    if src.get("execution_identity_sha256") != FROZEN_SOURCE_EXECUTION_IDENTITY:
        raise ValueError(
            "Frozen PRIMARY6 Sentinel-1 execution identity changed: "
            f"expected {FROZEN_SOURCE_EXECUTION_IDENTITY}, got {src.get('execution_identity_sha256')}"
        )
    if src.get("selected_window_count") != 108:
        raise ValueError("Expected exactly 108 frozen selected windows")
    if src.get("compatible_pair_count") != 104 or src.get("missing_compatible_pair_count") != 4:
        raise ValueError("Expected exactly 104 compatible pairs + 4 explicit missing windows")
    if src.get("selected_window_replacement_allowed") is not False:
        raise ValueError("Selected-window replacement must remain forbidden")
    if src.get("compatible_pair_reselection_allowed") is not False:
        raise ValueError("Compatible-pair reselection must remain forbidden")
    if src.get("missing_pair_imputation_allowed") is not False:
        raise ValueError("Missing-pair imputation must remain forbidden")
    if src.get("case_control_assignment_performed") is not False:
        raise ValueError("Case/control assignment must remain absent")
    if src.get("territorial_outcomes_read") is not False or src.get("known_event_dates_read") is not False:
        raise ValueError("Territorial outcome/event-date leakage detected")

    windows = src.get("windows") or []
    if len(windows) != 108:
        raise ValueError(f"Expected 108 window records, got {len(windows)}")

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    selected_seen: set[tuple[str, str, str]] = set()
    compatible_seen: set[tuple[str, str]] = set()
    status_counter = Counter()
    track_compatible = Counter()
    track_missing = Counter()

    for w in windows:
        unit = w.get("unit_id")
        season = w.get("season_id")
        date_local = w.get("date_local")
        status = w.get("sar_execution_status")
        if unit not in TRACKS:
            raise ValueError(f"Unexpected track: {unit!r}")
        if season not in SEASONS:
            raise ValueError(f"Unexpected PRIMARY6 season: {season!r}")
        if not isinstance(date_local, str) or not date_local:
            raise ValueError("Every selected window must retain date_local")
        if w.get("case_control_role") != "UNASSIGNED":
            raise ValueError("Case/control role must remain UNASSIGNED")
        if status not in (COMPATIBLE, MISSING):
            raise ValueError(f"Unexpected SAR execution status: {status!r}")

        selected_key = (unit, season, date_local)
        if selected_key in selected_seen:
            raise ValueError(f"Duplicate selected-window identity: {selected_key}")
        selected_seen.add(selected_key)

        if status == COMPATIBLE:
            pre, post = w.get("pre_item_id"), w.get("post_item_id")
            if not isinstance(pre, str) or not pre or not isinstance(post, str) or not post:
                raise ValueError(f"Compatible window lacks immutable pair IDs: {selected_key}")
            pair_key = (pre, post)
            if pair_key in compatible_seen:
                raise ValueError(f"Duplicate frozen compatible pair: {pair_key}")
            compatible_seen.add(pair_key)
            track_compatible[unit] += 1
        else:
            if w.get("pre_item_id") is not None or w.get("post_item_id") is not None:
                raise ValueError(f"Missing window unexpectedly has pair IDs: {selected_key}")
            track_missing[unit] += 1

        status_counter[status] += 1
        buckets[(unit, season)].append(w)

    if set(buckets) != {(u, s) for u in TRACKS for s in SEASONS}:
        raise ValueError("Expected exactly all 18 track x season shards")
    if len(selected_seen) != 108 or len(compatible_seen) != 104:
        raise ValueError("Coverage mismatch before partition freeze")
    if status_counter[COMPATIBLE] != 104 or status_counter[MISSING] != 4:
        raise ValueError("Frozen compatible/missing counts changed")
    expected_track = src.get("track_compatible_pair_counts") or {}
    if {u: track_compatible[u] for u in TRACKS} != {u: int(expected_track[u]) for u in TRACKS}:
        raise ValueError("Per-track compatible counts changed")

    shards: list[dict[str, Any]] = []
    compatible_ids_across_shards: list[str] = []
    selected_ids_across_shards: list[str] = []

    for unit in TRACKS:
        for season in SEASONS:
            rows = sorted(buckets[(unit, season)], key=lambda w: (w["date_local"], str(w.get("pre_item_id") or ""), str(w.get("post_item_id") or "")))
            if len(rows) != 6:
                raise ValueError(f"Expected six frozen selected windows in {unit}/{season}, got {len(rows)}")

            records: list[dict[str, Any]] = []
            compatible_count = 0
            missing_count = 0
            for w in rows:
                ident = execution_identity(w)
                window_sha = canonical_sha(ident)
                record = {
                    **ident,
                    "window_execution_identity_sha256": window_sha,
                    "case_control_role": "UNASSIGNED",
                }
                records.append(record)
                selected_ids_across_shards.append(window_sha)
                if w["sar_execution_status"] == COMPATIBLE:
                    compatible_count += 1
                    compatible_ids_across_shards.append(window_sha)
                else:
                    missing_count += 1

            shard_id = f"{unit}__{season.replace('-', '_')}"
            shard_identity_payload = {
                "shard_id": shard_id,
                "unit_id": unit,
                "season_id": season,
                "assignment_fields": ["unit_id", "season_id"],
                "records": records,
            }
            shards.append({
                "shard_id": shard_id,
                "unit_id": unit,
                "season_id": season,
                "projection": rows[0]["projection"],
                "selected_window_count": len(rows),
                "compatible_pair_count": compatible_count,
                "missing_compatible_pair_count": missing_count,
                "execution_order": "DATE_LOCAL_ASCENDING_FOR_STABLE_COMPUTE_ONLY_NO_SCIENTIFIC_PRIORITY",
                "partition_assignment_fields": ["unit_id", "season_id"],
                "partition_uses_selected_rank_or_percentile": False,
                "partition_uses_rainfall_magnitude": False,
                "partition_uses_sar_response": False,
                "partition_uses_outcome_or_event_date": False,
                "shard_identity_sha256": canonical_sha(shard_identity_payload),
                "windows": records,
            })

    if len(shards) != 18:
        raise ValueError(f"Expected 18 shards, got {len(shards)}")
    if len(selected_ids_across_shards) != 108 or len(set(selected_ids_across_shards)) != 108:
        raise ValueError("Every selected window must appear exactly once across shards")
    if len(compatible_ids_across_shards) != 104 or len(set(compatible_ids_across_shards)) != 104:
        raise ValueError("Every compatible pair window must appear exactly once across shards")

    partition_identity_payload = [{
        "shard_id": s["shard_id"],
        "shard_identity_sha256": s["shard_identity_sha256"],
        "selected_window_count": s["selected_window_count"],
        "compatible_pair_count": s["compatible_pair_count"],
        "missing_compatible_pair_count": s["missing_compatible_pair_count"],
    } for s in shards]

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-execution-partition-v0.1",
        "generated_at": now(),
        "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "cohort_id": "PRIMARY6_CHRONOLOGICAL",
        "purpose": "Freeze purely computational track-by-season R1-R4 execution shards without changing scientific selection, pair identity, missingness, or blind state.",
        "source_manifest": str(args.manifest),
        "source_manifest_sha256": sha256_bytes(raw),
        "source_execution_identity_sha256": src["execution_identity_sha256"],
        "source_selected_window_identity_sha256": src.get("source_selected_window_identity_sha256"),
        "partition_rule": "EXACT_TRACK_X_PRIMARY6_SEASON",
        "partition_assignment_fields": ["unit_id", "season_id"],
        "partition_assignment_uses_scientific_magnitude": False,
        "partition_assignment_uses_selected_rank_or_percentile": False,
        "partition_assignment_uses_sensor_response": False,
        "partition_assignment_uses_known_event_dates": False,
        "partition_assignment_uses_territorial_outcomes": False,
        "partition_assignment_uses_case_control_role": False,
        "partition_count": len(shards),
        "track_count": len(TRACKS),
        "season_count": len(SEASONS),
        "seasons": list(SEASONS),
        "selected_window_count": 108,
        "compatible_pair_count": 104,
        "missing_compatible_pair_count": 4,
        "all_selected_windows_covered_exactly_once": True,
        "all_compatible_pair_windows_covered_exactly_once": True,
        "missing_windows_preserved_in_original_shards": True,
        "selected_window_replacement_allowed": False,
        "compatible_pair_reselection_allowed": False,
        "missing_pair_imputation_allowed": False,
        "science_pixels_read": False,
        "rainfall_values_read": False,
        "sar_change_values_read": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_assignment_performed": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "track_compatible_pair_counts": {u: track_compatible[u] for u in TRACKS},
        "track_missing_pair_counts": {u: track_missing[u] for u in TRACKS},
        "partition_identity_sha256": canonical_sha(partition_identity_payload),
        "shards": shards,
        "status": "PASS_18_TRACK_SEASON_SHARDS_108_WINDOWS_104_COMPATIBLE_4_MISSING_EXACT_COVERAGE_NO_OUTCOME",
    }
    guards(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "partition_count": report["partition_count"],
        "selected_window_count": report["selected_window_count"],
        "compatible_pair_count": report["compatible_pair_count"],
        "missing_compatible_pair_count": report["missing_compatible_pair_count"],
        "track_compatible_pair_counts": report["track_compatible_pair_counts"],
        "track_missing_pair_counts": report["track_missing_pair_counts"],
        "partition_identity_sha256": report["partition_identity_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
