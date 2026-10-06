#!/usr/bin/env python3
"""Fail-closed structural check of the national inventory completeness audit.

The audit file is a research backlog. This checker proves that it stays one:
no row may carry a geometry, an outlet, a parent basin, a threshold, a map
promotion or an event flag that its own evidence does not support.

Standard library only. Exit code 0 = consistent, 1 = violations (listed).

    python scripts/validate_phase2_national_inventory_audit.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"

GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}
STATES = {"IDENTITY_ONLY", "GEOMETRY_PENDING", "GEOMETRY_REPRODUCIBLE", "OUTLET_PENDING", "EVENT_EVIDENCE", "MAP_ELIGIBLE"}
PRIMARY_STATES = {"IDENTITY_ONLY", "GEOMETRY_PENDING", "GEOMETRY_REPRODUCIBLE", "EVENT_EVIDENCE"}
EVIDENCE_TYPES = {"IDENTITY", "CRITICAL_POINT", "EVENT", "WORKS", "FAJA", "GEOMETRY"}
PRESENCE = {
    "MAIN_REGISTERED_UNIT", "MAIN_NAME_CONTEXT_ONLY", "MAIN_NAMED_AS_QUEBRADA_WITH_CORRIDOR_CONTEXT",
    "MAIN_LABEL_MENTION_UNCONFIRMED", "BRANCH_OR_OPEN_PR_ONLY", "BRANCH_LABEL_MENTION_UNCONFIRMED",
    "NOT_FOUND_IN_REPO", "NOT_EVALUATED_NO_DISCRIMINATING_CONTEXT",
}
PRIORITIES = {"EXISTING", "P1", "P2", "P3", "P4"}
# Keys that would mean a geometry, outlet or hydraulic value slipped into a row.
FORBIDDEN_ROW_KEYS = {
    "geometry", "coordinates", "outlet", "outlet_point", "confluence_point", "lon", "lat", "longitude", "latitude",
    "area_km2", "length_km", "discharge", "caudal", "capacity", "threshold", "thresholds", "travel_time",
    "alert_level", "risk_class", "activation_state", "evidence_state",
}


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_keys(value)


def validate(doc: dict) -> list[str]:
    errors: list[str] = []
    for key, expected in GUARDS.items():
        if key not in doc or doc[key] != expected:
            errors.append(f"guard {key} must be {expected!r}")
    if doc.get("status") != "RESEARCH_ONLY_INVENTORY_BACKLOG_PENDING_INDEPENDENT_QA":
        errors.append("status must stay RESEARCH_ONLY_INVENTORY_BACKLOG_PENDING_INDEPENDENT_QA")
    rules = doc.get("strict_rules", {})
    for key, value in rules.items():
        if value not in (False, 0):
            errors.append(f"strict_rules.{key} must be false/0")
    if doc.get("map_updates") != {
        "new_geometries_published": 0, "new_nodes_published": 0,
        "new_local_units_published": 0, "new_event_ledger_entries": 0,
    }:
        errors.append("map_updates must be all zero")

    sources = doc.get("sources", {})
    eligible = {
        sid for sid, src in sources.items()
        if src["source_class"].startswith("PRIMARY_INSTITUTIONAL") and src["access"] != "NOT_READ_FILE_TOO_LARGE"
    } - {"IGP-IT-001-2023"}
    rows = doc.get("candidates", [])
    ids = [row.get("inventory_id") for row in rows]
    for dup, count in Counter(ids).items():
        if count > 1:
            errors.append(f"duplicate inventory_id {dup}")
    known = set(ids)

    for row in rows:
        rid = row.get("inventory_id")
        where = f"candidate {rid}"
        if row.get("map_eligible") is not False:
            errors.append(f"{where}: map_eligible must be false")
        if row.get("parent_basin_or_system") is not None:
            errors.append(f"{where}: parent basin must not be asserted by this audit")
        bad = FORBIDDEN_ROW_KEYS & set(walk_keys(row))
        if bad:
            errors.append(f"{where}: forbidden keys {sorted(bad)}")
        if not row.get("documentary_name"):
            errors.append(f"{where}: documentary_name missing")
        evidence = row.get("evidence") or []
        if not evidence:
            errors.append(f"{where}: at least one evidence item is required")
        types = set()
        for item in evidence:
            if item.get("evidence_type") not in EVIDENCE_TYPES:
                errors.append(f"{where}: unknown evidence_type {item.get('evidence_type')}")
            if item.get("source_id") not in sources:
                errors.append(f"{where}: unknown source_id {item.get('source_id')}")
            types.add(item.get("evidence_type"))
            point = item.get("source_reference_point")
            if point is not None and set(point) != {"easting_m", "northing_m"}:
                errors.append(f"{where}: source_reference_point may only carry the two source-printed numbers")
            if item.get("evidence_type") != "EVENT" and "event_dates" in item:
                errors.append(f"{where}: only EVENT evidence may carry event_dates")
        if sorted(types) != row.get("evidence_types"):
            errors.append(f"{where}: evidence_types out of sync with evidence")
        for variant in row.get("name_variants_observed", []):
            if variant.get("source_id") not in sources:
                errors.append(f"{where}: variant with unknown source")

        flags = row.get("state_flags") or []
        primary = row.get("suggested_state")
        if primary not in PRIMARY_STATES or not set(flags) <= STATES:
            errors.append(f"{where}: state outside the allowed vocabulary")
        if "MAP_ELIGIBLE" in flags or primary == "MAP_ELIGIBLE":
            errors.append(f"{where}: this audit may not assign MAP_ELIGIBLE")
        counted = sorted({
            date for item in evidence
            if item.get("evidence_type") == "EVENT" and item.get("source_id") in eligible
            for date in item.get("event_dates", [])
        })
        if counted != row.get("documented_event_dates_primary_institutional"):
            errors.append(f"{where}: institutional event dates out of sync with evidence")
        if ("EVENT_EVIDENCE" in flags) != bool(counted):
            errors.append(f"{where}: EVENT_EVIDENCE must follow from a dated primary institutional EVENT item only")
        geometry = row.get("reproducible_geometry", {})
        presence = (row.get("irfen_presence") or {}).get("status")
        if presence not in PRESENCE:
            errors.append(f"{where}: unknown irfen_presence status {presence}")
        if geometry.get("exists"):
            if presence != "MAIN_REGISTERED_UNIT" or "GEOMETRY_REPRODUCIBLE" not in flags:
                errors.append(f"{where}: reproducible geometry is allowed only for units already registered in main")
        elif "GEOMETRY_REPRODUCIBLE" in flags:
            errors.append(f"{where}: GEOMETRY_REPRODUCIBLE without reproducible geometry")
        if "GEOMETRY_PENDING" in flags:
            lead = "FAJA" in types or "FROZEN" in (geometry.get("legacy_or_branch") or "")
            if not lead:
                errors.append(f"{where}: GEOMETRY_PENDING needs a faja resolution or a frozen legacy geometry lead")
        if flags == ["IDENTITY_ONLY"] and primary != "IDENTITY_ONLY":
            errors.append(f"{where}: primary state inconsistent with flags")
        if "IDENTITY_ONLY" in flags and len(flags) > 1:
            errors.append(f"{where}: IDENTITY_ONLY cannot be combined with other flags")
        if types <= {"CRITICAL_POINT", "WORKS", "IDENTITY"} and flags != ["IDENTITY_ONLY"] and "FROZEN" not in (geometry.get("legacy_or_branch") or ""):
            errors.append(f"{where}: critical-point, works or identity evidence alone cannot raise the state")
        if row.get("priority") not in PRIORITIES:
            errors.append(f"{where}: unknown priority")
        if (row.get("priority") == "EXISTING") != (presence == "MAIN_REGISTERED_UNIT"):
            errors.append(f"{where}: EXISTING priority must match MAIN_REGISTERED_UNIT presence")

    aliases = doc.get("aliases_pending_adjudication", {})
    for group in aliases.get("curated_relationships", []) + aliases.get("cross_department_homonyms_noted", []) + aliases.get("same_label_groups_not_merged", []):
        for rid in group.get("inventory_ids", []):
            if rid not in known:
                errors.append(f"alias group references unknown inventory_id {rid}")
    for group in aliases.get("curated_relationships", []):
        if "MERGED" in group.get("status", "") and "NOT" not in group.get("status", ""):
            errors.append("alias groups may not be merged by this audit")
    for view, members in doc.get("derived_views", {}).items():
        unknown = set(members) - known
        if unknown:
            errors.append(f"derived view {view} references unknown ids {sorted(unknown)[:3]}")

    summary = doc.get("summary", {})
    if summary.get("candidate_rows") != len(rows):
        errors.append("summary.candidate_rows out of sync")
    if summary.get("by_suggested_state") != dict(Counter(row["suggested_state"] for row in rows)):
        errors.append("summary.by_suggested_state out of sync")
    if summary.get("by_priority") != dict(Counter(row["priority"] for row in rows)):
        errors.append("summary.by_priority out of sync")
    for key in ("map_eligible_rows", "new_geometries", "new_outlets", "new_events_written_to_any_event_ledger"):
        if summary.get(key) != 0:
            errors.append(f"summary.{key} must be 0")
    return errors


def main() -> int:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    errors = validate(doc)
    if errors:
        print(f"FAIL: {len(errors)} violation(s) in {PATH.relative_to(ROOT)}")
        for line in errors[:200]:
            print("  -", line)
        return 1
    rows = doc["candidates"]
    print(f"OK: {len(rows)} inventory rows, 0 map-eligible, 0 new geometries, 0 new outlets, guards closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
