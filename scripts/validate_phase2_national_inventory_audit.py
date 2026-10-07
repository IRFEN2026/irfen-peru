#!/usr/bin/env python3
"""Fail-closed structural check of the national inventory completeness audit.

The audit file is a research backlog. This checker proves that it stays one:
no row may carry a geometry, an outlet, a parent basin, a threshold, a map
promotion or an event flag that its own evidence does not support.

Event rule: an EVENT item read through automated extraction is only a lead.
It counts as EVENT_EVIDENCE only when the source and the item both carry
``source_text_verified: true`` together with a reproducible verification
record (SHA-256 of the archived bytes, archive locator, date, verifier, and
the item's own locator). Otherwise the row carries EVENT_LEAD_UNVERIFIED.

Standard library only. Exit code 0 = consistent, 1 = violations (listed).

    python scripts/validate_phase2_national_inventory_audit.py
"""
from __future__ import annotations

import json
import re
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
STATES = {
    "IDENTITY_ONLY", "GEOMETRY_PENDING", "GEOMETRY_REPRODUCIBLE", "OUTLET_PENDING",
    "EVENT_LEAD_UNVERIFIED", "EVENT_EVIDENCE", "MAP_ELIGIBLE",
}
PRIMARY_STATES = {"IDENTITY_ONLY", "GEOMETRY_PENDING", "GEOMETRY_REPRODUCIBLE", "EVENT_LEAD_UNVERIFIED", "EVENT_EVIDENCE"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Sources whose per-unit event dates may never count, verified or not.
NEVER_EVENT_ELIGIBLE = {"IGP-IT-001-2023"}
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


def nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def source_verification_errors(sid: str, src: dict) -> list[str]:
    """A source is verified only with a reproducible record of the archived bytes."""
    errors = []
    flag = src.get("source_text_verified")
    record = src.get("verification_record")
    if not isinstance(flag, bool):
        errors.append(f"source {sid}: source_text_verified must be an explicit boolean")
        return errors
    if not flag:
        if record is not None:
            errors.append(f"source {sid}: verification_record must be null while source_text_verified is false")
        return errors
    if not isinstance(record, dict):
        errors.append(f"source {sid}: source_text_verified=true needs a verification_record")
        return errors
    if not SHA256_RE.match(str(record.get("archived_sha256", ""))):
        errors.append(f"source {sid}: verification_record.archived_sha256 must be 64 lowercase hex characters")
    if not nonempty(record.get("archive_locator")):
        errors.append(f"source {sid}: verification_record.archive_locator is required")
    if not DATE_RE.match(str(record.get("verified_on", ""))):
        errors.append(f"source {sid}: verification_record.verified_on must be YYYY-MM-DD")
    if not nonempty(record.get("verified_by")):
        errors.append(f"source {sid}: verification_record.verified_by is required")
    if src.get("access") == "NOT_READ_FILE_TOO_LARGE":
        errors.append(f"source {sid}: a source that was not read cannot be marked verified")
    return errors


def event_item_is_verified(item: dict, sources: dict, eligible: set[str]) -> bool:
    """True only for an eligible EVENT item verified at both source and item level."""
    if item.get("evidence_type") != "EVENT" or item.get("source_id") not in eligible:
        return False
    if item.get("source_text_verified") is not True:
        return False
    if sources.get(item["source_id"], {}).get("source_text_verified") is not True:
        return False
    record = item.get("verification")
    return isinstance(record, dict) and nonempty(record.get("locator")) and nonempty(record.get("verified_statement"))


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
        if str(src.get("source_class", "")).startswith("PRIMARY_INSTITUTIONAL") and src.get("access") != "NOT_READ_FILE_TOO_LARGE"
    } - NEVER_EVENT_ELIGIBLE
    for sid, src in sources.items():
        errors.extend(source_verification_errors(sid, src))
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
            if item.get("evidence_type") != "EVENT":
                for key in ("event_dates", "source_text_verified", "verification", "event_lead_eligible"):
                    if key in item:
                        errors.append(f"{where}: only EVENT evidence may carry {key}")
                continue
            if item.get("event_lead_eligible") is not (item.get("source_id") in eligible):
                errors.append(f"{where}: event_lead_eligible out of sync with the source class")
            flag = item.get("source_text_verified")
            if not isinstance(flag, bool):
                errors.append(f"{where}: EVENT item needs an explicit boolean source_text_verified")
            elif flag and not event_item_is_verified(item, sources, eligible):
                errors.append(
                    f"{where}: EVENT item marked verified without a verified eligible source "
                    "and an item-level locator + verified_statement"
                )
            elif not flag and item.get("verification") is not None:
                errors.append(f"{where}: verification must be null while source_text_verified is false")
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
        dated = [item for item in evidence if item.get("evidence_type") == "EVENT" and item.get("source_id") in eligible]
        verified = sorted({d for item in dated if event_item_is_verified(item, sources, eligible) for d in item.get("event_dates", [])})
        leads = sorted({d for item in dated if not event_item_is_verified(item, sources, eligible) for d in item.get("event_dates", [])})
        if verified != row.get("verified_event_dates"):
            errors.append(f"{where}: verified_event_dates out of sync with verified EVENT items")
        if leads != row.get("event_lead_dates_unverified"):
            errors.append(f"{where}: event_lead_dates_unverified out of sync with unverified EVENT items")
        if ("EVENT_EVIDENCE" in flags) != bool(verified):
            errors.append(
                f"{where}: EVENT_EVIDENCE is allowed only with an EVENT item whose source text is verified "
                "(source_text_verified=true on source and item, with verification records)"
            )
        if ("EVENT_LEAD_UNVERIFIED" in flags) != bool(leads):
            errors.append(f"{where}: EVENT_LEAD_UNVERIFIED must follow from an unverified dated EVENT item")
        expected_primary = next(
            (state for state in ("GEOMETRY_REPRODUCIBLE", "GEOMETRY_PENDING", "EVENT_EVIDENCE", "EVENT_LEAD_UNVERIFIED") if state in flags),
            "IDENTITY_ONLY",
        )
        if primary != expected_primary:
            errors.append(f"{where}: suggested_state must be {expected_primary} for flags {flags}")
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
    if summary.get("event_evidence_rows") != sum("EVENT_EVIDENCE" in row.get("state_flags", []) for row in rows):
        errors.append("summary.event_evidence_rows out of sync")
    if summary.get("event_lead_unverified_rows") != sum("EVENT_LEAD_UNVERIFIED" in row.get("state_flags", []) for row in rows):
        errors.append("summary.event_lead_unverified_rows out of sync")
    if summary.get("sources_with_verified_text") != sum(src.get("source_text_verified") is True for src in sources.values()):
        errors.append("summary.sources_with_verified_text out of sync")
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
    summary = doc["summary"]
    print(
        f"OK: {len(rows)} inventory rows, 0 map-eligible, 0 new geometries, 0 new outlets, "
        f"{summary['event_evidence_rows']} verified EVENT_EVIDENCE, "
        f"{summary['event_lead_unverified_rows']} EVENT_LEAD_UNVERIFIED, guards closed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
