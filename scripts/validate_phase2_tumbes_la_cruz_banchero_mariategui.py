#!/usr/bin/env python3
"""Fail-closed check of the La Cruz (Tumbes) documentary increment (inventory r7: Banchero, Mariátegui, Banchero Rossi).

Offline, standard library only: archived bytes match SHA-256, quotes are re-read from the archived text layers,
identity/works and event evidence stay separate, events stay unverified leads, geometry/outlet stay unknown, the
Banchero / Banchero Rossi relation stays UNRESOLVED and the Tumbes Mariátegui row is not tied to Piura.

    python scripts/validate_phase2_tumbes_la_cruz_banchero_mariategui.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG_PATH = ROOT / "config/phase2_tumbes_la_cruz_banchero_mariategui_v0_1.json"
AUDIT_PATH = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
GUARDS = {"deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
          "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
          "decision_thresholds": None, "hydraulic_factors": None}
ROWS = {"tumbes_la_cruz_banchero": "EVENT_LEAD_UNVERIFIED", "tumbes_la_cruz_mariategui": "EVENT_LEAD_UNVERIFIED",
        "tumbes_la_cruz_banchero_rossi": "IDENTITY_ONLY"}
norm = lambda s: re.sub(r"\s+", " ", s).strip()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate(reg: dict, audit: dict, root: Path = ROOT) -> list[str]:
    errors = []
    for k, v in GUARDS.items():
        if reg.get(k) != v:
            errors.append(f"guard {k} must be {v!r}")
    if reg.get("map_publishable") is not False or any(v != 0 for v in reg.get("map_updates", {"x": 1}).values()):
        errors.append("map_publishable/map_updates must stay closed")
    layers = {}
    for sid, s in reg.get("sources", {}).items():
        raw = root / s["archive_raw"]
        if not raw.is_file() or _sha(raw) != s.get("sha256"):
            errors.append(f"source {sid}: archived bytes missing or SHA-256 mismatch")
            continue
        if raw.resolve().is_relative_to((root / "site").resolve()):
            errors.append(f"source {sid}: archive must stay outside site/")
        layer = json.loads((root / s["archive_text"]).read_text(encoding="utf-8"))
        if layer.get("sha256_of_raw") != s["sha256"]:
            errors.append(f"source {sid}: text layer belongs to other bytes")
        layers[sid] = [norm(p) for p in layer["pages"]]
        scan = s.get("scanned_document")
        if scan and (not (root / scan["archive_raw"]).is_file() or _sha(root / scan["archive_raw"]) != scan["sha256"]):
            errors.append(f"source {sid}: scanned document missing or SHA-256 mismatch")
    for qid, q in reg.get("quotes", {}).items():
        if q.get("text_layer_page") is None:
            if "VISUAL_REVIEW" not in q.get("check", ""):
                errors.append(f"quote {qid}: without text layer it must be declared a visual review")
            continue
        pages = layers.get(q["source_id"], [])
        if not 1 <= q["text_layer_page"] <= len(pages) or norm(q["text"]) not in pages[q["text_layer_page"] - 1]:
            errors.append(f"quote {qid}: not a verbatim substring of the archived text layer")
    rows = {r["inventory_id"]: r for r in audit.get("candidates", [])}
    for rid, state in ROWS.items():
        r = rows.get(rid)
        if not r:
            errors.append(f"row {rid} missing from the audit")
            continue
        if r.get("suggested_state") != state or r.get("state_flags") != [state]:
            errors.append(f"row {rid}: state must be {state}")
        if r.get("map_eligible") is not False or r.get("parent_basin_or_system") is not None or \
                r.get("reproducible_geometry") != {"exists": False} or r.get("reproducible_outlet_or_confluence") != {"exists": False}:
            errors.append(f"row {rid}: geometry, outlet, parent and map must stay absent")
        if r.get("verified_event_dates"):
            errors.append(f"row {rid}: events must stay unverified leads")
        for e in r.get("evidence", []):
            q = reg["quotes"].get(e.get("quote_id"))
            if not q or q["source_id"] != e["source_id"]:
                errors.append(f"row {rid}: evidence without a matching quote")
            if e["evidence_type"] == "EVENT" and (e.get("source_text_verified") is not False or e.get("verification") is not None):
                errors.append(f"row {rid}: EVENT item must stay unverified")
        types = [e["evidence_type"] for e in r.get("evidence", [])]
        if state == "EVENT_LEAD_UNVERIFIED" and not ("IDENTITY" in types and "EVENT" in types):
            errors.append(f"row {rid}: identity and event must be separate evidence items")
        if state == "IDENTITY_ONLY" and "EVENT" in types:
            errors.append(f"row {rid}: works-only row cannot carry an event")
    groups = audit.get("aliases_pending_adjudication", {}).get("curated_relationships", [])
    g = [x for x in groups if set(x.get("inventory_ids", [])) == {"tumbes_la_cruz_banchero", "tumbes_la_cruz_banchero_rossi"}]
    if len(g) != 1 or g[0].get("equivalence") != "UNRESOLVED":
        errors.append("Banchero / Banchero Rossi must be one UNRESOLVED relationship, not merged")
    for x in groups:
        if "tumbes_la_cruz_mariategui" in x.get("inventory_ids", []) and any(i.startswith("piura_") for i in x["inventory_ids"]):
            errors.append("Mariátegui (Tumbes) must not be grouped with Piura rows")
    return errors


def main() -> int:
    errors = validate(json.loads(REG_PATH.read_text(encoding="utf-8")), json.loads(AUDIT_PATH.read_text(encoding="utf-8")))
    for e in errors:
        print("ERROR:", e)
    if not errors:
        print("OK: 3 La Cruz rows, archives and quotes verified, events unverified leads, geometry/outlet unknown.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
