#!/usr/bin/env python3
"""Fail-closed validator for the Pisco/Ica La Polvareda / La Pólvora / Higos Monte documentary identity registry.

Checks the registry against its archived sources (SHA-256 and verbatim quotes) and against the
three rows it adds to the national master inventory. Standard library only; no network.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "config/phase2_pisco_ica_polvareda_polvora_higos_monte_identity_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
MANIFEST = ROOT / "data/phase2/source_archive/pisco_ica_polvareda/archive_manifest_v0_1.json"
PUBLIC_ROOT = ROOT / "site"
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
}
REQUESTED = {
    "Quebrada La Polvareda": "ica_humay_la_polvareda",
    "Quebrada La Pólvora": "ica_district_unknown_la_polvora",
    "Quebrada Higos Monte": "ica_district_unknown_higos_monte",
}
CLASS = {"identity_state": "IDENTITY_ONLY", "geometry_state": "GEOMETRY_PENDING", "outlet_state": "OUTLET_PENDING"}
FORBIDDEN_KEYS = {"geometry", "coordinates", "outlet", "outlet_point", "confluence_point", "lon", "lat", "longitude", "latitude",
                  "area_km2", "length_km", "discharge", "caudal", "capacity", "threshold", "thresholds", "travel_time",
                  "alert_level", "risk_class", "activation_state", "event_date", "event_dates"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_keys(value)


def validate(reg: dict, audit: dict, manifest: dict | None = None) -> list[str]:
    errors: list[str] = []
    manifest = manifest if manifest is not None else json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if reg.get(key) != value:
            errors.append(f"guard {key} must be {value!r}")
    if reg.get("map_publishable") is not False:
        errors.append("map_publishable must be false")
    if reg.get("map_updates") and any(v != 0 for v in reg["map_updates"].values()):
        errors.append("map_updates must be all zero")

    # sources: bytes and text layers archived outside site/ and identical to the manifest
    records = {r["document_id"]: r for r in manifest.get("records", [])}
    sources = reg.get("sources", {})
    for sid, src in sources.items():
        record = records.get(src.get("archive_document_id"))
        if not record or record.get("status") != "ARCHIVED":
            errors.append(f"source {sid}: not archived in the manifest")
            continue
        for key in ("sha256", "raw_path", "text_path", "text_sha256", "bytes"):
            if src.get(key) != record.get(key):
                errors.append(f"source {sid}: {key} differs from the archive manifest")
        for key, digest in (("raw_path", "sha256"), ("text_path", "text_sha256")):
            path = ROOT / str(src.get(key, ""))
            if path.resolve().is_relative_to(PUBLIC_ROOT.resolve()):
                errors.append(f"source {sid}: {key} inside site/ (published by GitHub Pages)")
            elif not path.is_file() or sha256_file(path) != src.get(digest):
                errors.append(f"source {sid}: {key} missing or SHA-256 mismatch")
    for sid, item in reg.get("sources_not_read", {}).items():
        if item.get("status") != "NOT_READ":
            errors.append(f"{sid}: a source that was not captured must stay NOT_READ")
        if sid in sources or sid in audit.get("sources", {}):
            errors.append(f"{sid}: an unread source may not be cited")

    # quotes: verbatim on the cited page of the archived text layer
    quotes = reg.get("quotes", {})
    cache: dict[str, dict] = {}
    for qid, q in quotes.items():
        src = sources.get(q.get("source_id"))
        if not src:
            errors.append(f"quote {qid}: unknown or unread source {q.get('source_id')}")
            continue
        path = ROOT / src["text_path"]
        if not path.is_file():
            continue
        text = cache.setdefault(src["text_path"], json.loads(path.read_text(encoding="utf-8")))
        layer = text.get(q.get("text_layer")) or []
        page = q.get("page")
        if not isinstance(page, int) or not 1 <= page <= len(layer):
            errors.append(f"quote {qid}: page {page} outside the archived text layer")
        elif norm(q.get("text", "")) not in norm(layer[page - 1]):
            errors.append(f"quote {qid}: not verbatim on page {page} of {src['archive_document_id']}")

    # candidates
    cands = reg.get("candidates", [])
    if sorted(c.get("requested_name") for c in cands) != sorted(REQUESTED):
        errors.append("candidates must be exactly the three requested names")
    maturity = set(reg.get("maturity_vocabulary", {}))
    rows = {r["inventory_id"]: r for r in audit.get("candidates", [])}
    for c in cands:
        name = c.get("requested_name")
        where = f"candidate {name}"
        if REQUESTED.get(name) != c.get("inventory_id"):
            errors.append(f"{where}: inventory_id must be {REQUESTED.get(name)}")
        bad = FORBIDDEN_KEYS & set(walk_keys(c))
        if bad:
            errors.append(f"{where}: forbidden keys {sorted(bad)}")
        if c.get("classification") != CLASS:
            errors.append(f"{where}: classification must stay {CLASS}")
        if c.get("map_publishable") is not False or c.get("map_eligible") is not False:
            errors.append(f"{where}: map_publishable and map_eligible must be false")
        if not str(c.get("geometry_status", "")).startswith("GEOMETRY_PENDING") or not str(c.get("outlet_status", "")).startswith("OUTLET_PENDING"):
            errors.append(f"{where}: geometry and outlet must stay pending")
        if c.get("events_attributed") != []:
            errors.append(f"{where}: no event may be attributed from a feasibility study, plan or law")
        for work in c.get("works_named_in_sources", []):
            if work.get("execution") != "NOT_ASSERTED" or not str(work.get("status", "")).startswith("PROPOSED"):
                errors.append(f"{where}: works from a design study must stay PROPOSED with execution NOT_ASSERTED")
        hyd = c.get("hydrologic_context_in_source", {})
        if hyd.get("adopted_as_parent_basin") is not False or hyd.get("adopted_as_outlet") is not False:
            errors.append(f"{where}: source hydrologic context may not be adopted as parent basin or outlet")
        if c.get("maturity") not in maturity:
            errors.append(f"{where}: maturity outside the vocabulary")
        basis = c.get("administrative_basis", {})
        if (c.get("district") or c.get("province")) and not basis.get("quote_id"):
            errors.append(f"{where}: district/province need a quote that states them")
        if basis.get("quote_id"):
            q = quotes.get(basis["quote_id"], {})
            for part in (c.get("district"), c.get("province")):
                if part and fold(part) not in fold(q.get("text", "")):
                    errors.append(f"{where}: '{part}' is not stated in quote {basis['quote_id']}")
        ids = c.get("identity_quote_ids") or []
        if not ids:
            errors.append(f"{where}: at least one identity quote is required")
        for qid in ids:
            if fold(c.get("documentary_name", "")) not in fold(quotes.get(qid, {}).get("text", "")):
                errors.append(f"{where}: identity quote {qid} does not contain '{c.get('documentary_name')}'")
        for qid in ids + (c.get("context_quote_ids") or []) + (hyd.get("quote_ids") or []):
            if qid not in quotes:
                errors.append(f"{where}: unknown quote {qid}")

        row = rows.get(c.get("inventory_id"))
        if row is None:
            errors.append(f"{where}: row missing from the national audit")
            continue
        if row.get("suggested_state") != "IDENTITY_ONLY" or row.get("state_flags") != ["IDENTITY_ONLY"]:
            errors.append(f"{where}: audit row must stay IDENTITY_ONLY")
        if row.get("map_eligible") is not False or row.get("parent_basin_or_system") is not None:
            errors.append(f"{where}: audit row may not be map-eligible or carry a parent basin")
        if row.get("reproducible_geometry") != {"exists": False} or row.get("reproducible_outlet_or_confluence") != {"exists": False}:
            errors.append(f"{where}: audit row may not carry geometry or outlet")
        if row.get("evidence_types") != ["IDENTITY"] or row.get("event_lead_dates_unverified") or row.get("verified_event_dates"):
            errors.append(f"{where}: audit row evidence must be IDENTITY only, with no event dates")
        if (row.get("district"), row.get("province"), row.get("department")) != (c.get("district"), c.get("province"), "Ica"):
            errors.append(f"{where}: audit row location differs from the registry")
        for item in row.get("evidence", []):
            q = quotes.get(item.get("quote_id"))
            if not q or q.get("source_id") != item.get("source_id") or q.get("page") != item.get("page"):
                errors.append(f"{where}: audit evidence must cite a registry quote with the same source and page")

    # possible equivalence La Polvareda / La Pólvora stays unresolved, in the registry and in the audit
    pair = {"ica_humay_la_polvareda", "ica_district_unknown_la_polvora"}
    eq = [e for e in reg.get("possible_equivalences", []) if set(e.get("inventory_ids", [])) == pair]
    if len(eq) != 1 or eq[0].get("status") != "UNRESOLVED":
        errors.append("La Polvareda / La Pólvora equivalence must be recorded once as UNRESOLVED")
    groups = [g for g in audit.get("aliases_pending_adjudication", {}).get("curated_relationships", []) if pair <= set(g.get("inventory_ids", []))]
    if len(groups) != 1 or groups[0].get("status") != "PENDING_ADJUDICATION" or groups[0].get("equivalence") != "UNRESOLVED":
        errors.append("audit alias group La Polvareda / La Pólvora must be PENDING_ADJUDICATION with equivalence UNRESOLVED")
    for rel in reg.get("other_relations_recorded_not_adopted", []):
        if rel.get("status") not in {"UNRESOLVED", "NOT_STATED_IN_SOURCE"}:
            errors.append(f"relation {rel.get('labels')}: may not be resolved by this registry")
    return errors


def main() -> int:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    errors = validate(reg, audit)
    if errors:
        print(f"FAIL: {len(errors)} violation(s)")
        for line in errors:
            print("  -", line)
        return 1
    print(f"OK: {len(reg['candidates'])} documentary identities, {len(reg['quotes'])} verbatim quotes on archived bytes, "
          "IDENTITY_ONLY / GEOMETRY_PENDING / OUTLET_PENDING, equivalence UNRESOLVED, map_publishable=false, guards closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
