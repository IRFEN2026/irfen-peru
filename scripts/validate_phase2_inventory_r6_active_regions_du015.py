#!/usr/bin/env python3
"""Fail-closed check of master-inventory revision r6 (active regions, ANA DU 015-2023 Anexo II/III, Huarangal link).

Offline, standard library only. It proves that:
- the archived Anexo II/III bytes match their SHA-256 and every quote is re-read from the archived text layer;
- every r6 row exists once in the national audit, stays IDENTITY_ONLY, map-ineligible, with no geometry, outlet or
  parent basin, and its evidence cites a tested quote (Anexo III reference numbers must be the printed ones);
- link rows point at units that main already registers, and no main unit gets a second master row;
- every source row read in the active regions is accounted for exactly once, and pre-existing rows are unchanged;
- equivalences added in r6 stay UNRESOLVED.

    python scripts/validate_phase2_inventory_r6_active_regions_du015.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XW_PATH = ROOT / "config/phase2_inventory_r6_active_regions_du015_v0_1.json"
AUDIT_PATH = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
}
A2, A3 = "ANA-DU-015-2023-ANEXO-II", "ANA-DU-015-2023-ANEXO-III"
# Source rows read in the active regions: Anexo III (all 22 rows) and Anexo II sección XV (ICA) + Casma-basin quebradas.
EXPECTED_ROWS = {A3: set(range(1, 23)), A2: set(range(73, 83)) | {88, 89, 90}}
RELATIONS = {"NEW_ROW_R6", "LINK_ROW_R6_TO_MAIN_UNIT", "EXISTING_ROW_UNCHANGED"}
# Units that main registers and that r6 links to (main file that must carry the id).
LINKS = {
    "ica_catambo": "config/phase2_south_coast_ica_arequipa_discovery_v0_1.json",
    "ica_huarangal_pisco": "config/phase2_south_coast_channel_identity_v0_1.json",
}
norm = lambda s: re.sub(r"\s+", " ", s).strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(xw: dict, audit: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for key, expected in GUARDS.items():
        if xw.get(key) != expected:
            errors.append(f"guard {key} must be {expected!r}")
    if xw.get("map_publishable") is not False:
        errors.append("map_publishable must be false")
    if any(v != 0 for v in xw.get("map_updates", {}).values()) or not xw.get("map_updates"):
        errors.append("map_updates must exist and be all zero")

    pages = {}
    for sid in (A2, A3):
        src = xw.get("sources", {}).get(sid) or {}
        raw, text = root / str(src.get("archive_raw")), root / str(src.get("archive_text"))
        if not raw.is_file() or not text.is_file():
            errors.append(f"source {sid}: archived file missing")
            continue
        if _sha(raw) != src.get("sha256"):
            errors.append(f"source {sid}: archived bytes do not match sha256")
        layer = json.loads(text.read_text(encoding="utf-8"))
        if layer.get("sha256_of_raw") != src.get("sha256"):
            errors.append(f"source {sid}: text layer belongs to other bytes")
        if raw.resolve().is_relative_to((root / "site").resolve()):
            errors.append(f"source {sid}: archive must stay outside site/")
        pages[sid] = [norm(p) for p in layer.get("pages", [])]

    quotes = xw.get("quotes", {})
    for qid, q in quotes.items():
        sid, page = q.get("source_id"), q.get("page")
        if sid not in pages:
            continue
        if not isinstance(page, int) or not 1 <= page <= len(pages[sid]) or norm(q.get("text", "")) not in pages[sid][page - 1]:
            errors.append(f"quote {qid}: not a verbatim text-layer quote of {sid} p. {page}")
        if not q.get("text", "").startswith(f"{q.get('row_number_as_read')} "):
            errors.append(f"quote {qid}: does not start with its row number")

    rows = {r["inventory_id"]: r for r in audit.get("candidates", [])}
    r6 = [r for r in audit.get("candidates", []) if r.get("added_in_revision") == "r6"]
    if sorted(r["inventory_id"] for r in r6) != sorted(xw.get("new_rows", [])):
        errors.append("new_rows out of sync with the audit rows marked added_in_revision r6")
    for r in r6:
        where = f"row {r['inventory_id']}"
        if r.get("map_eligible") is not False or r.get("parent_basin_or_system") is not None:
            errors.append(f"{where}: must stay map-ineligible without parent basin")
        if r.get("reproducible_geometry") != {"exists": False} or r.get("reproducible_outlet_or_confluence") != {"exists": False}:
            errors.append(f"{where}: geometry and outlet must stay absent")
        if r.get("suggested_state") != "IDENTITY_ONLY" or r.get("state_flags") != ["IDENTITY_ONLY"]:
            errors.append(f"{where}: must stay IDENTITY_ONLY")
        for e in r.get("evidence", []):
            if e.get("source_id") not in (A2, A3):
                continue
            q = quotes.get(e.get("quote_id"))
            if not q or q.get("source_id") != e["source_id"] or q.get("row_number_as_read") != e.get("row_number_as_read"):
                errors.append(f"{where}: evidence without a matching tested quote")
                continue
            if f"«{q['text']}»" not in e.get("detail", ""):
                errors.append(f"{where}: evidence detail does not carry the tested quote")
            point = e.get("source_reference_point")
            if e["source_id"] == A3:
                if not point or f" {point.get('easting_m')} {point.get('northing_m')} " not in f" {q['text']} ":
                    errors.append(f"{where}: Anexo III reference numbers must be the printed ones")
            elif point is not None:
                errors.append(f"{where}: Anexo II prints no coordinates")
        presence = r.get("irfen_presence", {})
        if presence.get("status") == "MAIN_REGISTERED_UNIT":
            unit = presence.get("main_unit_id")
            path = LINKS.get(unit)
            if not path or f'"{unit}"' not in (root / path).read_text(encoding="utf-8"):
                errors.append(f"{where}: links to {unit}, which main does not register")
    linked = Counter((r.get("irfen_presence") or {}).get("main_unit_id") for r in rows.values())
    for unit in LINKS:
        if linked[unit] != 1:
            errors.append(f"main unit {unit} must have exactly one master row (found {linked[unit]})")

    seen = Counter()
    for c in xw.get("crosswalk", []):
        key = (c.get("source_id"), c.get("row_number_as_read"))
        seen[key] += 1
        rid, rel = c.get("inventory_id"), c.get("relation")
        if rel not in RELATIONS:
            errors.append(f"crosswalk {key}: unknown relation {rel}")
        if rid not in rows:
            errors.append(f"crosswalk {key}: unknown inventory_id {rid}")
            continue
        is_new = rows[rid].get("added_in_revision") == "r6"
        if (rel == "EXISTING_ROW_UNCHANGED") == is_new:
            errors.append(f"crosswalk {key}: relation {rel} inconsistent with row {rid}")
        if rel == "EXISTING_ROW_UNCHANGED" and any(e.get("source_id") in (A2, A3) for e in rows[rid].get("evidence", [])):
            errors.append(f"crosswalk {key}: pre-existing row {rid} must stay unchanged")
        if rel == "LINK_ROW_R6_TO_MAIN_UNIT" and rows[rid].get("priority") != "EXISTING":
            errors.append(f"crosswalk {key}: a link row must carry priority EXISTING")
    for sid, expected in EXPECTED_ROWS.items():
        got = {n for (s, n), k in seen.items() if s == sid}
        if got != expected or any(k != 1 for (s, _), k in seen.items() if s == sid):
            errors.append(f"crosswalk {sid}: rows {sorted(expected)} must each be accounted for exactly once")

    for g in audit.get("aliases_pending_adjudication", {}).get("curated_relationships", []):
        if g.get("added_in_revision") == "r6" and (g.get("equivalence") != "UNRESOLVED" or g.get("status") != "PENDING_ADJUDICATION"):
            errors.append(f"equivalence {g.get('labels')}: must stay UNRESOLVED / PENDING_ADJUDICATION")
    return errors


def main() -> int:
    xw = json.loads(XW_PATH.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    errors = validate(xw, audit)
    for e in errors:
        print("ERROR:", e)
    if not errors:
        print(f"OK: {len(xw['new_rows'])} r6 rows, {len(xw['quotes'])} quotes re-read on the archived text layer, "
              f"{len(xw['crosswalk'])} source rows accounted for, 0 geometry/outlet/map changes.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
