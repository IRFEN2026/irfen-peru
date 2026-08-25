#!/usr/bin/env python3
"""Build the canonical, auditable IRFEN v0.8 shadow-review queue.

The builder reads only canonical repository data and the versioned closeout
contract. It never creates or changes a human outcome label. In particular,
missing or partial evidence remains UNKNOWN/UNCERTAIN and can never be turned
into EVENT or NONE by this script.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
import argparse
import hashlib
import json
import os
import tempfile

try:
    from build_v08_scorecard import (
        forecast_covers_target_day as scorecard_forecast_covers_target_day,
        official_outcome_url,
        review_after_utc_day_close as scorecard_review_after_utc_day_close,
        shadow_record_eligibility,
        snapshot_captured_within_pre_outcome_window as scorecard_snapshot_in_window,
    )
except ImportError:  # Imported as scripts.build_shadow_review_queue in tests.
    from scripts.build_v08_scorecard import (
        forecast_covers_target_day as scorecard_forecast_covers_target_day,
        official_outcome_url,
        review_after_utc_day_close as scorecard_review_after_utc_day_close,
        shadow_record_eligibility,
        snapshot_captured_within_pre_outcome_window as scorecard_snapshot_in_window,
    )

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "site/data/validation/shadow_runs.json"
DEFAULT_CONTRACT = ROOT / "config/v08_closeout_contract.json"
DEFAULT_SCHEMA = ROOT / "config/shadow_review_queue.schema.v1.json"
DEFAULT_OUTPUT = ROOT / "site/data/validation/shadow_review_queue.json"

SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "IRFEN_SHADOW_REVIEW_QUEUE"
FLOW_STATES = (
    "DAY_NOT_CLOSED",
    "READY_FOR_HUMAN_REVIEW",
    "TECHNICALLY_INELIGIBLE",
    "REVIEWED_UNCERTAIN",
    "ELIGIBLE_EVENT",
    "ELIGIBLE_NONE",
)
ACCEPTED_STORED_LABELS = {"EVENT", "NONE", "UNCERTAIN"}
PENDING_REVIEW_STATUS = "PENDING_REAL_WORLD_OUTCOME_REVIEW"
REVIEWED_REVIEW_STATUS = "REVIEWED_REAL_WORLD_OUTCOME"
IMERG_AVAILABLE_STATUS = "EARLY_HALFHOURLY_SOURCE_AVAILABLE"

TECHNICAL_SCORECARD_CHECK_IDS = (
    "snapshot_not_production",
    "snapshot_captured_within_pre_outcome_window",
    "all_pilots_present",
    "all_recommendations_test_only",
    "forecast_available",
    "forecast_covers_target_day",
    "forecast_pairs_mature_at_snapshot",
    "imerg_early_available",
    "imerg_latency_recorded",
    "regression_passed",
)

REVIEW_SCORECARD_CHECK_IDS = (
    "outcome_status_reviewed",
    "outcome_label_accepted",
    "outcome_official_sources_recorded",
    "outcome_named_human_reviewer",
    "outcome_not_automatic",
    "outcome_counts_toward_closeout_explicit",
    "outcome_label_semantics_supported",
    "outcome_review_after_utc_day_close",
)



def parse_utc(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp and normalize it to UTC.

    Invalid or timezone-less values return ``None`` rather than being guessed.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def utc_iso(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def day_close_utc(snapshot_date: str) -> datetime | None:
    try:
        target = date.fromisoformat(snapshot_date)
    except (TypeError, ValueError):
        return None
    return datetime.combine(target + timedelta(days=1), time.min, tzinfo=timezone.utc)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"No existe el archivo requerido: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido en {path}: {exc}") from exc


def normalize_sources(value: Any) -> list[str]:
    if isinstance(value, str):
        values: Iterable[Any] = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]


def normalize_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def normalize_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        if value is None or str(value).strip() == "":
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def gate(
    gate_id: str,
    passed: bool,
    category: str,
    evidence: Any = None,
    contract_reference: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": gate_id,
        "category": category,
        "passed": bool(passed),
        "evidence": evidence,
    }
    if contract_reference:
        row["contract_reference"] = contract_reference
    return row


def add_inconsistency(
    target: list[dict[str, Any]],
    code: str,
    message: str,
    *,
    snapshot_date_utc: str | None = None,
    severity: str = "ERROR",
    evidence: Any = None,
) -> None:
    row: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if snapshot_date_utc is not None:
        row["snapshot_date_utc"] = snapshot_date_utc
    if evidence is not None:
        row["evidence"] = evidence
    target.append(row)


def contract_projection(contract: dict[str, Any]) -> dict[str, Any]:
    shadow = contract.get("shadow_validation") or {}
    acceptance = shadow.get("acceptance_rules") or {}
    capture = shadow.get("snapshot_capture") or {}
    forecast = contract.get("forecast_verification") or {}
    return {
        "pilot_zone_ids": list(contract.get("pilot_zone_ids") or []),
        "minimum_mature_pairs_per_pilot": forecast.get(
            "minimum_mature_pairs_per_pilot"
        ),
        "accepted_outcome_labels": list(shadow.get("accepted_outcome_labels") or []),
        "snapshot_capture": {
            "earliest_eligible_capture_lead_minutes": capture.get(
                "earliest_eligible_capture_lead_minutes", 720
            ),
            "latest_eligible_capture_delay_minutes": capture.get(
                "latest_eligible_capture_delay_minutes", 120
            ),
        },
        "acceptance_rules": {
            key: acceptance.get(key)
            for key in (
                "named_human_reviewer_required",
                "automatic_classification_forbidden",
                "official_source_required",
                "counts_toward_closeout_must_be_explicit",
                "pre_outcome_capture_window_required",
                "forecast_must_cover_target_day",
                "none_requires_comprehensive_coverage",
                "event_requires_verified_event_description",
            )
        },
    }



def source_projection(archive: dict[str, Any], pilots: list[str]) -> dict[str, Any]:
    """Project only fields that influence the queue contract.

    The resulting SHA-256 is stable even if unrelated historical notes or
    display-only fields change. Every queue value is derivable from this
    projection plus the versioned closeout contract.
    """
    records = []
    for record in archive.get("records") or []:
        zones = record.get("zones") if isinstance(record.get("zones"), list) else []
        zone_projection = []
        for zone in zones:
            if not isinstance(zone, dict):
                zone_projection.append({"invalid_zone": True})
                continue
            recommendation = zone.get("recommendation") or {}
            zone_projection.append(
                {
                    "zone_id": zone.get("zone_id"),
                    "recommendation": {
                        "code": recommendation.get("code"),
                        "mode": recommendation.get("mode"),
                        "operational_alert": recommendation.get("operational_alert"),
                    },
                    "forecast_mm": {
                        "available_future_hours": (zone.get("forecast_mm") or {}).get(
                            "available_future_hours"
                        ),
                    },
                }
            )
        health = record.get("source_health") or {}
        pairs = health.get("forecast_verification_pairs_by_zone") or {}
        review = record.get("outcome_verification") or {}
        window = record.get("pre_outcome_capture_window") or {}
        records.append(
            {
                "snapshot_date_utc": record.get("snapshot_date_utc"),
                "archived_at": record.get("archived_at"),
                "pre_outcome_capture_window": {
                    "start_utc": window.get("start_utc"),
                    "end_utc": window.get("end_utc"),
                    "captured_within_window": window.get("captured_within_window"),
                },
                "zones": zone_projection,
                "source_health": {
                    "forecast_available": health.get("forecast_available"),
                    "forecast_covers_target_day": health.get(
                        "forecast_covers_target_day"
                    ),
                    "forecast_verification_pairs_by_zone": {
                        pilot: pairs.get(pilot) for pilot in pilots
                    },
                    "imerg_early_status": health.get("imerg_early_status"),
                    "imerg_early_latency_hours": health.get(
                        "imerg_early_latency_hours"
                    ),
                    "regression_status": health.get("regression_status"),
                },
                "operational_dataset_status": record.get(
                    "operational_dataset_status"
                ),
                "production_use": record.get("production_use"),
                "outcome_verification": {
                    "status": review.get("status"),
                    "label": review.get("label"),
                    "verified_event": review.get("verified_event"),
                    "official_source": normalize_sources(
                        review.get("official_source")
                    ),
                    "reviewed_at": review.get("reviewed_at"),
                    "reviewed_by": review.get("reviewed_by"),
                    "automatic": review.get("automatic"),
                    "review_window_closed_utc": review.get(
                        "review_window_closed_utc"
                    ),
                    "comprehensive_none_coverage": review.get(
                        "comprehensive_none_coverage"
                    ),
                    "counts_toward_closeout": review.get(
                        "counts_toward_closeout"
                    ),
                },
                "integrity_chain_sha256": (
                    (record.get("integrity") or {}).get("chain_sha256")
                ),
            }
        )
    return {
        "archive_version": archive.get("version"),
        "archive_updated_at": archive.get("updated_at"),
        "record_count": archive.get("record_count"),
        "production_use": archive.get("production_use"),
        "production_ready": archive.get("production_ready"),
        "records": records,
    }


def _review_state(raw_status: Any, stored_label: Any) -> str:
    if raw_status == PENDING_REVIEW_STATUS and stored_label is None:
        return "PENDING"
    if raw_status == REVIEWED_REVIEW_STATUS and stored_label in ACCEPTED_STORED_LABELS:
        return "REVIEWED"
    return "UNKNOWN"


def _capture_window_bounds(
    snapshot_date_text: str,
    earliest_capture_lead_minutes: int,
    latest_capture_delay_minutes: int,
) -> tuple[datetime | None, datetime | None]:
    try:
        target = date.fromisoformat(snapshot_date_text)
    except (TypeError, ValueError):
        return None, None
    day_start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    return (
        day_start - timedelta(minutes=earliest_capture_lead_minutes),
        day_start + timedelta(minutes=latest_capture_delay_minutes),
    )


def _forecast_horizon_details(
    record: dict[str, Any], pilots: list[str]
) -> tuple[float | None, dict[str, int | float | None]]:
    try:
        snapshot_day = date.fromisoformat(str(record.get("snapshot_date_utc")))
        target_end = datetime.combine(
            snapshot_day + timedelta(days=1), time.min, tzinfo=timezone.utc
        )
        captured = parse_utc(record.get("archived_at"))
        required_hours = (target_end - captured).total_seconds() / 3600 if captured else None
    except (TypeError, ValueError):
        required_hours = None
    zones_by_id = {
        zone.get("zone_id"): zone
        for zone in (record.get("zones") or [])
        if isinstance(zone, dict) and zone.get("zone_id")
    }
    available = {
        pilot: normalize_number(
            (((zones_by_id.get(pilot) or {}).get("forecast_mm") or {}).get(
                "available_future_hours"
            ))
        )
        for pilot in pilots
    }
    return required_hours, available


def build_day(
    record: dict[str, Any],
    *,
    evaluation_as_of: datetime,
    pilots: list[str],
    minimum_pairs: int,
    accepted_closeout_labels: set[str],
    earliest_capture_lead_minutes: int,
    latest_capture_delay_minutes: int,
    inconsistencies: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot_date = record.get("snapshot_date_utc")
    snapshot_date_text = str(snapshot_date) if snapshot_date is not None else "UNKNOWN"
    close_at = day_close_utc(snapshot_date_text)
    day_closed = bool(close_at and evaluation_as_of >= close_at)

    stored_window = record.get("pre_outcome_capture_window")
    stored_window = stored_window if isinstance(stored_window, dict) else {}
    stored_window_start = stored_window.get("start_utc")
    stored_window_end = stored_window.get("end_utc")
    stored_captured = normalize_bool(stored_window.get("captured_within_window"))
    computed_window_start, computed_window_end = _capture_window_bounds(
        snapshot_date_text,
        earliest_capture_lead_minutes,
        latest_capture_delay_minutes,
    )
    captured_at = parse_utc(record.get("archived_at"))
    capture_calculation_available = bool(
        computed_window_start and computed_window_end and captured_at
    )
    computed_captured = bool(
        scorecard_snapshot_in_window(
            record,
            earliest_capture_lead_minutes,
            latest_capture_delay_minutes,
        )
    )
    if stored_captured is not None and stored_captured != computed_captured:
        add_inconsistency(
            inconsistencies,
            "CAPTURE_WINDOW_STORED_COMPUTED_MISMATCH",
            "captured_within_window almacenado contradice el cálculo reproducible del scorecard.",
            snapshot_date_utc=snapshot_date_text,
            evidence={
                "stored": stored_captured,
                "computed": computed_captured,
                "archived_at": record.get("archived_at"),
                "computed_start_utc": utc_iso(computed_window_start)
                if computed_window_start
                else None,
                "computed_end_utc": utc_iso(computed_window_end)
                if computed_window_end
                else None,
            },
        )

    zones_raw = record.get("zones")
    zones_raw = zones_raw if isinstance(zones_raw, list) else []
    zones_by_id: dict[str, dict[str, Any]] = {}
    unexpected_pilots: list[str] = []
    for zone in zones_raw:
        if not isinstance(zone, dict):
            continue
        zone_id = zone.get("zone_id")
        if not isinstance(zone_id, str) or not zone_id:
            continue
        if zone_id in zones_by_id:
            add_inconsistency(
                inconsistencies,
                "DUPLICATE_PILOT_IN_DAY",
                f"La jornada contiene el piloto {zone_id} más de una vez.",
                snapshot_date_utc=snapshot_date_text,
                evidence=zone_id,
            )
            continue
        zones_by_id[zone_id] = zone
        if zone_id not in pilots:
            unexpected_pilots.append(zone_id)

    present_pilots = [pilot for pilot in pilots if pilot in zones_by_id]
    missing_pilots = [pilot for pilot in pilots if pilot not in zones_by_id]
    recommendations: dict[str, dict[str, Any]] = {}
    no_operational_alerts = not missing_pilots
    for pilot in pilots:
        recommendation = (zones_by_id.get(pilot) or {}).get("recommendation") or {}
        recommendations[pilot] = {
            "code": recommendation.get("code"),
            "mode": recommendation.get("mode"),
            "operational_alert": recommendation.get("operational_alert"),
        }
        if recommendation.get("operational_alert") is not False:
            no_operational_alerts = False

    health = record.get("source_health") or {}
    stored_forecast_coverage = normalize_bool(
        health.get("forecast_covers_target_day")
    )
    computed_forecast_coverage = bool(
        scorecard_forecast_covers_target_day(record, pilots)
    )
    if (
        stored_forecast_coverage is not None
        and stored_forecast_coverage != computed_forecast_coverage
    ):
        add_inconsistency(
            inconsistencies,
            "FORECAST_COVERAGE_STORED_COMPUTED_MISMATCH",
            "forecast_covers_target_day almacenado contradice el cálculo reproducible del scorecard.",
            snapshot_date_utc=snapshot_date_text,
            evidence={
                "stored": stored_forecast_coverage,
                "computed": computed_forecast_coverage,
            },
        )
    required_future_hours, available_future_hours = _forecast_horizon_details(
        record, pilots
    )
    pairs_raw = health.get("forecast_verification_pairs_by_zone") or {}
    pairs_by_pilot = {
        pilot: normalize_number(pairs_raw.get(pilot)) for pilot in pilots
    }

    review = record.get("outcome_verification")
    review = review if isinstance(review, dict) else {}
    raw_review_status = review.get("status")
    stored_label = review.get("label")
    reviewed_at = review.get("reviewed_at")
    reviewed_by = review.get("reviewed_by")
    reviewer_identified = isinstance(reviewed_by, str) and bool(reviewed_by.strip())
    automatic = normalize_bool(review.get("automatic"))
    official_sources = normalize_sources(review.get("official_source"))
    invalid_official_sources = [
        url for url in official_sources if not official_outcome_url(url)
    ]
    official_sources_valid = bool(official_sources) and not invalid_official_sources
    reviewed_after_close = bool(scorecard_review_after_utc_day_close(record))
    verified_event = review.get("verified_event")
    comprehensive_none_coverage = normalize_bool(
        review.get("comprehensive_none_coverage")
    )
    counts_toward_closeout = normalize_bool(review.get("counts_toward_closeout"))
    review_state = _review_state(raw_review_status, stored_label)
    evidence_state = (
        stored_label if stored_label in ACCEPTED_STORED_LABELS else "UNKNOWN"
    )

    scorecard = shadow_record_eligibility(
        record,
        pilots,
        minimum_pairs,
        accepted_closeout_labels,
        earliest_capture_lead_minutes,
        latest_capture_delay_minutes,
    )
    scorecard_checks = {
        str(key): bool(value) for key, value in (scorecard.get("checks") or {}).items()
    }

    # Data consistency checks are reported, never repaired silently.
    if raw_review_status == PENDING_REVIEW_STATUS and stored_label is not None:
        add_inconsistency(
            inconsistencies,
            "PENDING_STATUS_WITH_STORED_LABEL",
            "El estado de revisión es pendiente pero existe una etiqueta almacenada.",
            snapshot_date_utc=snapshot_date_text,
            evidence={"status": raw_review_status, "label": stored_label},
        )
    if raw_review_status == REVIEWED_REVIEW_STATUS and stored_label is None:
        add_inconsistency(
            inconsistencies,
            "REVIEWED_STATUS_WITHOUT_STORED_LABEL",
            "El estado indica revisión completada pero no existe etiqueta almacenada.",
            snapshot_date_utc=snapshot_date_text,
            evidence={"status": raw_review_status, "label": stored_label},
        )
    if stored_label is not None and stored_label not in ACCEPTED_STORED_LABELS:
        add_inconsistency(
            inconsistencies,
            "INVALID_STORED_LABEL",
            "La etiqueta almacenada no pertenece al vocabulario humano permitido.",
            snapshot_date_utc=snapshot_date_text,
            evidence=stored_label,
        )
    if raw_review_status == REVIEWED_REVIEW_STATUS and not reviewer_identified:
        add_inconsistency(
            inconsistencies,
            "REVIEWED_WITHOUT_IDENTIFIED_REVIEWER",
            "La revisión humana no identifica al revisor requerido por el contrato vigente.",
            snapshot_date_utc=snapshot_date_text,
            evidence=reviewed_by,
        )
    if raw_review_status == REVIEWED_REVIEW_STATUS and not official_sources:
        add_inconsistency(
            inconsistencies,
            "REVIEWED_WITHOUT_OFFICIAL_SOURCE",
            "La revisión humana no conserva una fuente oficial.",
            snapshot_date_utc=snapshot_date_text,
        )
    if raw_review_status == REVIEWED_REVIEW_STATUS and invalid_official_sources:
        add_inconsistency(
            inconsistencies,
            "REVIEWED_WITH_NON_OFFICIAL_SOURCE",
            "La revisión contiene una URL fuera de los dominios oficiales aceptados por el scorecard.",
            snapshot_date_utc=snapshot_date_text,
            evidence=invalid_official_sources,
        )
    if raw_review_status == REVIEWED_REVIEW_STATUS and automatic is not False:
        add_inconsistency(
            inconsistencies,
            "REVIEWED_WITHOUT_EXPLICIT_AUTOMATIC_FALSE",
            "La revisión no conserva automatic=false de forma explícita.",
            snapshot_date_utc=snapshot_date_text,
            evidence=review.get("automatic"),
        )
    if (
        raw_review_status == REVIEWED_REVIEW_STATUS
        and reviewed_at
        and not reviewed_after_close
    ):
        add_inconsistency(
            inconsistencies,
            "REVIEW_BEFORE_UTC_DAY_CLOSE",
            "La revisión fue registrada antes del cierre UTC de la jornada.",
            snapshot_date_utc=snapshot_date_text,
            evidence={
                "reviewed_at": reviewed_at,
                "target_day_close_utc": utc_iso(close_at) if close_at else None,
            },
        )
    if stored_label == "UNCERTAIN" and counts_toward_closeout is True:
        add_inconsistency(
            inconsistencies,
            "UNCERTAIN_COUNTS_TOWARD_CLOSEOUT",
            "UNCERTAIN no puede contar para cierre.",
            snapshot_date_utc=snapshot_date_text,
        )

    gate_specs = [
        (
            "DAY_CLOSED_UTC",
            day_closed,
            "TEMPORAL",
            {
                "evaluation_as_of_utc": utc_iso(evaluation_as_of),
                "target_day_close_utc": utc_iso(close_at) if close_at else None,
            },
            None,
        ),
        (
            "PRE_OUTCOME_CAPTURE_WINDOW_STORED",
            bool(parse_utc(stored_window_start) and parse_utc(stored_window_end)),
            "TECHNICAL",
            {
                "start_utc": stored_window_start,
                "end_utc": stored_window_end,
                "stored_captured_within_window": stored_captured,
            },
            "diagnostic_only",
        ),
        (
            "CAPTURED_WITHIN_WINDOW",
            scorecard_checks.get(
                "snapshot_captured_within_pre_outcome_window", False
            ),
            "TECHNICAL",
            {
                "stored": stored_captured,
                "computed": computed_captured,
                "archived_at": record.get("archived_at"),
                "computed_start_utc": utc_iso(computed_window_start)
                if computed_window_start
                else None,
                "computed_end_utc": utc_iso(computed_window_end)
                if computed_window_end
                else None,
            },
            "build_v08_scorecard.shadow_record_eligibility.snapshot_captured_within_pre_outcome_window",
        ),
        (
            "ALL_PILOTS_PRESENT",
            scorecard_checks.get("all_pilots_present", False),
            "TECHNICAL",
            {
                "expected": pilots,
                "present": present_pilots,
                "missing": missing_pilots,
                "unexpected": unexpected_pilots,
            },
            "build_v08_scorecard.shadow_record_eligibility.all_pilots_present",
        ),
        (
            "ALL_RECOMMENDATIONS_TEST_ONLY",
            scorecard_checks.get("all_recommendations_test_only", False),
            "TECHNICAL",
            recommendations,
            "build_v08_scorecard.shadow_record_eligibility.all_recommendations_test_only",
        ),
        (
            "NO_OPERATIONAL_ALERTS",
            no_operational_alerts,
            "SAFETY",
            recommendations,
            "diagnostic_redundant_with_all_recommendations_test_only",
        ),
        (
            "FORECAST_AVAILABLE",
            scorecard_checks.get("forecast_available", False),
            "TECHNICAL",
            normalize_bool(health.get("forecast_available")),
            "build_v08_scorecard.shadow_record_eligibility.forecast_available",
        ),
        (
            "FORECAST_COVERS_TARGET_DAY",
            scorecard_checks.get("forecast_covers_target_day", False),
            "TECHNICAL",
            {
                "stored": stored_forecast_coverage,
                "computed": computed_forecast_coverage,
                "required_future_hours": required_future_hours,
                "available_future_hours_by_pilot": available_future_hours,
            },
            "build_v08_scorecard.shadow_record_eligibility.forecast_covers_target_day",
        ),
        (
            "MATURE_PAIRS_PER_PILOT",
            scorecard_checks.get("forecast_pairs_mature_at_snapshot", False),
            "TECHNICAL",
            {"minimum_required": minimum_pairs, "by_pilot": pairs_by_pilot},
            "build_v08_scorecard.shadow_record_eligibility.forecast_pairs_mature_at_snapshot",
        ),
        (
            "IMERG_EARLY_AVAILABLE",
            scorecard_checks.get("imerg_early_available", False),
            "TECHNICAL",
            health.get("imerg_early_status"),
            "build_v08_scorecard.shadow_record_eligibility.imerg_early_available",
        ),
        (
            "IMERG_EARLY_LATENCY_RECORDED",
            scorecard_checks.get("imerg_latency_recorded", False),
            "TECHNICAL",
            normalize_number(health.get("imerg_early_latency_hours")),
            "build_v08_scorecard.shadow_record_eligibility.imerg_latency_recorded",
        ),
        (
            "REGRESSION_PASS",
            scorecard_checks.get("regression_passed", False),
            "TECHNICAL",
            health.get("regression_status"),
            "build_v08_scorecard.shadow_record_eligibility.regression_passed",
        ),
        (
            "PRODUCTION_USE_FALSE",
            scorecard_checks.get("snapshot_not_production", False),
            "SAFETY",
            record.get("production_use"),
            "build_v08_scorecard.shadow_record_eligibility.snapshot_not_production",
        ),
        (
            "HUMAN_REVIEW_COMPLETED",
            scorecard_checks.get("outcome_status_reviewed", False),
            "HUMAN_REVIEW",
            raw_review_status,
            "build_v08_scorecard.shadow_record_eligibility.outcome_status_reviewed",
        ),
        (
            "STORED_LABEL_ACCEPTED_FOR_CLOSEOUT",
            scorecard_checks.get("outcome_label_accepted", False),
            "HUMAN_REVIEW",
            stored_label,
            "build_v08_scorecard.shadow_record_eligibility.outcome_label_accepted",
        ),
        (
            "OFFICIAL_SOURCES_VALID",
            scorecard_checks.get("outcome_official_sources_recorded", False),
            "HUMAN_REVIEW",
            {
                "sources": official_sources,
                "invalid_sources": invalid_official_sources,
            },
            "build_v08_scorecard.shadow_record_eligibility.outcome_official_sources_recorded",
        ),
        (
            "HUMAN_REVIEWER_IDENTIFIED",
            scorecard_checks.get("outcome_named_human_reviewer", False),
            "HUMAN_REVIEW",
            reviewed_by,
            "build_v08_scorecard.shadow_record_eligibility.outcome_named_human_reviewer",
        ),
        (
            "AUTOMATIC_CLASSIFICATION_FALSE",
            scorecard_checks.get("outcome_not_automatic", False),
            "SAFETY",
            automatic,
            "build_v08_scorecard.shadow_record_eligibility.outcome_not_automatic",
        ),
        (
            "COUNTS_TOWARD_CLOSEOUT_EXPLICIT_TRUE",
            scorecard_checks.get(
                "outcome_counts_toward_closeout_explicit", False
            ),
            "HUMAN_REVIEW",
            counts_toward_closeout,
            "build_v08_scorecard.shadow_record_eligibility.outcome_counts_toward_closeout_explicit",
        ),
        (
            "OUTCOME_LABEL_SEMANTICS_SUPPORTED",
            scorecard_checks.get("outcome_label_semantics_supported", False),
            "HUMAN_REVIEW",
            {
                "stored_label": stored_label,
                "verified_event": verified_event,
                "comprehensive_none_coverage": comprehensive_none_coverage,
            },
            "build_v08_scorecard.shadow_record_eligibility.outcome_label_semantics_supported",
        ),
        (
            "REVIEW_AFTER_UTC_DAY_CLOSE",
            scorecard_checks.get("outcome_review_after_utc_day_close", False),
            "TEMPORAL",
            {
                "reviewed_at": reviewed_at,
                "target_day_close_utc": utc_iso(close_at) if close_at else None,
            },
            "build_v08_scorecard.shadow_record_eligibility.outcome_review_after_utc_day_close",
        ),
    ]
    gates = [
        gate(gate_id, passed, category, evidence, reference)
        for gate_id, passed, category, evidence, reference in gate_specs
    ]

    technical_eligible = bool(
        day_closed
        and all(
            scorecard_checks.get(check_id, False)
            for check_id in TECHNICAL_SCORECARD_CHECK_IDS
        )
    )
    review_eligible = all(
        scorecard_checks.get(check_id, False)
        for check_id in REVIEW_SCORECARD_CHECK_IDS
    )
    closeout_eligible = bool(scorecard.get("eligible"))

    if not day_closed:
        flow_state = "DAY_NOT_CLOSED"
    elif raw_review_status == REVIEWED_REVIEW_STATUS and stored_label == "UNCERTAIN":
        flow_state = "REVIEWED_UNCERTAIN"
    elif closeout_eligible and stored_label == "EVENT":
        flow_state = "ELIGIBLE_EVENT"
    elif closeout_eligible and stored_label == "NONE":
        flow_state = "ELIGIBLE_NONE"
    elif raw_review_status == PENDING_REVIEW_STATUS and technical_eligible:
        flow_state = "READY_FOR_HUMAN_REVIEW"
    else:
        flow_state = "TECHNICALLY_INELIGIBLE"

    if counts_toward_closeout is True and not closeout_eligible:
        add_inconsistency(
            inconsistencies,
            "COUNTS_TRUE_BUT_NOT_ELIGIBLE",
            "counts_toward_closeout=true pero la jornada no supera todas las puertas del scorecard.",
            snapshot_date_utc=snapshot_date_text,
            evidence={"flow_state": flow_state, "stored_label": stored_label},
        )

    if stored_captured is None:
        capture_evidence_state = (
            "CALCULATED" if capture_calculation_available else "UNKNOWN"
        )
    else:
        capture_evidence_state = (
            "STORED_AND_CALCULATED"
            if capture_calculation_available
            else "STORED_ONLY"
        )

    return {
        "snapshot_date_utc": snapshot_date,
        "target_day_close_utc": utc_iso(close_at) if close_at else None,
        "day_closed_utc": day_closed,
        "capture_window": {
            "stored_start_utc": stored_window_start,
            "stored_end_utc": stored_window_end,
            "stored_captured_within_window": stored_captured,
            "computed_start_utc": utc_iso(computed_window_start)
            if computed_window_start
            else None,
            "computed_end_utc": utc_iso(computed_window_end)
            if computed_window_end
            else None,
            "computed_captured_within_window": computed_captured,
            "captured_within_window": computed_captured,
            "calculation_available": capture_calculation_available,
            "evidence_state": capture_evidence_state,
        },
        "pilots": {
            "expected": pilots,
            "present": present_pilots,
            "missing": missing_pilots,
            "unexpected": unexpected_pilots,
            "all_present": scorecard_checks.get("all_pilots_present", False),
            "test_only_recommendations": recommendations,
            "all_test_only": scorecard_checks.get(
                "all_recommendations_test_only", False
            ),
            "all_non_operational": no_operational_alerts,
        },
        "forecast": {
            "available": normalize_bool(health.get("forecast_available")),
            "stored_covers_target_day": stored_forecast_coverage,
            "computed_covers_target_day": computed_forecast_coverage,
            "covers_target_day": computed_forecast_coverage,
            "required_future_hours": required_future_hours,
            "available_future_hours_by_pilot": available_future_hours,
            "mature_pairs_by_pilot": pairs_by_pilot,
            "minimum_mature_pairs_per_pilot": minimum_pairs,
        },
        "imerg_early": {
            "status": health.get("imerg_early_status"),
            "available": scorecard_checks.get("imerg_early_available", False),
            "latency_hours": normalize_number(
                health.get("imerg_early_latency_hours")
            ),
        },
        "regression_status": health.get("regression_status"),
        "operational_dataset_status": {
            "value": record.get("operational_dataset_status"),
            "role": "ANNOTATION_ONLY",
            "is_eligibility_gate": False,
        },
        "human_review": {
            "raw_status": raw_review_status,
            "state": review_state,
            "reviewed_at": reviewed_at,
            "review_after_utc_day_close": reviewed_after_close,
            "reviewer": reviewed_by,
            "reviewer_identified": reviewer_identified,
            "automatic": automatic,
            "official_sources": official_sources,
            "official_sources_valid": official_sources_valid,
            "invalid_official_sources": invalid_official_sources,
            "stored_label": stored_label,
            "evidence_state": evidence_state,
            "verified_event": verified_event,
            "comprehensive_none_coverage": comprehensive_none_coverage,
            "counts_toward_closeout": counts_toward_closeout,
        },
        "scorecard_eligibility": {
            "eligible": closeout_eligible,
            "checks": scorecard_checks,
        },
        "technical_eligibility": technical_eligible,
        "review_eligibility": review_eligible,
        "closeout_eligible": closeout_eligible,
        "flow_state": flow_state,
        "failed_gates": [row["id"] for row in gates if not row["passed"]],
        "gates": gates,
    }



def artifact_refresh_required(
    artifact: dict[str, Any], now: datetime
) -> tuple[bool, list[str]]:
    if now.tzinfo is None:
        raise ValueError("now requiere zona horaria explícita")
    now = now.astimezone(timezone.utc)
    reasons: list[str] = []
    next_transition = parse_utc(
        ((artifact.get("freshness") or {}).get("next_transition_at_utc"))
    )
    if next_transition and now >= next_transition:
        reasons.append("NEXT_TRANSITION_REACHED")
    for day in artifact.get("days") or []:
        close_at = parse_utc(day.get("target_day_close_utc"))
        if (
            day.get("flow_state") == "DAY_NOT_CLOSED"
            and close_at
            and now >= close_at
        ):
            reasons.append(
                f"DAY_NOT_CLOSED_AFTER_CLOSE:{day.get('snapshot_date_utc')}"
            )
    return bool(reasons), reasons


def validate_artifact_contract(artifact: dict[str, Any]) -> None:
    errors: list[str] = []
    if artifact.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if artifact.get("artifact_type") != ARTIFACT_TYPE:
        errors.append("artifact_type")
    guards = artifact.get("guards") or {}
    required_guards = {
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "automatic_event_none_classification_enabled": False,
        "operational_dataset_status_is_gate": False,
        "stale_is_gate": False,
    }
    for key, expected in required_guards.items():
        if guards.get(key) is not expected:
            errors.append(f"guards.{key}")
    evaluation_as_of = parse_utc(artifact.get("evaluation_as_of_utc"))
    if evaluation_as_of is None:
        errors.append("evaluation_as_of_utc")
    for day in artifact.get("days") or []:
        if day.get("flow_state") not in FLOW_STATES:
            errors.append(f"invalid_flow_state:{day.get('flow_state')}")
        label = (day.get("human_review") or {}).get("stored_label")
        if label is not None and label not in ACCEPTED_STORED_LABELS:
            errors.append(f"invalid_stored_label:{label}")
        if day.get("closeout_eligible") is not (
            (day.get("scorecard_eligibility") or {}).get("eligible")
        ):
            errors.append(
                f"scorecard_parity:{day.get('snapshot_date_utc')}"
            )
        if label in {"EVENT", "NONE"} and (day.get("human_review") or {}).get(
            "automatic"
        ) is not False:
            if day.get("closeout_eligible") is True:
                errors.append("automatic_event_none_became_eligible")
        op_status = day.get("operational_dataset_status") or {}
        if op_status.get("is_eligibility_gate") is not False:
            errors.append("operational_dataset_status_promoted_to_gate")
        close_at = parse_utc(day.get("target_day_close_utc"))
        if (
            evaluation_as_of
            and close_at
            and evaluation_as_of >= close_at
            and day.get("flow_state") == "DAY_NOT_CLOSED"
        ):
            errors.append(
                f"stale_day_not_closed:{day.get('snapshot_date_utc')}"
            )
    if errors:
        raise ValueError("El artefacto incumple su contrato: " + ", ".join(errors))



def build_queue(
    archive: dict[str, Any],
    contract: dict[str, Any],
    *,
    evaluation_as_of: datetime,
    schema_sha256: str | None = None,
    archive_path: str = "site/data/validation/shadow_runs.json",
    contract_path: str = "config/v08_closeout_contract.json",
    schema_path: str = "config/shadow_review_queue.schema.v1.json",
) -> dict[str, Any]:
    if evaluation_as_of.tzinfo is None:
        raise ValueError("evaluation_as_of requiere zona horaria explícita")
    evaluation_as_of = evaluation_as_of.astimezone(timezone.utc)

    contract_view = contract_projection(contract)
    pilots = [str(value) for value in contract_view["pilot_zone_ids"] if str(value)]
    if not pilots:
        raise ValueError("El contrato no define pilot_zone_ids")
    minimum_pairs_value = normalize_number(
        contract_view.get("minimum_mature_pairs_per_pilot")
    )
    if not isinstance(minimum_pairs_value, (int, float)) or minimum_pairs_value < 0:
        raise ValueError("El contrato no define minimum_mature_pairs_per_pilot válido")
    minimum_pairs = int(minimum_pairs_value)
    acceptance_rules = contract_view.get("acceptance_rules") or {}
    accepted_closeout_labels = {
        str(value)
        for value in (contract_view.get("accepted_outcome_labels") or [])
        if str(value)
    }
    capture_contract = contract_view.get("snapshot_capture") or {}
    earliest_capture_lead_minutes = int(
        normalize_number(
            capture_contract.get("earliest_eligible_capture_lead_minutes")
        )
        or 720
    )
    latest_capture_delay_minutes = int(
        normalize_number(
            capture_contract.get("latest_eligible_capture_delay_minutes")
        )
        or 120
    )

    inconsistencies: list[dict[str, Any]] = []
    records_raw = archive.get("records")
    if not isinstance(records_raw, list):
        add_inconsistency(
            inconsistencies,
            "RECORDS_NOT_ARRAY",
            "El campo records no es una lista.",
            evidence=type(records_raw).__name__,
        )
        records: list[dict[str, Any]] = []
    else:
        records = [row if isinstance(row, dict) else {} for row in records_raw]
        for index, row in enumerate(records_raw):
            if not isinstance(row, dict):
                add_inconsistency(
                    inconsistencies,
                    "RECORD_NOT_OBJECT",
                    "Existe un registro que no es un objeto JSON.",
                    evidence={"index": index, "type": type(row).__name__},
                )

    declared_record_count = normalize_number(archive.get("record_count"))
    actual_record_count = len(records)
    if declared_record_count != actual_record_count:
        add_inconsistency(
            inconsistencies,
            "RECORD_COUNT_MISMATCH",
            "record_count no coincide con el número real de registros.",
            evidence={
                "declared": declared_record_count,
                "actual": actual_record_count,
            },
        )

    dates = [row.get("snapshot_date_utc") for row in records]
    duplicate_dates = sorted(
        str(value) for value, count in Counter(dates).items() if count > 1
    )
    for duplicate in duplicate_dates:
        add_inconsistency(
            inconsistencies,
            "DUPLICATE_SNAPSHOT_DATE",
            "La fecha objetivo aparece más de una vez.",
            snapshot_date_utc=duplicate,
        )
    comparable_dates = [str(value) for value in dates if value is not None]
    if comparable_dates != sorted(comparable_dates):
        add_inconsistency(
            inconsistencies,
            "SNAPSHOT_DATES_NOT_SORTED",
            "Los registros no están ordenados por fecha UTC.",
            evidence=comparable_dates,
        )

    days = [
        build_day(
            record,
            evaluation_as_of=evaluation_as_of,
            pilots=pilots,
            minimum_pairs=minimum_pairs,
            accepted_closeout_labels=accepted_closeout_labels,
            earliest_capture_lead_minutes=earliest_capture_lead_minutes,
            latest_capture_delay_minutes=latest_capture_delay_minutes,
            inconsistencies=inconsistencies,
        )
        for record in records
    ]

    label_counts = Counter()
    review_state_counts = Counter()
    flow_state_counts = Counter()
    for day in days:
        label = (day.get("human_review") or {}).get("stored_label")
        label_counts[label if label in ACCEPTED_STORED_LABELS else "PENDING"] += 1
        review_state_counts[(day.get("human_review") or {}).get("state") or "UNKNOWN"] += 1
        flow_state_counts[day.get("flow_state") or "UNKNOWN"] += 1

    closeout_days = [day for day in days if day.get("closeout_eligible") is True]
    closeout_labels = Counter(
        (day.get("human_review") or {}).get("stored_label") for day in closeout_days
    )
    source_view = source_projection(archive, pilots)
    last_chain = next(
        (
            (row.get("integrity") or {}).get("chain_sha256")
            for row in reversed(records)
            if (row.get("integrity") or {}).get("chain_sha256")
        ),
        None,
    )
    future_transitions = sorted(
        close_at
        for close_at in (
            day_close_utc(str(row.get("snapshot_date_utc"))) for row in records
        )
        if close_at and close_at > evaluation_as_of
    )
    next_transition = future_transitions[0] if future_transitions else None

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": utc_iso(evaluation_as_of),
        "evaluation_as_of_utc": utc_iso(evaluation_as_of),
        "freshness": {
            "status_at_generation": "CURRENT",
            "basis": "SOURCE_UPDATE_OR_UTC_DAY_CLOSE",
            "next_transition_at_utc": utc_iso(next_transition)
            if next_transition
            else None,
            "refresh_required_at_generation": False,
        },
        "status": "CONSISTENT" if not inconsistencies else "INCONSISTENCIES_DETECTED",
        "source": {
            "archive_path": archive_path,
            "archive_version": archive.get("version"),
            "archive_updated_at": archive.get("updated_at"),
            "archive_record_count_declared": declared_record_count,
            "archive_record_count_actual": actual_record_count,
            "archive_contract_projection_sha256": canonical_sha256(source_view),
            "archive_last_integrity_chain_sha256": last_chain,
            "closeout_contract_path": contract_path,
            "closeout_contract_projection_sha256": canonical_sha256(contract_view),
            "schema_path": schema_path,
            "schema_sha256": schema_sha256,
            "methodology": "CANONICAL_ARCHIVE_PLUS_VERSIONED_CLOSEOUT_CONTRACT_AND_SCORECARD_PARITY",
        },
        "guards": {
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "automatic_event_none_classification_enabled": False,
            "missing_evidence_interpretation": "UNKNOWN_OR_UNCERTAIN",
            "operational_dataset_status_is_gate": False,
            "stale_is_gate": False,
            "stored_human_label_is_authoritative": True,
        },
        "contract": {
            "flow_states": list(FLOW_STATES),
            "pilot_zone_ids": pilots,
            "minimum_mature_pairs_per_pilot": minimum_pairs,
            "accepted_closeout_labels": list(
                contract_view.get("accepted_outcome_labels") or []
            ),
            "snapshot_capture": {
                "earliest_eligible_capture_lead_minutes": earliest_capture_lead_minutes,
                "latest_eligible_capture_delay_minutes": latest_capture_delay_minutes,
            },
            "acceptance_rules": acceptance_rules,
        },
        "summary": {
            "record_count_declared": declared_record_count,
            "record_count_actual": actual_record_count,
            "label_counts": {
                "EVENT": label_counts.get("EVENT", 0),
                "NONE": label_counts.get("NONE", 0),
                "UNCERTAIN": label_counts.get("UNCERTAIN", 0),
                "PENDING": label_counts.get("PENDING", 0),
            },
            "review_state_counts": {
                "REVIEWED": review_state_counts.get("REVIEWED", 0),
                "PENDING": review_state_counts.get("PENDING", 0),
                "UNKNOWN": review_state_counts.get("UNKNOWN", 0),
            },
            "flow_state_counts": {
                state: flow_state_counts.get(state, 0) for state in FLOW_STATES
            },
            "closeout_eligible_total": len(closeout_days),
            "closeout_eligible_event": closeout_labels.get("EVENT", 0),
            "closeout_eligible_none": closeout_labels.get("NONE", 0),
            "source_counts_toward_closeout_true": sum(
                1
                for day in days
                if (day.get("human_review") or {}).get("counts_toward_closeout")
                is True
            ),
            "inconsistency_count": len(inconsistencies),
        },
        "inconsistencies": inconsistencies,
        "days": days,
    }
    validate_artifact_contract(artifact)
    return artifact


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def build_from_paths(
    *,
    archive_path: Path,
    contract_path: Path,
    schema_path: Path,
    output_path: Path,
    evaluation_as_of: datetime,
) -> dict[str, Any]:
    archive = load_json(archive_path)
    contract = load_json(contract_path)
    if not schema_path.exists():
        raise ValueError(f"No existe el schema versionado: {schema_path}")
    return build_queue(
        archive,
        contract,
        evaluation_as_of=evaluation_as_of,
        schema_sha256=file_sha256(schema_path),
        archive_path=str(archive_path.relative_to(ROOT))
        if archive_path.is_relative_to(ROOT)
        else str(archive_path),
        contract_path=str(contract_path.relative_to(ROOT))
        if contract_path.is_relative_to(ROOT)
        else str(contract_path),
        schema_path=str(schema_path.relative_to(ROOT))
        if schema_path.is_relative_to(ROOT)
        else str(schema_path),
    )


def material_evaluation_time(
    archive: dict[str, Any], wall_clock_now: datetime
) -> datetime:
    if wall_clock_now.tzinfo is None:
        raise ValueError("wall_clock_now requiere zona horaria explícita")
    wall_clock_now = wall_clock_now.astimezone(timezone.utc)
    candidates: list[datetime] = []
    source_updated = parse_utc(archive.get("updated_at"))
    if source_updated and source_updated <= wall_clock_now:
        candidates.append(source_updated)
    for record in archive.get("records") or []:
        close_at = day_close_utc(str((record or {}).get("snapshot_date_utc")))
        if close_at and close_at <= wall_clock_now:
            candidates.append(close_at)
    if candidates:
        return max(candidates)
    return datetime.combine(
        wall_clock_now.date(), time.min, tzinfo=timezone.utc
    )


def resolve_evaluation_time(
    explicit: str | None,
    *,
    archive_path: Path,
    wall_clock_now: datetime | None = None,
) -> datetime:
    if explicit:
        parsed = parse_utc(explicit)
        if parsed is None:
            raise ValueError("--as-of requiere ISO-8601 con zona horaria")
        return parsed
    archive = load_json(archive_path)
    return material_evaluation_time(
        archive, wall_clock_now or datetime.now(timezone.utc)
    )



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Construye la cola canónica de revisión humana en sombra."
    )
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--as-of",
        help="Instante ISO-8601 con zona horaria para evaluar cierre de jornadas.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Comprueba que el artefacto versionado coincide; no escribe.",
    )
    args = parser.parse_args()

    try:
        evaluation_as_of = resolve_evaluation_time(
            args.as_of,
            archive_path=args.archive,
        )
        artifact = build_from_paths(
            archive_path=args.archive,
            contract_path=args.contract,
            schema_path=args.schema,
            output_path=args.output,
            evaluation_as_of=evaluation_as_of,
        )
        if args.check:
            if not args.output.exists():
                raise ValueError(f"No existe el artefacto para comprobar: {args.output}")
            current = load_json(args.output)
            if current != artifact:
                raise ValueError(
                    "shadow_review_queue.json no coincide con sus fuentes canónicas; "
                    "ejecute scripts/build_shadow_review_queue.py"
                )
            action = "CHECK_OK"
        else:
            atomic_write_json(args.output, artifact)
            action = "WRITTEN"
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "status": action,
                "output": str(args.output),
                "evaluation_as_of_utc": artifact["evaluation_as_of_utc"],
                "next_transition_at_utc": (artifact.get("freshness") or {}).get(
                    "next_transition_at_utc"
                ),
                "record_count": artifact["summary"]["record_count_actual"],
                "label_counts": artifact["summary"]["label_counts"],
                "closeout_eligible_total": artifact["summary"][
                    "closeout_eligible_total"
                ],
                "inconsistency_count": artifact["summary"][
                    "inconsistency_count"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
