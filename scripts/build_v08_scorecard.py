#!/usr/bin/env python3
"""Construye la scorecard conservadora y auditable de cierre IRFEN v0.8.

La scorecard solo reconoce hitos completos de 25 puntos. No modifica umbrales,
recomendaciones ni estado operativo, y nunca convierte evidencia experimental
en autorización de producción.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import json

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CONTRACT_PATH = ROOT / "config" / "v08_closeout_contract.json"
OUT = SITE / "data" / "v08_scorecard.json"
OFFICIAL_OUTCOME_HOST_SUFFIXES = (
    "senamhi.gob.pe",
    "ana.gob.pe",
    "indeci.gob.pe",
    "gob.pe",
)


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


def final_release_audit_gate(shadow_gate_passed: bool, scientific_gate_passed: bool, release_document_complete: bool):
    """Require every independent closeout prerequisite; no partial shortcut."""
    return bool(shadow_gate_passed and scientific_gate_passed and release_document_complete)


def target_window_gate(rolling: dict, targets: list[str], windows: list[str]):
    """Require every declared rolling window to be both available and continuous."""
    evidence = {
        target: {
            window: bool((rolling.get(target) or {}).get(window, {}).get("available"))
            and bool((rolling.get(target) or {}).get(window, {}).get("continuous"))
            for window in windows
        }
        for target in targets
    }
    return bool(evidence) and all(all(values.values()) for values in evidence.values()), evidence


def review_after_utc_day_close(record: dict):
    try:
        snapshot_day = date.fromisoformat(str(record.get("snapshot_date_utc")))
        closed_at = datetime.combine(snapshot_day + timedelta(days=1), time.min, tzinfo=timezone.utc)
        reviewed_at = str((record.get("outcome_verification") or {}).get("reviewed_at"))
        reviewed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        return reviewed.tzinfo is not None and reviewed.astimezone(timezone.utc) >= closed_at
    except Exception:
        return False


def snapshot_captured_within_pre_outcome_window(record: dict, latest_delay_minutes: int = 120):
    """Reject snapshots taken late enough to have observed the same day's result."""
    try:
        snapshot_day = date.fromisoformat(str(record.get("snapshot_date_utc")))
        day_start = datetime.combine(snapshot_day, time.min, tzinfo=timezone.utc)
        captured = datetime.fromisoformat(str(record.get("archived_at")).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            return False
        captured_utc = captured.astimezone(timezone.utc)
        return day_start <= captured_utc <= day_start + timedelta(minutes=latest_delay_minutes)
    except Exception:
        return False


def external_validation_gate(contract: dict, ledger: dict, pilots: list[str]):
    """Accept external evidence only when every required item is traceable and reviewed."""
    contract_by = {row.get("zone_id"): row for row in contract.get("pilots", [])}
    ledger_by = {row.get("zone_id"): row for row in ledger.get("pilots", [])}
    evidence = {}
    for zone_id in pilots:
        required_order = (
            (contract_by.get(zone_id) or {}).get("required_evidence_ids") or []
        )
        required = set(required_order)
        items = (ledger_by.get(zone_id) or {}).get("items") or []
        items_by_id = {row.get("evidence_id"): row for row in items}
        accepted = {
            row.get("evidence_id") for row in items
            if row.get("status") == "ACCEPTED"
            and row.get("official_sources")
            and (row.get("review") or {}).get("reviewed_by")
            and (row.get("review") or {}).get("reviewed_at")
            and (row.get("review") or {}).get("automatic") is False
        }
        candidates = {
            row.get("evidence_id") for row in items
            if row.get("status") in {"CANDIDATE_REVIEW", "PARTIAL_CANDIDATE_REVIEW"}
            and row.get("official_sources")
        }
        missing = sorted(required - accepted)
        review_queue = []
        for evidence_id in required_order:
            if evidence_id in accepted:
                continue
            row = items_by_id.get(evidence_id) or {}
            review_queue.append({
                "evidence_id": evidence_id,
                "status": row.get("status", "MISSING"),
                "official_source_count": len(row.get("official_sources") or []),
                "remaining_gap": row.get("remaining_gap") or "No candidate evidence recorded.",
                "named_human_review_required": True,
                "automatic_acceptance_forbidden": True,
            })
        evidence[zone_id] = {
            "required_count": len(required),
            "accepted_count": len(required & accepted),
            "candidate_count": len(required & candidates),
            "candidate_evidence_ids": sorted(required & candidates),
            "missing_without_candidate_count": len(required - accepted - candidates),
            "missing_or_unaccepted_evidence_ids": missing,
            "review_queue": review_queue,
            "passed": bool(required) and not missing,
        }
    passed = (
        contract.get("production_use") is False
        and ledger.get("production_use") is False
        and set(contract_by) == set(pilots)
        and set(ledger_by) == set(pilots)
        and all(row["passed"] for row in evidence.values())
    )
    return passed, evidence


def official_outcome_url(url: str):
    host = (urlparse(str(url)).hostname or "").lower()
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in OFFICIAL_OUTCOME_HOST_SUFFIXES
    )


