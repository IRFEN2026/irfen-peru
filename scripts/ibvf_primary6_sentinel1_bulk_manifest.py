#!/usr/bin/env python3
"""Freeze the deterministic PRIMARY6 Sentinel-1 bulk execution manifest.

RESEARCH_ONLY / TEST_ONLY. This script consumes only the already-frozen blind
PRIMARY6 selected-window A1 catalog and pre-outcome Sentinel-1 contracts. It
never reselects a scientific window or compatible pair, never reads rainfall
magnitudes, SAR response values, territorial outcomes, known event dates, or
case/control roles, and never substitutes the four windows with no compatible
pair.

The output is an identity/provenance manifest for the 104 compatible pairs plus
four explicit MISSING_COMPATIBLE_PAIR windows. It contains no science pixels and
performs no R1-R4 processing or activation inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACKS = ("huaycoloro", "shingolay", "san_ildefonso")


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


def pair_ids(pair: dict[str, Any]) -> tuple[str, str]:
    def one(prefix: str) -> str | None:
        for key in (f"{prefix}_id", f"{prefix}_item_id", f"{prefix}_scene_id"):
            v = pair.get(key)
            if isinstance(v, str) and v:
                return v
        v = pair.get(prefix)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            for key in ("id", "item_id", "scene_id"):
                x = v.get(key)
                if isinstance(x, str) and x:
                    return x
        for key in (f"{prefix}_item", f"{prefix}_scene"):
            v = pair.get(key)
            if isinstance(v, dict):
                x = v.get("id") or v.get("item_id")
                if isinstance(x, str) and x:
                    return x
        return None

    pre, post = one("pre"), one("post")
    if not pre or not post:
        raise ValueError(f"Cannot resolve pre/post IDs from selected_pair keys={sorted(pair.keys())}")
    return pre, post


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--a4-contract", type=Path, required=True)
    ap.add_argument("--reconciliation", type=Path, required=True)
    ap.add_argument("--projection-amendment", type=Path, required=True)
    ap.add_argument("--graph-audit", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    catalog_raw = args.catalog.read_bytes()
    a4_raw = args.a4_contract.read_bytes()
    reconciliation_raw = args.reconciliation.read_bytes()
    projection_raw = args.projection_amendment.read_bytes()
    graph_audit_raw = args.graph_audit.read_bytes()

    catalog = json.loads(catalog_raw)
    a4 = json.loads(a4_raw)
    reconciliation = json.loads(reconciliation_raw)
    projection = json.loads(projection_raw)
    graph_audit = json.loads(graph_audit_raw)
    for d in (catalog, a4, reconciliation, projection, graph_audit):
        guards(d)

    assert catalog["cohort_id"] == "PRIMARY6_CHRONOLOGICAL"
    assert catalog["case_control_assignment_performed"] is False
    assert catalog["territorial_outcome_fields_read"] is False
    assert catalog["known_event_dates_read"] is False
    assert catalog["selected_windows_replaced_for_sensor_availability"] is False
    assert a4["selected_window_count"] == 108
    assert a4["compatible_pair_count"] == 104
    assert a4["missing_compatible_pair_count"] == 4
    assert a4["unknown_pair_count"] == 0
    assert a4["replacement_of_selected_window_for_sar_availability"] is False
    assert reconciliation["execution_gate"]["parallel_sentinel1_r2_r4_allowed_after_reconciliation"] is True
    assert reconciliation["execution_gate"]["compatible_pair_window_count"] == 104
    assert reconciliation["execution_gate"]["missing_pair_window_count"] == 4
    assert reconciliation["required_processing_identity"]["compatible_pair_reselection_allowed"] is False
    assert reconciliation["required_processing_identity"]["selected_window_replacement_allowed"] is False
    assert projection["resolution"]["per_window_projection_tuning_allowed"] is False
    assert projection["resolution"]["per_window_parameter_tuning_allowed"] is False
    assert projection["resolution"]["outcome_aware_parameter_tuning_allowed"] is False
    assert set(projection["resolution"]["track_projection"]) == set(TRACKS)
    assert graph_audit["status"] == "PASS_ONLY_ID_AND_CRS_DIFFER"
    assert graph_audit["normalized_graphs_identical"] is True
    assert graph_audit["science_pixels_read"] is False

    windows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    compatible = 0
    missing = 0
    per_track = Counter()
    per_track_compatible = Counter()
    per_track_missing = Counter()

    for w in catalog.get("windows", []):
        unit = w.get("unit_id")
        if unit not in TRACKS:
            raise ValueError(f"Unexpected selected PRIMARY6 unit in Sentinel-1 A4 catalog: {unit!r}")
        if w.get("case_control_role") != "UNASSIGNED":
            raise ValueError("Case/control role must remain UNASSIGNED before unblind")
        identity = (
            unit,
            w.get("season_id"),
            w.get("date_local"),
            w.get("selected_target_order"),
            w.get("selected_target_percentile"),
        )
        if identity in seen:
            raise ValueError(f"Duplicate selected-window identity: {identity}")
        seen.add(identity)
        per_track[unit] += 1

        s1 = w.get("sentinel1") or {}
        pair = s1.get("selected_pair")
        rec: dict[str, Any] = {
            "unit_id": unit,
            "season_id": w.get("season_id"),
            "date_local": w.get("date_local"),
            "selected_target_order": w.get("selected_target_order"),
            "selected_target_percentile": w.get("selected_target_percentile"),
            "case_control_role": "UNASSIGNED",
            "projection": projection["resolution"]["track_projection"][unit],
            "source_sentinel1_catalog_status": s1.get("status"),
        }
        if isinstance(pair, dict):
            pre_id, post_id = pair_ids(pair)
            rec.update({
                "sar_execution_status": "COMPATIBLE_PAIR_FROZEN_PENDING_R1_R4",
                "pre_item_id": pre_id,
                "post_item_id": post_id,
                "pair_identity": {
                    "platform": pair.get("platform"),
                    "instrument_mode": pair.get("instrument_mode"),
                    "orbit_state": pair.get("orbit_state"),
                    "relative_orbit": pair.get("relative_orbit"),
                },
            })
            compatible += 1
            per_track_compatible[unit] += 1
        else:
            status = str(s1.get("status") or "")
            if "MISSING_COMPATIBLE" not in status:
                raise ValueError(f"Selected window lacks pair without frozen missing semantics: {identity} status={status}")
            rec.update({
                "sar_execution_status": "MISSING_COMPATIBLE_PAIR_RETAIN_WINDOW_NO_REPLACEMENT_NO_IMPUTATION",
                "pre_item_id": None,
                "post_item_id": None,
                "pair_identity": None,
            })
            missing += 1
            per_track_missing[unit] += 1
        windows.append(rec)

    windows.sort(key=lambda x: (
        TRACKS.index(x["unit_id"]),
        str(x["season_id"]),
        str(x["date_local"]),
        int(x["selected_target_order"]),
    ))

    if len(windows) != 108:
        raise ValueError(f"Expected exactly 108 selected PRIMARY6 windows, got {len(windows)}")
    if compatible != 104 or missing != 4:
        raise ValueError(f"Expected 104 compatible + 4 missing, got {compatible} + {missing}")
    if set(per_track) != set(TRACKS):
        raise ValueError(f"Expected all three frozen tracks, got {sorted(per_track)}")

    identity_payload = [{
        "unit_id": r["unit_id"],
        "season_id": r["season_id"],
        "date_local": r["date_local"],
        "selected_target_order": r["selected_target_order"],
        "selected_target_percentile": r["selected_target_percentile"],
        "sar_execution_status": r["sar_execution_status"],
        "pre_item_id": r["pre_item_id"],
        "post_item_id": r["post_item_id"],
        "projection": r["projection"],
    } for r in windows]

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-bulk-execution-manifest-v0.1",
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
        "purpose": "Bind all frozen PRIMARY6 Sentinel-1 selected-window identities to the pre-outcome R1-R4 execution contract before bulk science-pixel processing.",
        "source_catalog": str(args.catalog),
        "source_catalog_sha256": sha256_bytes(catalog_raw),
        "source_selected_window_identity_sha256": catalog.get("selected_window_identity_sha256"),
        "source_a4_contract": str(args.a4_contract),
        "source_a4_contract_sha256": sha256_bytes(a4_raw),
        "source_reconciliation": str(args.reconciliation),
        "source_reconciliation_sha256": sha256_bytes(reconciliation_raw),
        "source_projection_amendment": str(args.projection_amendment),
        "source_projection_amendment_sha256": sha256_bytes(projection_raw),
        "source_graph_family_audit": str(args.graph_audit),
        "source_graph_family_audit_sha256": sha256_bytes(graph_audit_raw),
        "selected_window_count": len(windows),
        "compatible_pair_count": compatible,
        "missing_compatible_pair_count": missing,
        "unknown_pair_count": 0,
        "track_window_counts": dict(sorted(per_track.items())),
        "track_compatible_pair_counts": dict(sorted(per_track_compatible.items())),
        "track_missing_pair_counts": {k: int(per_track_missing.get(k, 0)) for k in sorted(per_track)},
        "track_projection": projection["resolution"]["track_projection"],
        "operator_chain": projection["resolution"]["operator_chain_identical"],
        "r3_minimum_common_support": reconciliation["required_processing_identity"]["r3"],
        "canonical_r4_features": reconciliation["canonical_primary6_sar_features"],
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
        "execution_identity_sha256": canonical_sha(identity_payload),
        "windows": windows,
        "status": "PASS_108_WINDOWS_BOUND_104_COMPATIBLE_4_MISSING_NO_RESELECTION_NO_OUTCOME",
    }
    guards(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "selected_window_count": report["selected_window_count"],
        "compatible_pair_count": report["compatible_pair_count"],
        "missing_compatible_pair_count": report["missing_compatible_pair_count"],
        "track_window_counts": report["track_window_counts"],
        "track_compatible_pair_counts": report["track_compatible_pair_counts"],
        "track_missing_pair_counts": report["track_missing_pair_counts"],
        "execution_identity_sha256": report["execution_identity_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
