#!/usr/bin/env python3
"""Fail-closed check of the Tumbes La Capitana / Hualaca / Higuerón identity record.

The record may only say what the archived official text says. This checker
proves it, offline:

* the guards stay closed and nothing is publishable on the map;
* every cited source is an archived file whose SHA-256 matches the capture
  manifest, and the record was built against that exact manifest;
* every quote is a verbatim (whitespace-normalised) substring of the archived
  text page it cites;
* no geometry, outlet, receiver, parent basin, hydraulic value or alias merge
  is asserted, and the 2017 period-level rows are not turned into dated events;
* every unit is named by the quotes it cites (a unit cannot exist without an
  archived source that prints its name);
* no relation between two Tumbes channel names is asserted: different labels
  are not proof of hydraulically independent channels, so same_channel and
  hydraulically_independent stay UNRESOLVED;
* the archive lives outside site/, the directory GitHub Pages publishes.

Standard library only. Exit code 0 = consistent, 1 = violations (listed).

    python scripts/validate_phase2_tumbes_capitana_hualaca_higueron_identity.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "config/phase2_tumbes_capitana_hualaca_higueron_identity_v0_1.json"
MANIFEST = ROOT / "data/phase2/source_archive/tumbes_capitana_hualaca_higueron/archive_manifest_v0_1.json"

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
# Outcomes allowed for a relation. Only an out-of-department homonym may be kept
# apart on the strength of the sources' own locations; every Tumbes relation stays open.
DECISIONS = {"UNRESOLVED", "DIFFERENT_FEATURE_TYPES_RELATION_UNRESOLVED", "DIFFERENT_DEPARTMENTS_NOT_MERGED"}
REQUIRED_DECISIONS = {"HUALACA_VS_HIGUERON", "HUALACA_VS_HUALTACAL", "HIGUERON_VS_HUALTACAL", "CAPITANA_VS_HIGUERON",
                      "CAPITANA_VS_HUALACA", "HIGUERON_ONE_OR_SEVERAL_CHANNELS"}
REQUIRED_UNITS = {"tumbes_san_jacinto_quebrada_la_capitana", "tumbes_quebrada_higueron_label_group",
                  "tumbes_san_jacinto_quebrada_hualaca"}
PUBLIC_DIR = "site/"
# Keys that would mean a coordinate, geometry or hydraulic value slipped in.
FORBIDDEN_KEYS = {
    "geometry", "coordinates", "lat", "lon", "latitude", "longitude", "easting_m", "northing_m", "outlet_point",
    "confluence_point", "area_km2", "discharge", "caudal", "capacity", "threshold", "thresholds", "travel_time",
    "alert_level", "risk_class", "activation_state",
}
NULL_UNIT_FIELDS = ("reproducible_geometry_ref", "outlet_coordinate", "exact_confluence_coordinate", "parent_basin_or_system",
                    "travel_time_tau", "discharge_q_i", "collector_capacity", "collector_overflow_evidence")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


def quote_ids_in(node) -> set[str]:
    found = set()
    for _, key, value in walk(node):
        if key in ("quote_ids", "location_quote_ids") and isinstance(value, list):
            found.update(value)
        elif key == "quote_id" and isinstance(value, str):
            found.add(value)
    return found


def validate(record: dict, manifest: dict, manifest_sha256: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for key, expected in GUARDS.items():
        if record.get(key, "<missing>") != expected:
            errors.append(f"guard {key} must be {expected!r}")
        if manifest.get(key, "<missing>") != expected:
            errors.append(f"manifest guard {key} must be {expected!r}")
    if record.get("status") != "RESEARCH_ONLY_DOCUMENTARY_IDENTITY_RECORD_PENDING_INDEPENDENT_QA":
        errors.append("status must stay RESEARCH_ONLY_DOCUMENTARY_IDENTITY_RECORD_PENDING_INDEPENDENT_QA")
    if manifest.get("map_publishable") is not False:
        errors.append("manifest map_publishable must be false")
    if any(value != 0 for value in record.get("map_updates", {"missing": 1}).values()):
        errors.append("map_updates must all be zero")

    prov = record.get("provenance", {})
    if prov.get("archive_manifest_sha256") != manifest_sha256:
        errors.append("record was not built against the committed archive manifest (archive_manifest_sha256 differs)")
    if prov.get("archive_seeds_sha256") != manifest.get("seeds_sha256"):
        errors.append("archive_seeds_sha256 differs from the manifest")

    by_doc = {r["document_id"]: r for r in manifest.get("records", [])}
    sources = record.get("sources", {})
    pages_cache: dict[str, list[str]] = {}
    for sid, src in sources.items():
        rec = by_doc.get(src.get("archive_document_id"))
        if not rec or rec.get("status") != "ARCHIVED":
            errors.append(f"source {sid}: not an ARCHIVED manifest record")
            continue
        for key in ("raw_path", "sha256", "text_path", "text_sha256"):
            if src.get(key) != rec.get(key):
                errors.append(f"source {sid}: {key} differs from the manifest")
        if not SHA256_RE.match(str(src.get("sha256", ""))):
            errors.append(f"source {sid}: sha256 must be 64 lowercase hex characters")
        raw, text = root / rec["raw_path"], root / rec["text_path"]
        if not raw.is_file() or sha256_file(raw) != rec["sha256"]:
            errors.append(f"source {sid}: archived bytes missing or SHA-256 mismatch")
        if not text.is_file() or sha256_file(text) != rec["text_sha256"]:
            errors.append(f"source {sid}: text extraction missing or SHA-256 mismatch")
            continue
        pages_cache[sid] = json.loads(text.read_text(encoding="utf-8"))["pages"]

    quotes = record.get("quotes", {})
    for qid, q in quotes.items():
        pages = pages_cache.get(q.get("source_id"))
        if pages is None:
            errors.append(f"quote {qid}: unknown or unverifiable source {q.get('source_id')}")
            continue
        index = q.get("text_page_index")
        if not isinstance(index, int) or not 1 <= index <= len(pages):
            errors.append(f"quote {qid}: page index out of range")
            continue
        if not norm(q.get("text", "")) or norm(q["text"]) not in norm(pages[index - 1]):
            errors.append(f"quote {qid}: not a verbatim substring of the archived text page {index}")
    for qid in sorted(quote_ids_in({k: v for k, v in record.items() if k != "quotes"}) - set(quotes)):
        errors.append(f"reference to unknown quote {qid}")
    for path, key, value in walk(record):
        if key == "source_id" and isinstance(value, str) and value not in sources:
            errors.append(f"{path}: unknown source_id {value}")
        if key in FORBIDDEN_KEYS:
            errors.append(f"{path}: forbidden key {key}")
        if key == "map_publishable" and value is not False:
            errors.append(f"{path}: map_publishable must be false")
        if key in ("adjudicated_alias", "equivalence_asserted") and value is not False:
            errors.append(f"{path}: {key} must be false")
        if key == "same_channel_as_other_attestations" and value != "UNRESOLVED":
            errors.append(f"{path}: attestations may not be merged")

    decisions = {d.get("id"): d for d in record.get("identity_decisions", [])}
    for missing in sorted(REQUIRED_DECISIONS - set(decisions)):
        errors.append(f"identity decision {missing} missing")
    for did, decision in decisions.items():
        outcome = decision.get("decision")
        if outcome not in DECISIONS:
            errors.append(f"identity decision {did}: outcome outside the allowed vocabulary")
        if not decision.get("quote_ids"):
            errors.append(f"identity decision {did}: needs at least one quote")
        if decision.get("equivalence_asserted") is not False:
            errors.append(f"identity decision {did}: equivalence_asserted must be false")
        if outcome != "DIFFERENT_DEPARTMENTS_NOT_MERGED":
            # Different labels are not proof of independent channels, and nothing proves they are one channel.
            for key in ("same_channel", "hydraulically_independent"):
                if decision.get(key) != "UNRESOLVED":
                    errors.append(f"identity decision {did}: {key} must stay UNRESOLVED without reproducible geometry")
            if decision.get("distinctness_asserted") is not False:
                errors.append(f"identity decision {did}: distinctness_asserted must be false")

    for path, key, value in walk(record):
        if key in ("relation_to_hualaca", "relation_to_quebrada_higueron", "relation_to_quebrada_la_capitana", "number_of_channels") \
                and not str(value).startswith("UNRESOLVED"):
            errors.append(f"{path}: {key} must stay UNRESOLVED")
    for sid, src in sources.items():
        for key in ("raw_path", "text_path"):
            if str(src.get(key, "")).startswith(PUBLIC_DIR):
                errors.append(f"source {sid}: {key} lies inside site/, which GitHub Pages publishes")
    for rec in manifest.get("records", []):
        for key in ("raw_path", "text_path"):
            if str(rec.get(key, "")).startswith(PUBLIC_DIR):
                errors.append(f"manifest record {rec.get('document_id')}: {key} lies inside site/")

    units = {u.get("id"): u for u in record.get("units", [])}
    for missing in sorted(REQUIRED_UNITS - set(units)):
        errors.append(f"unit {missing} missing")
    for unit in record.get("units", []):
        uid = unit.get("id")
        token = fold(unit.get("name_token", ""))
        label_quotes = unit.get("label_quote_ids") or []
        if not token or token not in fold(unit.get("documentary_label", "")):
            errors.append(f"unit {uid}: name_token must be part of the documentary label")
        elif not label_quotes or not all(token in fold(quotes.get(q, {}).get("text", "")) for q in label_quotes):
            errors.append(f"unit {uid}: every label quote must print the unit's name (no unit without an archived source naming it)")
        for listing in unit.get("critical_point_listings", []):
            if listing.get("usable_as_event") is not False or listing.get("usable_as_footprint") is not False:
                errors.append(f"unit {uid}: a critical-point listing is not an event or a footprint")
        if unit.get("department") != "Tumbes":
            errors.append(f"unit {uid}: only Tumbes units belong in this record")
        if unit.get("geometry_status") != "MISSING" or unit.get("outlet_status") != "MISSING":
            errors.append(f"unit {uid}: geometry and outlet must stay MISSING (no reproducible source geometry)")
        if unit.get("receiver_relation") != "UNKNOWN_NOT_ASSUMED":
            errors.append(f"unit {uid}: receiver relation may not be assumed")
        for field in NULL_UNIT_FIELDS:
            if unit.get(field, "<missing>") is not None:
                errors.append(f"unit {uid}: {field} must be null")
        for event in unit.get("documented_events", []):
            if event.get("date") is not None or event.get("date_precision") != "PERIOD_ONLY_NO_DAY":
                errors.append(f"unit {uid}: {event.get('event_ref')} is period-level in the source and may not carry a date")
            if event.get("usable_as_dated_event") is not False or event.get("usable_as_footprint") is not False:
                errors.append(f"unit {uid}: {event.get('event_ref')} cannot be a dated event or a footprint")
            if "A6764-CUADRO-3.2-TITLE" not in event.get("quote_ids", []):
                errors.append(f"unit {uid}: {event.get('event_ref')} must cite the Cuadro 3.2 title that sets its period")
        if unit.get("unverified_event_leads"):
            errors.append(f"unit {uid}: unarchived event leads are not recorded here")
    return errors


def main() -> int:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors = validate(record, manifest, sha256_file(MANIFEST))
    if errors:
        print("FAIL:")
        for error in errors:
            print("  -", error)
        return 1
    print(f"OK: {len(record['sources'])} archived sources, {len(record['quotes'])} verbatim quotes, "
          f"{len(record['units'])} units with geometry/outlet MISSING, map_publishable=false, guards closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