def shadow_record_eligibility(
    record: dict,
    pilots: list[str],
    minimum_pairs_per_pilot: int,
    accepted_labels: set[str] | None = None,
    latest_capture_delay_minutes: int = 120,
):
    """Return auditable gates for a reviewed shadow day to count toward closure."""
    accepted_labels = accepted_labels or {"EVENT", "NONE"}
    health = record.get("source_health") or {}
    outcome = record.get("outcome_verification") or {}
    outcome_label = outcome.get("label")
    official_sources = outcome.get("official_source") or []
    zones = record.get("zones") or []
    zones_by_id = {zone.get("zone_id"): zone for zone in zones}
    pair_counts = health.get("forecast_verification_pairs_by_zone") or {}
    checks = {
        "snapshot_not_production": record.get("production_use") is False,
        "snapshot_captured_within_pre_outcome_window": snapshot_captured_within_pre_outcome_window(
            record, latest_capture_delay_minutes
        ),
        "all_pilots_present": set(zones_by_id) == set(pilots),
        "all_recommendations_test_only": all(
            str(((zones_by_id.get(zid) or {}).get("recommendation") or {}).get("code", "")).startswith("TEST_")
            and ((zones_by_id.get(zid) or {}).get("recommendation") or {}).get("mode") == "TEST_ONLY"
            and ((zones_by_id.get(zid) or {}).get("recommendation") or {}).get("operational_alert") is False
            for zid in pilots
        ),
        "forecast_available": health.get("forecast_available") is True,
        "forecast_pairs_mature_at_snapshot": all(
            int(pair_counts.get(zid, 0)) >= minimum_pairs_per_pilot for zid in pilots
        ),
        "imerg_early_available": health.get("imerg_early_status") == "EARLY_HALFHOURLY_SOURCE_AVAILABLE",
        "imerg_latency_recorded": health.get("imerg_early_latency_hours") is not None,
        "regression_passed": health.get("regression_status") == "PASS",
        "outcome_status_reviewed": outcome.get("status") == "REVIEWED_REAL_WORLD_OUTCOME",
        "outcome_label_accepted": outcome_label in accepted_labels,
        "outcome_official_sources_recorded": bool(official_sources)
        and all(official_outcome_url(url) for url in official_sources),
        "outcome_named_human_reviewer": bool(str(outcome.get("reviewed_by") or "").strip()),
        "outcome_not_automatic": outcome.get("automatic") is False,
        "outcome_counts_toward_closeout_explicit": outcome.get("counts_toward_closeout") is True,
        "outcome_label_semantics_supported": (
            outcome_label == "EVENT" and bool(str(outcome.get("verified_event") or "").strip())
        ) or (
            outcome_label == "NONE" and outcome.get("comprehensive_none_coverage") is True
        ),
        "outcome_review_after_utc_day_close": review_after_utc_day_close(record),
    }
    return {"eligible": all(checks.values()), "checks": checks}


