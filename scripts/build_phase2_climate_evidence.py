#!/usr/bin/env python3
"""Build the Phase-2 Climate Evidence and Normalization Layer (RESEARCH_ONLY / TEST_ONLY).

This module normalizes provenance, temporal windows, completeness and source
semantics. It does NOT classify physical plausibility, infer activation
thresholds, transfer v0.8 pilot observations into Phase-2 candidates, or
produce operational decisions.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_2.json"
CATALOG_PATH = ROOT / "site/data/phase2/catalog.json"
CLIMATE_MATRIX_PATH = ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"
EVENT_REANALYSIS_PATH = ROOT / "site/data/phase2/event_reanalysis.json"
EVENT_INTAKE_DIR = ROOT / "site/data/validation/phase2_event_intake"
IMERG_LATE_HISTORY_PATH = ROOT / "site/data/forecast/imerg_verification_history.json"
GOES_ARCHIVE_PATH = ROOT / "site/data/calibration/goes19_rrqpe_archive.json"
GEOS_HISTORICAL_DAILY_PATH = ROOT / "site/data/forecast/historical_daily.json"
OUT_PATH = ROOT / "site/data/phase2/climate_evidence_normalized_v0_1.json"

RAINFALL_WINDOWS = ("1h", "3h", "6h", "12h", "24h", "48h", "72h", "7d")
EVENT_WINDOWS = ("3h", "6h", "24h")


class EvidenceNormalizationError(ValueError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def source_count(payload, key):
    value = payload.get(key) or []
    return len(value) if isinstance(value, list) else 0


def build_source_registry(event_reanalysis, imerg_late, goes_archive, geos_daily):
    return [
        {
            "source_id": "IMERG_EARLY_PHASE2_EVENT_REANALYSIS",
            "path": "site/data/phase2/event_reanalysis.json",
            "source_kind": "OBSERVATION_REANALYSIS",
            "record_count": source_count(event_reanalysis, "items"),
            "temporal_resolution": "30_MIN",
            "spatial_scope": "EVENT_TARGET_ONLY",
            "supports_windows": list(EVENT_WINDOWS),
            "phase2_candidate_use": "EXACT_TARGET_ZONE_ID_AND_COMPLETE_WINDOW_ONLY",
            "cross_zone_transfer_allowed": False,
            "forecast_as_observation": False,
            "precipitation_values_archived": True,
            "note": (
                "Only complete event windows with an exact registered target_zone_id may become "
                "candidate-linked evidence. Partial windows remain insufficient evidence."
            ),
        },
        {
            "source_id": "IMERG_LATE_V08_SCIENTIFIC_HISTORY",
            "path": "site/data/forecast/imerg_verification_history.json",
            "source_kind": "OBSERVATION_DAILY",
            "record_count": source_count(imerg_late, "observations"),
            "temporal_resolution": "DAILY",
            "spatial_scope": "V08_PILOT_CONTRACTS_ONLY",
            "supports_windows": ["24h", "72h", "7d"],
            "phase2_candidate_use": "FORBIDDEN_WITHOUT_NEW_EXACT_SPATIAL_CONTRACT",
            "cross_zone_transfer_allowed": False,
            "forecast_as_observation": False,
            "precipitation_values_archived": True,
            "note": (
                "The durable IMERG Late ledger is scientifically useful but belongs to the three "
                "v0.8 pilot sampling contracts. It is not silently transferred to Phase-2."
            ),
        },
        {
            "source_id": "GOES19_RRQPE_AVAILABILITY_ARCHIVE",
            "path": "site/data/calibration/goes19_rrqpe_archive.json",
            "source_kind": "SOURCE_AVAILABILITY_METADATA",
            "record_count": source_count(goes_archive, "records"),
            "temporal_resolution": "SCAN_METADATA_ONLY",
            "spatial_scope": "V08_SHADOW_PROBE",
            "supports_windows": [],
            "phase2_candidate_use": "NOT_YET_NORMALIZABLE",
            "cross_zone_transfer_allowed": False,
            "forecast_as_observation": False,
            "precipitation_values_archived": False,
            "note": (
                "The committed archive proves source availability and freshness but does not preserve "
                "candidate-level precipitation values. Availability must never be interpreted as rain."
            ),
        },
        {
            "source_id": "GEOS_CF_V08_HISTORICAL_DAILY",
            "path": "site/data/forecast/historical_daily.json",
            "source_kind": "FORECAST",
            "record_count": source_count(geos_daily, "records"),
            "temporal_resolution": "DAILY_FORECAST_AGGREGATE",
            "spatial_scope": "V08_PILOT_CONTRACTS_ONLY",
            "supports_windows": ["24h"],
            "phase2_candidate_use": "REFERENCE_ONLY_UNTIL_EXACT_PHASE2_FORECAST_CONTRACT",
            "cross_zone_transfer_allowed": False,
            "forecast_as_observation": False,
            "precipitation_values_archived": True,
            "note": (
                "GEOS-CF is forecast evidence, not observed rainfall. It may be paired with observation "
                "evidence for forecast verification but cannot be normalized as an observation."
            ),
        },
    ]


def load_event_target_map():
    mapping = {}
    if not EVENT_INTAKE_DIR.is_dir():
        return mapping
    for path in sorted(EVENT_INTAKE_DIR.glob("*.json")):
        row = load_json(path)
        event_id = row.get("event_id")
        if event_id:
            mapping[event_id] = row.get("target_zone_id")
    return mapping


def empty_window(window_id):
    return {
        "window_id": window_id,
        "evidence_status": "INSUFFICIENT_EVIDENCE",
        "accumulated_mm": None,
        "coverage_pct": None,
        "complete": False,
        "source_refs": [],
        "note": "No exact, complete candidate-linked observation is available for this assessment context.",
    }


def normalize_event_window(window_id, raw_window, event_id):
    if not isinstance(raw_window, dict):
        return empty_window(window_id)
    complete = raw_window.get("continuous") is True and raw_window.get("accum_mm") is not None
    if complete:
        value = float(raw_window["accum_mm"])
        if value < 0:
            raise EvidenceNormalizationError(f"{event_id}/{window_id}: negative precipitation")
        return {
            "window_id": window_id,
            "evidence_status": "HISTORICAL_EVIDENCE_ONLY",
            "accumulated_mm": value,
            "coverage_pct": float(raw_window.get("coverage_pct", 100.0)),
            "complete": True,
            "source_refs": [
                f"site/data/phase2/event_reanalysis.json#event_id={event_id}:{window_id}"
            ],
            "note": "Complete historical event reanalysis window; non-operational and non-decisional.",
        }
    return {
        "window_id": window_id,
        "evidence_status": "INSUFFICIENT_EVIDENCE",
        "accumulated_mm": None,
        "coverage_pct": raw_window.get("coverage_pct"),
        "complete": False,
        "source_refs": [
            f"site/data/phase2/event_reanalysis.json#event_id={event_id}:{window_id}"
        ],
        "note": (
            "Incomplete event observation window. Partial accumulation is intentionally not normalized "
            "as usable rainfall; missing data is UNKNOWN, never zero or low risk."
        ),
    }


def normalize_event_evidence(event_reanalysis, candidate_ids):
    target_map = load_event_target_map()
    output = []
    for item in event_reanalysis.get("items") or []:
        event_id = item.get("event_id")
        target_zone_id = target_map.get(event_id)
        exact_link = target_zone_id in candidate_ids if target_zone_id else False
        windows = {
            window_id: normalize_event_window(
                window_id, (item.get("windows") or {}).get(window_id), event_id
            )
            for window_id in EVENT_WINDOWS
        }
        output.append({
            "event_id": event_id,
            "target_zone_id": target_zone_id if exact_link else None,
            "linkage_status": (
                "EXACT_REGISTERED_PHASE2_CANDIDATE"
                if exact_link
                else "UNLINKED_TO_REGISTERED_PHASE2_CANDIDATE"
            ),
            "source_status": item.get("status"),
            "research_role": item.get("research_role"),
            "occurrence_time_utc": item.get("occurrence_time_utc"),
            "windows": windows,
            "can_populate_candidate_context": bool(
                exact_link and any(window["complete"] for window in windows.values())
            ),
            "operational_use": False,
            "threshold_inference_allowed": False,
        })
    return output


def complete_daily_accumulations(observations, end_date):
    """Sum only complete consecutive daily observations; never infer a wetness state."""
    if isinstance(end_date, str):
        end = date.fromisoformat(end_date)
    else:
        end = end_date
    by_date = {}
    duplicates = set()
    for row in observations or []:
        day = date.fromisoformat(str(row["date"]))
        if day in by_date:
            duplicates.add(day)
        by_date[day] = row.get("rain_mm")
    for day in duplicates:
        by_date[day] = None

    def total(days):
        required = [end - timedelta(days=offset) for offset in range(days)]
        values = []
        for day in required:
            value = by_date.get(day)
            if value is None:
                return None
            number = float(value)
            if number < 0:
                raise EvidenceNormalizationError(f"negative daily precipitation on {day}")
            values.append(number)
        return round(sum(values), 6)

    return {"24h": total(1), "72h": total(3), "7d": total(7)}


def build_candidate_records(inventory, event_evidence):
    linked_by_candidate = {}
    for event in event_evidence:
        cid = event.get("target_zone_id")
        if cid:
            linked_by_candidate.setdefault(cid, []).append(event["event_id"])

    records = []
    for candidate in inventory.get("candidates") or []:
        cid = candidate["candidate_id"]
        records.append({
            "candidate_id": cid,
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "activation_gate": "BLOCKED",
            "assessment_context": {
                "status": "NO_ASSESSMENT_CONTEXT",
                "as_of_utc": None,
                "note": (
                    "v0.1 normalizes evidence contracts but does not fabricate a current or live "
                    "assessment context for Phase-2 candidates."
                ),
            },
            "rainfall_windows": {window: empty_window(window) for window in RAINFALL_WINDOWS},
            "antecedent_accumulations": {
                "24h_mm": None,
                "72h_mm": None,
                "7d_mm": None,
                "state": "UNKNOWN",
                "state_methodology_status": "UNRESOLVED_THRESHOLDS",
                "evidence_status": "INSUFFICIENT_EVIDENCE",
            },
            "climatology": {
                "status": "NOT_AVAILABLE_FOR_PHASE2_CANDIDATE",
                "percentile": None,
                "anomaly_mm": None,
                "baseline_ref": None,
                "note": (
                    "No cited candidate-specific climatological baseline is committed; percentiles "
                    "and anomalies are not synthesized from the short v0.8 pilot ledgers."
                ),
            },
            "linked_historical_event_evidence_ids": linked_by_candidate.get(cid, []),
        })
    return records


def build_layer():
    inventory = load_json(INVENTORY_PATH)
    catalog = load_json(CATALOG_PATH)
    climate_matrix = load_json(CLIMATE_MATRIX_PATH)
    event_reanalysis = load_json(EVENT_REANALYSIS_PATH)
    imerg_late = load_json(IMERG_LATE_HISTORY_PATH)
    goes_archive = load_json(GOES_ARCHIVE_PATH)
    geos_daily = load_json(GEOS_HISTORICAL_DAILY_PATH)

    candidates = inventory.get("candidates") or []
    if len(candidates) != 18:
        raise EvidenceNormalizationError(f"expected 18 Phase-2 candidates, found {len(candidates)}")
    candidate_ids = {candidate["candidate_id"] for candidate in candidates}

    event_evidence = normalize_event_evidence(event_reanalysis, candidate_ids)
    candidate_records = build_candidate_records(inventory, event_evidence)
    exact_linked_events = [row for row in event_evidence if row["target_zone_id"]]
    complete_linked_windows = sum(
        window["complete"]
        for row in exact_linked_events
        for window in row["windows"].values()
    )

    return {
        "version": "phase2-climate-evidence-normalization-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "decision_thresholds": None,
        "activation_gate": "BLOCKED",
        "decision_use": "TEST_ONLY",
        "relationship_to_climate_matrix": {
            "matrix_path": "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json",
            "writes_or_changes_plausibility": False,
            "writes_or_changes_classification_method": False,
            "required_current_classification_method_status": "NOT_YET_CALIBRATED",
            "matrix_candidate_count": len(climate_matrix.get("records") or []),
        },
        "guardrails": {
            "missing_data_is_unknown_never_zero": True,
            "cross_zone_transfer_forbidden": True,
            "daily_data_cannot_create_subdaily_windows": True,
            "forecast_is_not_observation": True,
            "source_availability_is_not_precipitation": True,
            "candidate_linkage_requires_exact_id": True,
            "climatological_percentiles_require_cited_baseline": True,
            "antecedent_state_thresholds_unresolved": True,
        },
        "normalization_contract": {
            "time_reference": "UTC",
            "precipitation_accumulation_unit": "mm",
            "precipitation_rate_unit": "mm/h",
            "supported_candidate_windows": list(RAINFALL_WINDOWS),
            "complete_interval_policy": "ALL_REQUIRED_INTERVALS_PRESENT",
            "partial_interval_policy": "PRESERVE_COVERAGE_BUT_NORMALIZED_ACCUMULATION_IS_NULL",
            "assessment_context_policy": "EXPLICIT_CONTEXT_REQUIRED_BEFORE_CANDIDATE_WINDOW_POPULATION",
        },
        "source_registry": build_source_registry(
            event_reanalysis, imerg_late, goes_archive, geos_daily
        ),
        "phase2_event_evidence": event_evidence,
        "candidate_evidence": candidate_records,
        "summary": {
            "candidate_count": len(candidate_records),
            "source_contract_count": 4,
            "phase2_event_record_count": len(event_evidence),
            "exact_candidate_linked_event_count": len(exact_linked_events),
            "complete_exact_candidate_event_window_count": complete_linked_windows,
            "candidates_with_current_normalized_rainfall": sum(
                any(
                    window["accumulated_mm"] is not None
                    for window in record["rainfall_windows"].values()
                )
                for record in candidate_records
            ),
            "classification_outputs_created": 0,
            "operational_activations": 0,
            "authoritative_phase2_registered_candidates": (catalog.get("summary") or {}).get(
                "registered_candidates"
            ),
        },
    }


def generate(write=True):
    layer = build_layer()
    if write:
        write_json(OUT_PATH, layer)
    return layer


def main():
    layer = generate(write=True)
    print(json.dumps(layer["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
