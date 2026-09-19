#!/usr/bin/env python3
"""Validate the Phase-2 Climate Evidence and Normalization Layer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/phase2/climate_evidence_normalized_v0_1.json"
SCHEMA = ROOT / "config/phase2_climate_evidence_normalization.schema.json"
INVENTORY = ROOT / "config/phase2_candidate_inventory_v0_2.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
CLIMATE_MATRIX = ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"
EVENT_REANALYSIS = ROOT / "site/data/phase2/event_reanalysis.json"
IMERG_LATE = ROOT / "site/data/forecast/imerg_verification_history.json"
GOES = ROOT / "site/data/calibration/goes19_rrqpe_archive.json"
GEOS = ROOT / "site/data/forecast/historical_daily.json"

ERRORS = []


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"cannot read {path.relative_to(ROOT)}: {exc}")
        return None


def check_schema(layer, schema):
    try:
        import jsonschema
    except ImportError:
        return
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(layer), key=str):
        ERRORS.append(
            "schema: " + error.message + " at " + "/".join(str(x) for x in error.absolute_path)
        )


def source_by_id(layer):
    return {row.get("source_id"): row for row in layer.get("source_registry") or []}


def check_authoritative_phase2(layer, inventory, catalog, climate_matrix):
    candidates = inventory.get("candidates") or []
    zones = catalog.get("zones") or []
    if len(candidates) != 18 or len(zones) != 18:
        ERRORS.append(
            f"authoritative Phase-2 candidate count changed: inventory={len(candidates)} catalog={len(zones)}"
        )
    if (catalog.get("summary") or {}).get("contracts_approved") != 0:
        ERRORS.append("authoritative contracts_approved must remain 0")
    if (catalog.get("summary") or {}).get("operational_candidates") != 0:
        ERRORS.append("authoritative operational_candidates must remain 0")
    if any(zone.get("activation_gate") != "BLOCKED" for zone in zones):
        ERRORS.append("all authoritative Phase-2 activation gates must remain BLOCKED")
    if any((zone.get("promotion_gate") or {}).get("promotion_gate_met") is True for zone in zones):
        ERRORS.append("no authoritative Phase-2 promotion gate may be met")
    if catalog.get("deployment_status") != "RESEARCH_ONLY":
        ERRORS.append("authoritative catalog deployment_status changed")
    if catalog.get("production_use") is not False or catalog.get("production_ready") is not False:
        ERRORS.append("authoritative production flags changed")
    if (catalog.get("guardrails") or {}).get("alerts_disabled") is not True:
        ERRORS.append("authoritative alerts_disabled guardrail changed")

    matrix_records = climate_matrix.get("records") or []
    if len(matrix_records) != 18:
        ERRORS.append("Claude D matrix candidate count must remain 18")
    for record in matrix_records:
        assessment = record.get("physical_plausibility_assessment") or {}
        if assessment.get("classification_method_status") != "NOT_YET_CALIBRATED":
            ERRORS.append(
                f"{record.get('candidate_id')}: Claude D classification method unexpectedly changed"
            )
        if assessment.get("category") != "INSUFFICIENT_EVIDENCE":
            ERRORS.append(
                f"{record.get('candidate_id')}: Claude E must not create a plausibility category"
            )
        if assessment.get("physical_response_plausibility_score") is not None:
            ERRORS.append(
                f"{record.get('candidate_id')}: Claude E must not create a plausibility score"
            )

    relation = layer.get("relationship_to_climate_matrix") or {}
    if relation.get("writes_or_changes_plausibility") is not False:
        ERRORS.append("evidence layer must not write or change plausibility")
    if relation.get("writes_or_changes_classification_method") is not False:
        ERRORS.append("evidence layer must not change classification method")


def check_source_contracts(layer, event_reanalysis, imerg_late, goes, geos):
    registry = source_by_id(layer)
    expected = {
        "IMERG_EARLY_PHASE2_EVENT_REANALYSIS": len(event_reanalysis.get("items") or []),
        "IMERG_LATE_V08_SCIENTIFIC_HISTORY": len(imerg_late.get("observations") or []),
        "GOES19_RRQPE_AVAILABILITY_ARCHIVE": len(goes.get("records") or []),
        "GEOS_CF_V08_HISTORICAL_DAILY": len(geos.get("records") or []),
    }
    if set(registry) != set(expected):
        ERRORS.append(f"source registry mismatch: {sorted(registry)}")
    for source_id, count in expected.items():
        row = registry.get(source_id) or {}
        if row.get("record_count") != count:
            ERRORS.append(f"{source_id}: record_count {row.get('record_count')} != {count}")
        if row.get("cross_zone_transfer_allowed") is not False:
            ERRORS.append(f"{source_id}: cross-zone transfer must be false")
        if row.get("forecast_as_observation") is not False:
            ERRORS.append(f"{source_id}: forecast_as_observation must be false")

    imerg_late_row = registry.get("IMERG_LATE_V08_SCIENTIFIC_HISTORY") or {}
    if (
        imerg_late_row.get("phase2_candidate_use")
        != "FORBIDDEN_WITHOUT_NEW_EXACT_SPATIAL_CONTRACT"
    ):
        ERRORS.append("IMERG Late v0.8 evidence must not silently transfer to Phase-2")

    goes_row = registry.get("GOES19_RRQPE_AVAILABILITY_ARCHIVE") or {}
    if goes_row.get("precipitation_values_archived") is not False:
        ERRORS.append(
            "GOES archive currently contains availability metadata, not normalized precipitation values"
        )

    geos_row = registry.get("GEOS_CF_V08_HISTORICAL_DAILY") or {}
    if geos_row.get("source_kind") != "FORECAST":
        ERRORS.append("GEOS-CF must remain forecast evidence, never observation")


def check_candidate_records(layer, inventory):
    expected_ids = {row["candidate_id"] for row in inventory.get("candidates") or []}
    records = layer.get("candidate_evidence") or []
    actual_ids = {row.get("candidate_id") for row in records}
    if len(records) != 18 or actual_ids != expected_ids:
        ERRORS.append("candidate_evidence must match the 18 registered Phase-2 candidates exactly")
    for row in records:
        cid = row.get("candidate_id")
        if row.get("deployment_status") != "RESEARCH_ONLY":
            ERRORS.append(f"{cid}: must remain RESEARCH_ONLY")
        if row.get("production_use") is not False or row.get("production_ready") is not False:
            ERRORS.append(f"{cid}: production flags must remain false")
        if row.get("activation_gate") != "BLOCKED":
            ERRORS.append(f"{cid}: activation gate must remain BLOCKED")
        if (row.get("assessment_context") or {}).get("status") != "NO_ASSESSMENT_CONTEXT":
            ERRORS.append(f"{cid}: v0.1 must not invent a live assessment context")
        for window_id, window in (row.get("rainfall_windows") or {}).items():
            if window.get("accumulated_mm") is not None:
                ERRORS.append(
                    f"{cid}/{window_id}: current candidate rainfall must remain unpopulated without explicit context"
                )
            if window.get("evidence_status") != "INSUFFICIENT_EVIDENCE":
                ERRORS.append(
                    f"{cid}/{window_id}: missing candidate evidence must remain INSUFFICIENT_EVIDENCE"
                )
        antecedent = row.get("antecedent_accumulations") or {}
        if antecedent.get("state") != "UNKNOWN":
            ERRORS.append(f"{cid}: antecedent state must remain UNKNOWN")
        if antecedent.get("state_methodology_status") != "UNRESOLVED_THRESHOLDS":
            ERRORS.append(f"{cid}: antecedent state thresholds must remain unresolved")
        climatology = row.get("climatology") or {}
        if climatology.get("percentile") is not None or climatology.get("anomaly_mm") is not None:
            ERRORS.append(f"{cid}: climatology cannot be fabricated")


def check_event_evidence(layer, event_reanalysis, inventory):
    raw_by_id = {row.get("event_id"): row for row in event_reanalysis.get("items") or []}
    candidate_ids = {row["candidate_id"] for row in inventory.get("candidates") or []}
    normalized = layer.get("phase2_event_evidence") or []
    if len(normalized) != len(raw_by_id):
        ERRORS.append("normalized event evidence count does not match event_reanalysis")
    for event in normalized:
        eid = event.get("event_id")
        raw = raw_by_id.get(eid)
        if raw is None:
            ERRORS.append(f"unknown normalized event: {eid}")
            continue
        target = event.get("target_zone_id")
        if target is not None and target not in candidate_ids:
            ERRORS.append(f"{eid}: non-registered target_zone_id was normalized")
        for window_id, norm in (event.get("windows") or {}).items():
            raw_window = (raw.get("windows") or {}).get(window_id) or {}
            raw_complete = (
                raw_window.get("continuous") is True
                and raw_window.get("accum_mm") is not None
            )
            if norm.get("complete") != raw_complete:
                ERRORS.append(f"{eid}/{window_id}: completeness mismatch")
            if not raw_complete and norm.get("accumulated_mm") is not None:
                ERRORS.append(
                    f"{eid}/{window_id}: partial accumulation must not be normalized"
                )


def walk_forbidden(node, path="root"):
    forbidden = {
        "physical_plausibility_assessment",
        "physical_response_plausibility_score",
        "promotion_gate_met",
        "risk_score",
        "activation_score",
        "alert_score",
    }
    if isinstance(node, dict):
        for key, value in node.items():
            if key in forbidden:
                ERRORS.append(
                    f"forbidden decision or classification key in evidence layer: {path}.{key}"
                )
            walk_forbidden(value, path + "." + key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            walk_forbidden(value, f"{path}[{index}]")


def _first_difference(left, right, path="root"):
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys {sorted(set(left) ^ set(right))}"
        for key in sorted(left):
            diff = _first_difference(left[key], right[key], path + "." + str(key))
            if diff:
                return diff
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: list length {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            diff = _first_difference(a, b, f"{path}[{index}]")
            if diff:
                return diff
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def check_determinism(layer):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_phase2_climate_evidence as builder

    fresh = builder.generate(write=False)
    left = dict(layer)
    right = dict(fresh)
    left.pop("generated_at", None)
    right.pop("generated_at", None)
    if left != right:
        ERRORS.append(
            "committed normalized evidence does not match deterministic regeneration: "
            + (_first_difference(left, right) or "unknown difference")
        )


def main():
    ERRORS.clear()
    layer = load(OUT)
    schema = load(SCHEMA)
    inventory = load(INVENTORY)
    catalog = load(CATALOG)
    climate_matrix = load(CLIMATE_MATRIX)
    event_reanalysis = load(EVENT_REANALYSIS)
    imerg_late = load(IMERG_LATE)
    goes = load(GOES)
    geos = load(GEOS)

    if any(
        value is None
        for value in (
            layer,
            schema,
            inventory,
            catalog,
            climate_matrix,
            event_reanalysis,
            imerg_late,
            goes,
            geos,
        )
    ):
        for error in ERRORS:
            print("ERROR:", error)
        return 1

    check_schema(layer, schema)
    check_authoritative_phase2(layer, inventory, catalog, climate_matrix)
    check_source_contracts(layer, event_reanalysis, imerg_late, goes, geos)
    check_candidate_records(layer, inventory)
    check_event_evidence(layer, event_reanalysis, inventory)
    walk_forbidden(layer)
    check_determinism(layer)

    for error in ERRORS:
        print("ERROR:", error)
    if ERRORS:
        print(f"validate_phase2_climate_evidence: FAILED with {len(ERRORS)} error(s).")
        return 1
    print("validate_phase2_climate_evidence: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