def shadow_outcome_review_queue(
    shadow_records: list[dict],
    official_outcome_evidence: dict,
    pilots: list[str],
    minimum_pairs_per_pilot: int,
    accepted_labels: set[str],
    latest_capture_delay_minutes: int = 120,
):
    """Expose unresolved shadow days without inferring an outcome from missing evidence."""
    evidence_by_date = {
        row.get("snapshot_date_utc"): row
        for row in official_outcome_evidence.get("records", [])
    }
    queue = []
    for record in shadow_records:
        outcome = record.get("outcome_verification") or {}
        eligibility = shadow_record_eligibility(
            record,
            pilots,
            minimum_pairs_per_pilot,
            accepted_labels,
            latest_capture_delay_minutes,
        )
        accepted_outcome = outcome.get("label") in accepted_labels
        if accepted_outcome and eligibility["eligible"]:
            continue

        evidence_record = evidence_by_date.get(record.get("snapshot_date_utc")) or {}
        captures = evidence_record.get("captures") or []
        latest_capture = max(
            captures,
            key=lambda row: str(row.get("captured_at") or ""),
            default={},
        )
        pilot_links = []
        for source in latest_capture.get("sources") or []:
            summary = source.get("summary") or {}
            pilot_links.extend(summary.get("pilot_report_links_for_snapshot_date") or [])
        unique_pilot_links = {
            row.get("url") for row in pilot_links if row.get("url")
        }
        failed_checks = sorted(
            check_id for check_id, passed in eligibility["checks"].items() if not passed
        )
        if accepted_outcome:
            action = "RESOLVE_ELIGIBILITY_FAILURES"
        elif unique_pilot_links:
            action = "HUMAN_REVIEW_REQUIRED"
        else:
            action = "WAIT_FOR_OFFICIAL_EVIDENCE"
        queue.append({
            "snapshot_date_utc": record.get("snapshot_date_utc"),
            "review_status": outcome.get("status", "PENDING_REAL_WORLD_OUTCOME_REVIEW"),
            "current_label": outcome.get("label"),
            "failed_eligibility_check_ids": failed_checks,
            "latest_evidence_capture_at": latest_capture.get("captured_at"),
            "official_pilot_specific_link_count": len(unique_pilot_links),
            "action": action,
            "named_human_review_required": True,
            "automatic_outcome_classification_forbidden": True,
            "missing_evidence_is_not_none": True,
            "counts_toward_closeout": False,
        })
    return queue


