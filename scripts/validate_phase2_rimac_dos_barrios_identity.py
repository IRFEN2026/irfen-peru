#!/usr/bin/env python3
"""Fail-closed validator for the Quebrada Dos Barrios documentary identity (Rímac corridor).

Dos Barrios may be registered only as IDENTITY_ONLY and only on verifiable evidence: archived bytes whose
SHA-256 matches the manifest, and verbatim, page-cited quotes that contain the label. No geometry,
confluence, outlet or event may follow from it. Standard library only; no network.
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "config/phase2_rimac_dos_barrios_identity_v0_1.json"
RIMAC = ROOT / "config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
MANIFEST = ROOT / "data/phase2/source_archive/rimac_dos_barrios/archive_manifest_v0_1.json"
PUBLIC_ROOT = ROOT / "site"
RID = "lima_district_unknown_dos_barrios"
LABEL = re.compile(r"dos\s+barrios", re.I)
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
}
CLASS = {"identity_state": "IDENTITY_ONLY", "geometry_state": "GEOMETRY_PENDING", "outlet_state": "OUTLET_PENDING",
         "event_state": "EVENT_LEAD_UNVERIFIED"}
A6608_DOC = "ingemmet-a6608-sigrid-401"
A6608_SHA256 = "b710247572a7a83efed53be0f0f565cc4971eb542f43f2881cbefc7bba0b5927"
LEAD_DATE = "2012-04-05"
# Files that hold event ledgers or the published map: the lead may never appear there.
NO_LEAD_PATHS = [ROOT / "config/historical_events.json", ROOT / "site"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_all():
    return tuple(json.loads(p.read_text(encoding="utf-8")) for p in (REG, RIMAC, AUDIT, MANIFEST))


@functools.lru_cache(maxsize=1)
def ledger_or_map_hits() -> tuple[str, ...]:
    """Files under the event ledger or site/ (published map) that mention Dos Barrios; scanned once per process."""
    hits = []
    for path in NO_LEAD_PATHS:
        files = [path] if path.is_file() else (sorted(path.rglob("*")) if path.is_dir() else [])
        for f in files:
            if f.is_file() and f.suffix in {".json", ".geojson", ".js", ".html", ".csv"}:
                if re.search(r"dos\s*barrios|dos_barrios", f.read_text(encoding="utf-8", errors="ignore"), re.I):
                    hits.append(str(f.relative_to(ROOT)))
    return tuple(hits)


def validate(reg: dict, rimac: dict, audit: dict, manifest: dict) -> list[str]:
    errors: list[str] = []
    for key, value in GUARDS.items():
        if reg.get(key) != value:
            errors.append(f"guard {key} must be {value!r}")
    if reg.get("map_publishable") is not False or any(v != 0 for v in reg.get("map_updates", {}).values()):
        errors.append("map_publishable must be false and map_updates all zero")

    # archived sources
    records = {r["document_id"]: r for r in manifest.get("records", [])}
    sources = reg.get("sources", {})
    for sid, src in sources.items():
        record = records.get(src.get("archive_document_id"), {})
        if record.get("status") != "ARCHIVED":
            errors.append(f"source {sid}: not archived in the manifest")
            continue
        for key in ("sha256", "raw_path", "text_path", "text_sha256", "bytes"):
            if src.get(key) != record.get(key):
                errors.append(f"source {sid}: {key} differs from the archive manifest")
        for key, digest in (("raw_path", "sha256"), ("text_path", "text_sha256")):
            path = ROOT / str(src.get(key, ""))
            if path.resolve().is_relative_to(PUBLIC_ROOT.resolve()):
                errors.append(f"source {sid}: {key} inside site/")
            elif not path.is_file() or sha256_file(path) != src.get(digest):
                errors.append(f"source {sid}: {key} missing or SHA-256 mismatch")
        if record.get("acquisition") == "OWNER_SUPPLIED_COPY" and record.get("owner_supplied_copy", {}).get("byte_identity_with_host") != "NOT_VERIFIED_BY_AGENT":
            errors.append(f"source {sid}: an owner-supplied copy may not claim byte identity with the host")

    # quotes verbatim on the archived page
    texts: dict[str, dict] = {}
    quotes = reg.get("quotes", {})

    def page_text(sid: str, page: int) -> str | None:
        src = sources.get(sid)
        if not src or not (ROOT / src["text_path"]).is_file():
            return None
        layer = texts.setdefault(sid, json.loads((ROOT / src["text_path"]).read_text(encoding="utf-8"))).get(src["quote_text_layer"], [])
        return layer[page - 1] if isinstance(page, int) and 1 <= page <= len(layer) else None

    for qid, q in quotes.items():
        text = page_text(q.get("source_id"), q.get("page"))
        if text is None:
            errors.append(f"quote {qid}: source or page not in the archive")
        elif norm(q.get("text", "")) not in norm(text):
            errors.append(f"quote {qid}: not verbatim on page {q.get('page')}")

    # identity basis: verifiable, label-bearing, at least one primary institutional attestation
    cand = reg.get("candidate", {})
    if cand.get("inventory_id") != RID or cand.get("classification") != CLASS:
        errors.append("candidate must be lima_district_unknown_dos_barrios with IDENTITY_ONLY / GEOMETRY_PENDING / OUTLET_PENDING and event_state EVENT_LEAD_UNVERIFIED")
    attestations = cand.get("identity_basis", {}).get("attestations", [])
    primary = 0
    for att in attestations:
        qids = att.get("quote_ids") or []
        if not qids or not all(quotes.get(q, {}).get("source_id") == att.get("source_id") for q in qids):
            errors.append(f"attestation {att.get('source_id')}: quotes must exist and belong to its source")
        if not any(LABEL.search(quotes.get(q, {}).get("text", "")) for q in qids):
            errors.append(f"attestation {att.get('source_id')}: no quote contains 'Dos Barrios'")
        if sources.get(att.get("source_id"), {}).get("source_class") == "PRIMARY_INSTITUTIONAL":
            primary += 1
    if primary < 1:
        errors.append("Dos Barrios needs at least one archived primary institutional attestation")
    if cand.get("district") or cand.get("province"):
        errors.append("district/province are not stated by the sources and may not be filled")
    if cand.get("receiver_relation") != "UNKNOWN_NOT_ASSUMED" or cand.get("exact_confluence") is not None:
        errors.append("no receiver relation or confluence may be derived")
    if cand.get("map_publishable") is not False or cand.get("map_eligible") is not False:
        errors.append("candidate may not be map-publishable")
    if cand.get("events_attributed") != []:
        errors.append("no event may be attributed to Dos Barrios")
    for mention in cand.get("historical_period_mentions", []):
        if mention.get("event_lead_eligible") is not False or mention.get("usable_as_confirmed_unit_event") is not False:
            errors.append("list-level period mentions may not become event leads or unit events")
    # The only event lead: A6608 §5.6, 2012-04-05, authorised by independent QA as EVENT_LEAD_UNVERIFIED and nothing more
    a6608_ids = {sid for sid, src in sources.items() if src.get("archive_document_id") == A6608_DOC}
    leads = cand.get("event_leads", [])
    if len(leads) != 1:
        errors.append("exactly one event lead (A6608, 2012-04-05) may be recorded")
    for lead in leads:
        src = sources.get(lead.get("source_id"), {})
        if lead.get("source_id") not in a6608_ids or src.get("sha256") != A6608_SHA256 or src.get("source_class") != "PRIMARY_INSTITUTIONAL":
            errors.append("the event lead must rest on the archived INGEMMET A6608 (primary institutional, fixed SHA-256)")
        if lead.get("event_date") != LEAD_DATE or lead.get("state") != "EVENT_LEAD_UNVERIFIED" or lead.get("event_lead_eligible") is not True:
            errors.append("the event lead must be EVENT_LEAD_UNVERIFIED for 2012-04-05")
        if lead.get("source_text_verified") is not False or lead.get("verification") is not None:
            errors.append("the event lead must stay source_text_verified=false with no verification record (no EVENT_EVIDENCE)")
        for flag in ("usable_as_confirmed_unit_event", "event_ledger_entry_allowed", "promotion_to_event_evidence_allowed"):
            if lead.get(flag) is not False:
                errors.append(f"the event lead must keep {flag}=false")
        if not lead.get("date_warning") or "2011" not in lead.get("date_warning", ""):
            errors.append("the A6608 cover-date discrepancy (Octubre 2011 vs 05/04/2012) must stay recorded with the lead")
        if not any(re.search(r"05 de abril|5 de abril", quotes.get(q, {}).get("text", ""), re.I) for q in lead.get("quote_ids", [])):
            errors.append("the event lead must cite a quote that states the 5 April date")
    for hit in ledger_or_map_hits():
        errors.append(f"Dos Barrios may not appear in an event ledger or the published map: {hit}")
    relations = reg.get("relations_recorded_not_adopted", [])
    for rel in relations:
        status = str(rel.get("status", ""))
        if any(word in status for word in ("SAME", "EQUIVALEN", "MERGED", "ALIAS_CONFIRMED")):
            errors.append(f"relation {rel.get('labels')}: no channel equivalence may be recorded ({status})")
        for label in ("Pablo Patrón/Dos Amigos", "Mariscal Castilla"):
            if label in rel.get("labels", []) and status != "UNRESOLVED":
                errors.append(f"Dos Barrios / {label} must stay UNRESOLVED")
    # A6608 (primary source): Pablo Patrón is a sector on the fan, and a '/' in a heading is not an equivalence
    a6608 = [sid for sid, src in sources.items() if src.get("archive_document_id") == "ingemmet-a6608-sigrid-401"]
    if len(a6608) != 1 or not any(att.get("source_id") == a6608[0] for att in attestations):
        errors.append("INGEMMET A6608 must be archived and cited as an attestation")
    sector = [rel for rel in relations if "Pablo Patrón (sector)" in rel.get("labels", [])]
    if len(sector) != 1:
        errors.append("the Pablo Patrón sector relation must be recorded once")
    else:
        rel = sector[0]
        if rel.get("channel_equivalence") != "NOT_ASSERTED_BY_SOURCE" or rel.get("status") != "PABLO_PATRON_IS_A_SECTOR_ON_THE_LOWER_FAN_PER_A6608":
            errors.append("Pablo Patrón must stay recorded as a sector, with no channel equivalence")
        texts_rel = " ".join(quotes.get(q, {}).get("text", "") for q in rel.get("quote_ids", []))
        if not re.search(r"(sector|zona) de Pablo Patr[oó]n", texts_rel, re.I):
            errors.append("the Pablo Patrón sector relation must cite a quote naming the 'sector'/'zona' de Pablo Patrón")
        if a6608 and not any(quotes.get(q, {}).get("source_id") == a6608[0] for q in rel.get("quote_ids", [])):
            errors.append("the Pablo Patrón sector relation must rest on A6608 quotes")
    if a6608:
        layer = texts.setdefault(a6608[0], json.loads((ROOT / sources[a6608[0]]["text_path"]).read_text(encoding="utf-8"))).get(sources[a6608[0]]["quote_text_layer"], [])
        if any(re.search(r"dos\s+amigos", page, re.I) for page in layer) and any("Dos Amigos" in str(rel.get("note", "")) and "neither A6608" in str(rel.get("note", "")) for rel in relations):
            errors.append("the registry says 'Dos Amigos' is absent from A6608, but the archived text names it")
    for checked in reg.get("documents_checked_without_the_label", []):
        sid = checked.get("source_id")
        if sid and sid in sources:
            layer = texts.setdefault(sid, json.loads((ROOT / sources[sid]["text_path"]).read_text(encoding="utf-8"))).get(sources[sid]["quote_text_layer"], [])
            if any(LABEL.search(p) for p in layer):
                errors.append(f"{sid}: listed as checked without the label, but it names Dos Barrios")

    # Rímac corridor inventory
    if any(lead.get("requested_name") == "Dos Barrios" for lead in rimac.get("requested_unresolved_name_leads", [])):
        errors.append("Rímac inventory: Dos Barrios may not stay an unresolved lead once registered")
    units = [u for u in rimac.get("units", []) if u.get("id") == RID]
    if len(units) != 1:
        errors.append("Rímac inventory: exactly one Dos Barrios unit required")
    else:
        unit = units[0]
        if unit.get("map_publishable") is not False or unit.get("identity_adjudication") != "DOCUMENTARY_LABEL_ONLY_HYDROLOGIC_DISTINCTNESS_UNRESOLVED":
            errors.append("Rímac unit: documentary label only, not map-publishable")
        for field in ("reproducible_geometry_ref", "outlet_coordinate", "exact_confluence_coordinate", "travel_time_tau",
                      "discharge_q_i", "collector_capacity", "collector_overflow_evidence", "district", "province"):
            if unit.get(field) is not None:
                errors.append(f"Rímac unit: {field} must be null")
        if unit.get("receiver_relation") != "UNKNOWN_NOT_ASSUMED" or unit.get("verified_event_refs"):
            errors.append("Rímac unit: no receiver relation or verified event")
        if any("pablo" in str(v).lower() for v in unit.get("documentary_variants", [])):
            errors.append("Rímac unit: Pablo Patrón may not be recorded as a variant of Dos Barrios")
        if any(lead.get("usable_as_confirmed_unit_event") is not False for lead in unit.get("unverified_event_leads", [])):
            errors.append("Rímac unit: event leads may not be usable as confirmed unit events")
        refs = unit.get("source_refs", [])
        if not refs:
            errors.append("Rímac unit: archived source references required")
        for ref in refs:
            src = sources.get(ref.get("source_id"), {})
            if ref.get("archived_sha256") != src.get("sha256") or not set(ref.get("quote_ids", [])) <= set(quotes):
                errors.append(f"Rímac unit: source_ref {ref.get('source_id')} must carry the archived SHA-256 and registry quotes")
    groups = [g for g in rimac.get("pending_identity_groups", []) if set(g.get("inventory_ids", [])) == {RID, "lima_lurigancho_pablo_patron_dos_amigos"}]
    if len(groups) != 1 or not groups[0].get("status", "").startswith("PENDING"):
        errors.append("Rímac inventory: Dos Barrios / Pablo Patrón-Dos Amigos group must stay pending")

    # national audit row
    rows = [r for r in audit.get("candidates", []) if r.get("inventory_id") == RID]
    if len(rows) != 1:
        errors.append("national audit: exactly one Dos Barrios row required")
    else:
        row = rows[0]
        if (row.get("state_flags") != ["EVENT_LEAD_UNVERIFIED"] or row.get("suggested_state") != "EVENT_LEAD_UNVERIFIED"
                or row.get("map_eligible") is not False or row.get("parent_basin_or_system") is not None):
            errors.append("national audit row: EVENT_LEAD_UNVERIFIED only (never EVENT_EVIDENCE), not map-eligible, no parent basin")
        if row.get("reproducible_geometry") != {"exists": False} or row.get("reproducible_outlet_or_confluence") != {"exists": False}:
            errors.append("national audit row: no geometry or outlet")
        if row.get("evidence_types") != ["EVENT", "IDENTITY"] or row.get("event_lead_dates_unverified") != [LEAD_DATE] or row.get("verified_event_dates"):
            errors.append("national audit row: identity evidence plus the single 2012-04-05 lead; no verified event dates")
        events = [i for i in row.get("evidence", []) if i.get("evidence_type") == "EVENT"]
        if len(events) != 1 or events[0].get("source_id") not in a6608_ids or events[0].get("event_dates") != [LEAD_DATE]:
            errors.append("national audit row: the only EVENT item is the A6608 2012-04-05 lead")
        for item in events:
            if item.get("source_text_verified") is not False or item.get("verification") is not None or item.get("event_lead_eligible") is not True:
                errors.append("national audit row: the EVENT item stays an unverified, eligible lead")
        for sid in a6608_ids:
            if audit.get("sources", {}).get(sid, {}).get("source_text_verified") is not False:
                errors.append("national audit: A6608 source_text_verified must stay false until independent re-reading")
        for item in row.get("evidence", []):
            q = quotes.get(item.get("quote_id"), {})
            if q.get("source_id") != item.get("source_id") or q.get("page") != item.get("page"):
                errors.append("national audit row: evidence must cite a registry quote with the same source and page")
    groups = [g for g in audit.get("aliases_pending_adjudication", {}).get("curated_relationships", []) if RID in g.get("inventory_ids", [])]
    if not groups or any(g.get("status") != "PENDING_ADJUDICATION" or g.get("equivalence") != "UNRESOLVED" for g in groups):
        errors.append("national audit: Dos Barrios alias group must be PENDING_ADJUDICATION / UNRESOLVED")
    return errors


def main() -> int:
    errors = validate(*load_all())
    if errors:
        print(f"FAIL: {len(errors)} violation(s)")
        for line in errors:
            print("  -", line)
        return 1
    reg = json.loads(REG.read_text(encoding="utf-8"))
    print(f"OK: Dos Barrios IDENTITY_ONLY on {len(reg['sources'])} archived sources and {len(reg['quotes'])} verbatim quotes; "
          "one EVENT_LEAD_UNVERIFIED (A6608, 2012-04-05; not EVENT_EVIDENCE, not in any ledger); no geometry or confluence; map_publishable=false; guards closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
