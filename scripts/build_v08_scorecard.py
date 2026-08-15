#!/usr/bin/env python3
"""Construye la scorecard conservadora y auditable de cierre IRFEN v0.8.

La scorecard solo reconoce hitos completos de 25 puntos. No modifica umbrales,
recomendaciones ni estado operativo, y nunca convierte evidencia experimental
en autorización de producción.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CONTRACT_PATH = ROOT / "config" / "v08_closeout_contract.json"
OUT = SITE / "data" / "v08_scorecard.json"


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def item(item_id: str, passed: bool, evidence):
    return {"id": item_id, "passed": bool(passed), "evidence": evidence}


def milestone(percentage: int, prior_reached: bool, checks: list[dict]):
    own_gate = all(c["passed"] for c in checks)
    reached = bool(prior_reached and own_gate)
    return {
        "percentage": percentage,
        "status": "REACHED" if reached else "BLOCKED",
        "cumulative": True,
        "reached": reached,
        "checks": checks,
        "blocking_check_ids": [c["id"] for c in checks if not c["passed"]],
    }


def main():
    contract = load(CONTRACT_PATH, {}) or {}
    test_report = load(SITE / "data" / "test_report.json", {}) or {}
    state = load(SITE / "data" / "experimental_state.json", {}) or {}
    early = load(SITE / "data" / "calibration" / "imerg_early_live_archive.json", {}) or {}
    verification = load(SITE / "data" / "forecast" / "verification.json", {}) or {}
    shadow = load(SITE / "data" / "validation" / "shadow_runs.json", {}) or {}
    scientific = load(SITE / "data" / "scientific_status.json", {}) or {}

    pilots = contract.get("pilot_zone_ids") or []
    zones = state.get("zones") or []
    zones_by_id = {z.get("zone_id"): z for z in zones}
    recommendations_safe = (
        set(zones_by_id) == set(pilots)
        and all(
            z.get("production_use") is False
            and (z.get("test_recommendation") or {}).get("mode") == "TEST_ONLY"
            and str((z.get("test_recommendation") or {}).get("code", "")).startswith("TEST_")
            and (z.get("test_recommendation") or {}).get("operational_alert") is False
            for z in zones
        )
    )
    workflow_evidence = {
        path: (ROOT / path).is_file()
        for path in contract.get("required_workflows", [])
    }
    checks25 = [
        item("automation_publication_smoke_contracts_present", all(workflow_evidence.values()), workflow_evidence),
        item(
            "regression_passes",
            test_report.get("status") == "PASS" and int(test_report.get("failed", -1)) == 0,
            {
                "generated_at": test_report.get("generated_at"),
                "passed": test_report.get("passed"),
                "failed": test_report.get("failed"),
            },
        ),
        item(
            "three_pilots_and_test_only_guards",
            state.get("production_use") is False
            and state.get("production_ready") is False
            and recommendations_safe,
            {
                "expected_pilots": pilots,
                "observed_pilots": sorted(zones_by_id),
                "core_status": (state.get("core_test_status") or {}).get("code"),
            },
        ),
        item(
            "shadow_archive_started",
            shadow.get("production_use") is False and int(shadow.get("record_count", 0)) >= 1,
            {"record_count": shadow.get("record_count"), "updated_at": shadow.get("updated_at")},
        ),
    ]
    m25 = milestone(25, True, checks25)

    early_contract = contract.get("imerg_early") or {}
    early_summary = early.get("summary") or {}
    rolling = early.get("rolling_by_target") or {}
    targets = early_contract.get("target_ids") or []
    windows = early_contract.get("required_windows") or []
    target_windows = {
        target: {
            window: bool((rolling.get(target) or {}).get(window, {}).get("available"))
            and bool((rolling.get(target) or {}).get(window, {}).get("continuous"))
            for window in windows
        }
        for target in targets
    }
    latency_fields = ("latency_median_hours", "latency_p90_hours", "latency_max_hours")
    checks50 = [
        item(
            "imerg_latency_sample_sufficient",
            int(early_summary.get("source_available_count", 0)) >= int(early_contract.get("minimum_latency_records", 0))
            and all(early_summary.get(k) is not None for k in latency_fields),
            {
                "source_available_count": early_summary.get("source_available_count"),
                "minimum": early_contract.get("minimum_latency_records"),
                **{k: early_summary.get(k) for k in latency_fields},
            },
        ),
        item(
            "imerg_24h_continuous_run_observed",
            int(early_summary.get("longest_continuous_run_samples", 0))
            >= int(early_contract.get("minimum_continuous_half_hour_samples", 48)),
            {
                "longest_samples": early_summary.get("longest_continuous_run_samples"),
                "longest_hours": early_summary.get("longest_continuous_run_hours"),
                "required_samples": early_contract.get("minimum_continuous_half_hour_samples"),
                "continuity_coverage_pct": early_summary.get("continuity_coverage_pct"),
            },
        ),
        item(
            "imerg_windows_3h_6h_24h_valid_for_all_targets",
            bool(target_windows) and all(all(v.values()) for v in target_windows.values()),
            target_windows,
        ),
    ]
    m50 = milestone(50, m25["reached"], checks50)

    min_pairs = int((contract.get("forecast_verification") or {}).get("minimum_mature_pairs_per_pilot", 30))
    by_zone = verification.get("by_zone") or {}
    pair_counts = {zid: int((by_zone.get(zid) or {}).get("n", 0)) for zid in pilots}
    expected_blockers = contract.get("known_external_blockers") or {}
    blocker_contracts = {}
    for zid in pilots:
        z = zones_by_id.get(zid) or {}
        actual = set(z.get("blockers") or [])
        expected = set(expected_blockers.get(zid) or [])
        blocker_contracts[zid] = {
            "test_ready": z.get("test_ready") is True,
            "expected_external_blockers": sorted(expected),
            "declared_blockers": sorted(actual),
            "contract_complete_or_explicitly_blocked": z.get("test_ready") is True and actual.issubset(expected),
        }
    checks75 = [
        item(
            "geos_mature_pairs_per_pilot",
            bool(pair_counts) and all(n >= min_pairs for n in pair_counts.values()),
            {"minimum_per_pilot": min_pairs, "pair_counts": pair_counts, "total_pairs": verification.get("total_pairs")},
        ),
        item(
            "pilot_validation_contracts_complete_or_externally_blocked",
            bool(blocker_contracts)
            and all(x["contract_complete_or_explicitly_blocked"] for x in blocker_contracts.values()),
            blocker_contracts,
        ),
    ]
    m75 = milestone(75, m50["reached"], checks75)

    accepted_labels = set((contract.get("shadow_validation") or {}).get("accepted_outcome_labels") or [])
    shadow_records = shadow.get("records") or []
    reviewed = [
        r for r in shadow_records
        if (r.get("outcome_verification") or {}).get("status") != "PENDING_REAL_WORLD_OUTCOME_REVIEW"
        and (r.get("outcome_verification") or {}).get("label") in accepted_labels
    ]
    required_reviewed = int((contract.get("shadow_validation") or {}).get("minimum_reviewed_daily_records", 30))
    unresolved = {zid: zones_by_id.get(zid, {}).get("blockers") or [] for zid in pilots}
    local = (state.get("lima_east_submodels") or {}).get("chosica_local_debris_flows") or {}
    release_path = ROOT / str(contract.get("release_document", "docs/V08_RELEASE.md"))
    release_text = release_path.read_text(encoding="utf-8") if release_path.is_file() else ""
    checks100 = [
        item(
            "shadow_outcomes_sufficient_and_reviewed",
            len(reviewed) >= required_reviewed,
            {"reviewed_records": len(reviewed), "required": required_reviewed, "archive_records": len(shadow_records)},
        ),
        item(
            "scientific_and_hydraulic_blockers_resolved",
            all(not values for values in unresolved.values()) and local.get("live_test_ready") is True,
            {"pilot_blockers": unresolved, "pedregal_live_test_ready": local.get("live_test_ready")},
        ),
        item(
            "final_audit_and_release_documented",
            test_report.get("status") == "PASS"
            and scientific.get("production_ready") is False
            and release_path.is_file()
            and "v0.8" in release_text
            and "TEST_ONLY" in release_text,
            {
                "regression_status": test_report.get("status"),
                "scientific_production_ready": scientific.get("production_ready"),
                "release_document": str(release_path.relative_to(ROOT)),
                "release_document_present": release_path.is_file(),
            },
        ),
    ]
    m100 = milestone(100, m75["reached"], checks100)

    milestones = [m25, m50, m75, m100]
    current = max([m["percentage"] for m in milestones if m["reached"]], default=0)
    next_entry = next((m for m in milestones if not m["reached"]), None)
    output = {
        "version": "0.8-closeout-scorecard-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "measurement_principle": "Milestones are cumulative and evidence-based; partial completion within a milestone does not increase the reported percentage.",
        "contract": "config/v08_closeout_contract.json",
        "current_milestone_pct": current,
        "next_milestone_pct": next_entry["percentage"] if next_entry else None,
        "milestones": milestones,
        "next_blocking_check_ids": next_entry["blocking_check_ids"] if next_entry else [],
        "evidence_timestamps": {
            "regression": test_report.get("generated_at"),
            "experimental_state": state.get("generated_at"),
            "imerg_early": early.get("updated_at"),
            "forecast_verification": verification.get("generated_at"),
            "shadow_validation": shadow.get("updated_at"),
        },
        "safety_rules": contract.get("safety_rules") or [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "current_milestone_pct": current,
        "next_milestone_pct": output["next_milestone_pct"],
        "next_blocking_check_ids": output["next_blocking_check_ids"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