def main():
    contract = load(CONTRACT_PATH, {}) or {}
    test_report = load(SITE / "data" / "test_report.json", {}) or {}
    state = load(SITE / "data" / "experimental_state.json", {}) or {}
    early = load(SITE / "data" / "calibration" / "imerg_early_live_archive.json", {}) or {}
    verification = load(SITE / "data" / "forecast" / "verification.json", {}) or {}
    shadow = load(SITE / "data" / "validation" / "shadow_runs.json", {}) or {}
    official_outcomes = load(
        SITE / "data" / "validation" / "official_outcome_evidence.json", {}
    ) or {}
    scientific = load(SITE / "data" / "scientific_status.json", {}) or {}
    external_contract = load(ROOT / "config" / "v08_external_validation_contract.json", {}) or {}
    external_ledger = load(SITE / "data" / "validation" / "v08_external_evidence.json", {}) or {}

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
    validated_windows = early.get("validated_windows_by_target") or rolling
    targets = early_contract.get("target_ids") or []
    windows = early_contract.get("required_windows") or []
    target_windows_passed, target_windows = target_window_gate(validated_windows, targets, windows)
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
            target_windows_passed,
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
    latest_capture_delay_minutes = int(
        ((contract.get("shadow_validation") or {}).get("snapshot_capture") or {}).get(
            "latest_eligible_capture_delay_minutes", 120
        )
    )
    shadow_records = shadow.get("records") or []
    reviewed_all = [
        r for r in shadow_records
        if (r.get("outcome_verification") or {}).get("status") != "PENDING_REAL_WORLD_OUTCOME_REVIEW"
    ]
    reviewed_outcomes = [
        r for r in reviewed_all
        if (r.get("outcome_verification") or {}).get("label") in accepted_labels
    ]
    required_reviewed = int((contract.get("shadow_validation") or {}).get("minimum_reviewed_daily_records", 30))
    shadow_eligibility = [
        {
            "snapshot_date_utc": record.get("snapshot_date_utc"),
            "label": (record.get("outcome_verification") or {}).get("label"),
            **shadow_record_eligibility(
                record,
                pilots,
                min_pairs,
                accepted_labels,
                latest_capture_delay_minutes,
            ),
        }
        for record in reviewed_outcomes
    ]
    reviewed = [entry for entry in shadow_eligibility if entry["eligible"]]
    reviewed_label_counts = {
        label: sum(1 for entry in reviewed if entry.get("label") == label)
        for label in accepted_labels
    }
    minimum_event_days = int((contract.get("shadow_validation") or {}).get("minimum_verified_event_days", 1))
    minimum_none_days = int((contract.get("shadow_validation") or {}).get("minimum_verified_none_days", 1))
    unresolved = {zid: zones_by_id.get(zid, {}).get("blockers") or [] for zid in pilots}
    local = (state.get("lima_east_submodels") or {}).get("chosica_local_debris_flows") or {}
    release_path = ROOT / str(contract.get("release_document", "docs/V08_RELEASE.md"))
    release_text = release_path.read_text(encoding="utf-8") if release_path.is_file() else ""
    release_marker = str(contract.get("release_completion_marker", "Release status: COMPLETE"))
    supplemental_targets = early_contract.get("supplemental_release_target_ids") or []
    supplemental_windows_passed, supplemental_windows = target_window_gate(
        validated_windows, supplemental_targets, windows
    )
    shadow_gate_passed = (
        len(reviewed) >= required_reviewed
        and int(reviewed_label_counts.get("EVENT", 0)) >= minimum_event_days
        and int(reviewed_label_counts.get("NONE", 0)) >= minimum_none_days
    )
    shadow_review_queue = shadow_outcome_review_queue(
        shadow_records,
        official_outcomes,
        pilots,
        min_pairs,
        accepted_labels,
        latest_capture_delay_minutes,
    )
    external_evidence_passed, external_evidence = external_validation_gate(external_contract, external_ledger, pilots)
    scientific_gate_passed = (
        all(not values for values in unresolved.values())
        and local.get("live_test_ready") is True
        and external_evidence_passed
    )
    release_document_complete = (
        test_report.get("status") == "PASS"
        and scientific.get("production_ready") is False
        and release_path.is_file()
        and "v0.8" in release_text
        and "TEST_ONLY" in release_text
        and release_marker in release_text
    )
    checks100 = [
        item(
            "shadow_outcomes_sufficient_and_reviewed",
            shadow_gate_passed,
            {
                "eligible_reviewed_records": len(reviewed),
                "reviewed_records_total": len(reviewed_all),
                "reviewed_outcomes_total": len(reviewed_outcomes),
                "reviewed_uncertain_or_unaccepted": len(reviewed_all) - len(reviewed_outcomes),
                "reviewed_but_ineligible": len(reviewed_outcomes) - len(reviewed),
                "pending_outcome_review": len(shadow_records) - len(reviewed_all),
                "required": required_reviewed,
                "eligible_label_counts": reviewed_label_counts,
                "minimum_verified_event_days": minimum_event_days,
                "minimum_verified_none_days": minimum_none_days,
                "archive_records": len(shadow_records),
                "eligibility": shadow_eligibility,
                "review_queue": shadow_review_queue,
            },
        ),
        item(
            "scientific_and_hydraulic_blockers_resolved",
            scientific_gate_passed,
            {
                "pilot_blockers": unresolved,
                "pedregal_live_test_ready": local.get("live_test_ready"),
                "external_evidence_gate_passed": external_evidence_passed,
                "external_evidence_by_pilot": external_evidence,
            },
        ),
        item(
            "final_audit_and_release_documented",
            final_release_audit_gate(
                shadow_gate_passed,
                scientific_gate_passed,
                release_document_complete and supplemental_windows_passed,
            ),
            {
                "prerequisite_shadow_gate_passed": shadow_gate_passed,
                "prerequisite_scientific_gate_passed": scientific_gate_passed,
                "supplemental_imerg_release_gate_passed": supplemental_windows_passed,
                "supplemental_imerg_windows": supplemental_windows,
                "regression_status": test_report.get("status"),
                "scientific_production_ready": scientific.get("production_ready"),
                "release_document": str(release_path.relative_to(ROOT)),
                "release_document_present": release_path.is_file(),
                "completion_marker": release_marker,
                "completion_marker_present": release_marker in release_text,
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
