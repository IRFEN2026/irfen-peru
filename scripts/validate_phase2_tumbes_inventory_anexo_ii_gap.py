#!/usr/bin/env python3
"""Fail-closed check of the Tumbes inventory gap closure (ANA Anexo II DU 015-2023).

Proves, offline, that config/phase2_tumbes_inventory_anexo_ii_gap_v0_1.json:

* keeps every guard closed and publishes nothing to the map;
* cites only archived sources whose bytes and text match their manifest SHA-256,
  and quotes them verbatim (whitespace-normalised) on the cited page;
* accounts for every row of Anexo II section I - TUMBES (1-29) exactly once;
* classifies each of the 12 requested names with an allowed maturity, keeps
  geometry and outlet UNKNOWN, and points to existing national-audit rows that
  are not map-eligible, have no geometry, outlet or parent basin;
* does not create duplicate audit rows and leaves every alias group pending;
* does not use the Plan de Intervenciones while no complete copy is archived.

Standard library only. Exit code 0 = consistent, 1 = violations (listed).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "config/phase2_tumbes_inventory_anexo_ii_gap_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
}
REQUESTED = ["Fernández", "Seca", "Casitas", "Carretas", "07 de Junio", "Hualaca", "Hualtacal", "Plateros", "Santa María",
             "Nueva Esperanza", "Santa Rosa", "Malvales"]
MATURITY = {"M1_SINGLE_OFFICIAL_LISTING", "M2_MULTI_SOURCE_IDENTITY", "M3_PERIOD_EVENT_LEAD"}
FLAGS = {"HOMONYM_RESOLUTION_REQUIRED", "ALIAS_ADJUDICATION_PENDING", "GEOMETRY_UNKNOWN", "OUTLET_UNKNOWN", "NOT_MAP_ELIGIBLE"}
REQUIRED_FLAGS = {"GEOMETRY_UNKNOWN", "OUTLET_UNKNOWN", "NOT_MAP_ELIGIBLE"}
REGISTRATION = {"NEW_ROW_IN_MASTER_INVENTORY", "VARIANT_EVIDENCE_ON_EXISTING_ROW_PENDING_ALIAS"}
FORBIDDEN_KEYS = {"geometry", "coordinates", "lat", "lon", "latitude", "longitude", "easting_m", "northing_m", "outlet_point",
                  "confluence_point", "discharge", "capacity", "threshold", "thresholds", "alert_level", "risk_class"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def squash(text: str) -> str:
    """Accent-, case- and space-insensitive form ('Nueva Esperanz a' == 'Nueva Esperanza')."""
    folded = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", "", folded)


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_keys(value)


def validate(gap: dict, audit: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for key, expected in GUARDS.items():
        if gap.get(key, "<missing>") != expected:
            errors.append(f"guard {key} must be {expected!r}")
    if gap.get("status") != "RESEARCH_ONLY_INVENTORY_GAP_CLOSURE_PENDING_INDEPENDENT_QA":
        errors.append("status must stay RESEARCH_ONLY_INVENTORY_GAP_CLOSURE_PENDING_INDEPENDENT_QA")
    if any(v != 0 for v in gap.get("map_updates", {"missing": 1}).values()):
        errors.append("map_updates must all be zero")
    bad = FORBIDDEN_KEYS & set(walk_keys(gap))
    if bad:
        errors.append(f"forbidden keys {sorted(bad)}")

    prov = gap.get("provenance", {})
    manifests = {}
    for key in ("reused_archive_manifest", "lane_archive_manifest"):
        rel = prov.get(key, "")
        path = root / rel
        if not rel or rel.startswith("site/") or not path.is_file():
            errors.append(f"provenance {key} missing or inside site/")
            continue
        if sha256_file(path) != prov.get(f"{key}_sha256"):
            errors.append(f"provenance {key}_sha256 differs from the committed manifest")
        manifests[rel] = json.loads(path.read_text(encoding="utf-8"))
        for g, value in GUARDS.items():
            if manifests[rel].get(g) != value:
                errors.append(f"{rel}: guard {g} must be {value!r}")

    pages: dict[str, list[str]] = {}
    for sid, src in gap.get("sources", {}).items():
        man = manifests.get(src.get("archive_manifest"))
        rec = next((r for r in (man or {}).get("records", []) if r.get("document_id") == src.get("archive_document_id")), None)
        if not rec or rec.get("status") != "ARCHIVED":
            errors.append(f"source {sid}: not an ARCHIVED record of a committed manifest")
            continue
        for key in ("raw_path", "sha256", "text_path", "text_sha256"):
            if src.get(key) != rec.get(key):
                errors.append(f"source {sid}: {key} differs from the manifest")
        for key in ("raw_path", "text_path"):
            if str(src.get(key, "")).startswith("site/"):
                errors.append(f"source {sid}: {key} inside site/")
        raw, text = root / rec["raw_path"], root / rec["text_path"]
        if not raw.is_file() or sha256_file(raw) != rec["sha256"]:
            errors.append(f"source {sid}: archived bytes missing or SHA-256 mismatch")
        if not text.is_file() or sha256_file(text) != rec["text_sha256"]:
            errors.append(f"source {sid}: text missing or SHA-256 mismatch")
            continue
        pages[sid] = json.loads(text.read_text(encoding="utf-8"))["pages"]

    quotes = gap.get("quotes", {})
    for qid, q in quotes.items():
        pg = pages.get(q.get("source_id"))
        idx = q.get("text_page_index")
        if pg is None or not isinstance(idx, int) or not 1 <= idx <= len(pg):
            errors.append(f"quote {qid}: unverifiable source or page")
        elif not norm(q.get("text", "")) or norm(q["text"]) not in norm(pg[idx - 1]):
            errors.append(f"quote {qid}: not a verbatim substring of the archived text page {idx}")

    rows = {r["inventory_id"]: r for r in audit.get("candidates", [])}
    curated = audit.get("aliases_pending_adjudication", {}).get("curated_relationships", [])

    crosswalk = gap.get("anexo_ii_tumbes_crosswalk", [])
    if sorted(c.get("row") for c in crosswalk) != list(range(1, 30)):
        errors.append("crosswalk must account for Anexo II section I rows 1-29 exactly once")
    for c in crosswalk:
        q = quotes.get(c.get("quote_id"), {})
        if not norm(q.get("text", "")).startswith(f"{c.get('row')} "):
            errors.append(f"crosswalk row {c.get('row')}: quote does not start with its row number")
        if c.get("inventory_id") is not None and c["inventory_id"] not in rows:
            errors.append(f"crosswalk row {c.get('row')}: unknown inventory_id {c['inventory_id']}")

    names = gap.get("requested_names", [])
    if [n.get("requested_name") for n in names] != REQUESTED:
        errors.append("requested_names must list the 12 requested names in order")
    seen_ids: dict[str, str] = {}
    for n in names:
        name = n.get("requested_name")
        if n.get("maturity") not in MATURITY:
            errors.append(f"{name}: maturity outside the vocabulary")
        flags = set(n.get("flags", []))
        if not flags <= FLAGS or not REQUIRED_FLAGS <= flags:
            errors.append(f"{name}: flags must be in the vocabulary and include {sorted(REQUIRED_FLAGS)}")
        if n.get("geometry_status") != "UNKNOWN" or n.get("outlet_status") != "UNKNOWN" or n.get("map_eligible") is not False:
            errors.append(f"{name}: geometry and outlet must stay UNKNOWN and map_eligible false")
        if n.get("plan_de_intervenciones") != gap.get("plan_de_intervenciones", {}).get("status"):
            errors.append(f"{name}: plan_de_intervenciones status must match the plan record")
        for qid in n.get("anexo_ii_quote_ids", []):
            if squash(name) not in squash(quotes.get(qid, {}).get("text", "")):
                errors.append(f"{name}: Anexo II quote {qid} does not print the name")
        if not n.get("anexo_ii_quote_ids"):
            errors.append(f"{name}: needs at least one Anexo II row")
        for qid in n.get("context_quote_ids", []):
            if qid not in quotes:
                errors.append(f"{name}: unknown context quote {qid}")
        reg = n.get("registration")
        if reg not in REGISTRATION:
            errors.append(f"{name}: registration outside the vocabulary")
        ids = n.get("inventory_ids", [])
        if len(ids) != 1:
            errors.append(f"{name}: exactly one inventory row expected (no duplicates)")
            continue
        rid = ids[0]
        if rid in seen_ids:
            errors.append(f"{name}: inventory row {rid} already used by {seen_ids[rid]}")
        seen_ids[rid] = name
        row = rows.get(rid)
        if not row:
            errors.append(f"{name}: inventory row {rid} missing from the audit")
            continue
        if row.get("map_eligible") is not False or row.get("parent_basin_or_system") is not None \
                or row.get("reproducible_geometry", {}).get("exists") or row.get("reproducible_outlet_or_confluence", {}).get("exists"):
            errors.append(f"{name}: audit row {rid} must stay without map, geometry, outlet or parent basin")
        cps = {e.get("row_number_as_read") for e in row.get("evidence", []) if e.get("source_id") == "ANA-DU-015-2023-ANEXO-II"}
        if not set(n.get("anexo_ii_rows", [])) <= cps:
            errors.append(f"{name}: audit row {rid} lacks the Anexo II evidence for rows {n.get('anexo_ii_rows')}")
        if reg == "NEW_ROW_IN_MASTER_INVENTORY" and row.get("added_in_revision") != "r3":
            errors.append(f"{name}: {rid} is not a row added in r3")
        if reg == "VARIANT_EVIDENCE_ON_EXISTING_ROW_PENDING_ALIAS":
            if row.get("added_in_revision"):
                errors.append(f"{name}: variant evidence must sit on a pre-existing row")
            if not any(e.get("variant_attachment") for e in row.get("evidence", [])):
                errors.append(f"{name}: variant evidence must be marked as a pending attachment")
        if "ALIAS_ADJUDICATION_PENDING" in flags and not any(
                rid in g.get("inventory_ids", []) and g.get("status") == "PENDING_ADJUDICATION" for g in curated):
            errors.append(f"{name}: alias flag without a PENDING_ADJUDICATION group in the audit")
        has_event = any(e.get("evidence_type") == "EVENT" for e in row.get("evidence", []))
        if (n.get("maturity") == "M3_PERIOD_EVENT_LEAD") != has_event:
            errors.append(f"{name}: M3 requires (and only M3 allows) an EVENT item on the audit row")

    added = [r["inventory_id"] for r in audit.get("candidates", []) if r.get("added_in_revision") == "r3"]
    if sorted(added) != sorted(gap.get("audit_changes", {}).get("rows_added", [])):
        errors.append("audit_changes.rows_added differs from the audit rows marked r3")
    keys = [(squash(r.get("documentary_name", "")), r.get("district")) for r in audit.get("candidates", []) if r.get("department") == "Tumbes"]
    for key in {k for k in keys if keys.count(k) > 1}:
        errors.append(f"duplicate Tumbes audit rows for {key}")
    for g in curated:
        if "MERGED" in g.get("status", "") and "NOT" not in g.get("status", ""):
            errors.append("alias groups may not be merged")

    plan = gap.get("plan_de_intervenciones", {})
    lane = manifests.get(prov.get("lane_archive_manifest"), {})
    lane_rec = next((r for r in lane.get("records", []) if r.get("document_id") == "ana-plan-de-intervenciones"), {})
    archived = lane_rec.get("status") == "ARCHIVED" and not lane_rec.get("possibly_truncated")
    if plan.get("archived") is not archived or (plan.get("status") == "NOT_READ_SOURCE_INCOMPLETE") == archived:
        errors.append("plan_de_intervenciones status disagrees with the lane manifest")
    if not archived and any("PLAN" in str(q.get("source_id", "")).upper() for q in quotes.values()):
        errors.append("the Plan de Intervenciones may not be quoted while no complete copy is archived")
    return errors


def main() -> int:
    gap = json.loads(GAP.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    errors = validate(gap, audit)
    if errors:
        print("FAIL:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: 12 requested names classified, {len(gap['quotes'])} verbatim quotes, Anexo II rows 1-29 accounted for, "
          f"{len(gap['audit_changes']['rows_added'])} audit rows added, 0 map-eligible, guards closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
