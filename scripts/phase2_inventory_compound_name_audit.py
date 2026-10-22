"""Audit of compound documentary names in the national inventory (master + r8). RESEARCH_ONLY / TEST_ONLY.

Read-only and deterministic. It classifies every row whose documentary_name joins several labels (y, comma, hyphen,
slash, parentheses, numbered series) using only the text already recorded in that row's evidence. It never splits,
merges or renames a row: a split needs explicit evidence and a reviewed decision, recorded in the row itself
(split_basis). The output lists, for each compound name, what kind of compound it is and what review it needs.

Usage: python scripts/phase2_inventory_compound_name_audit.py   (prints the audit as JSON)
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
R8 = ROOT / "config/phase2_national_inventory_r8_sigrid_sweep_v0_1.json"

COMPOUND = re.compile(r"\s(?:y|e)\s|\s[-–—/]\s|[a-záéíóúñ]-[a-záéíóúñ]|\(|,|\s(?:I|II|III|1|2|3)(?:\s|,|$)", re.I)
CATEGORIES = {
    "SPLIT_RECORDED_WITH_BASIS": "Already recorded as separate rows, each carrying split_basis (source text + decision).",
    "LABEL_COMPONENT_ALREADY_FLAGGED": "The row itself says it is a component of a compound label; nothing to decide here.",
    "DISTRICT_QUALIFIER": "Parentheses carry the district name, not an alias.",
    "LOCALITY_QUALIFIER": "Parentheses carry the populated centre that identifies an unnamed or ambiguous quebrada, not an alias.",
    "PARENTHETICAL_ALIAS_OR_SUBNAME_PENDING": "Parentheses carry a second name (alias, sub-name, river or sector); not adjudicated.",
    "SOURCE_TABLE_LOCALITY_LABEL": "The source table prints the same compound as populated centre and quebrada: a locality label, kept as printed.",
    "SOURCE_TABLE_SINGLE_CELL_COMPOUND": "The source table prints the compound in one quebrada cell: kept as one row until the table is reread.",
    "ENUMERATED_DISTINCT_NAMES_IN_SOURCE": "The recorded source text enumerates the names with plural 'quebradas': explicit split candidate.",
    "NUMBERED_SERIES_IN_SOURCE": "The recorded source text names a numbered series (1, 2, 3 / I, II): split candidate, same pattern as El Establo.",
    "SOURCE_TEXT_NOT_READ": "The compound comes from a file name or an automated title reading; the source text naming it was not recorded.",
    "SECONDARY_OR_LIST_SOURCE_ONLY": "Only a press item or a district list carries the compound: needs a primary source first.",
}
RECOMMENDATION = {
    "SPLIT_RECORDED_WITH_BASIS": "NONE",
    "LABEL_COMPONENT_ALREADY_FLAGGED": "NONE",
    "DISTRICT_QUALIFIER": "NONE",
    "LOCALITY_QUALIFIER": "NONE",
    "PARENTHETICAL_ALIAS_OR_SUBNAME_PENDING": "ADJUDICATE_ALIAS_FROM_PRIMARY_SOURCE",
    "SOURCE_TABLE_LOCALITY_LABEL": "KEEP_AS_PRINTED",
    "SOURCE_TABLE_SINGLE_CELL_COMPOUND": "REREAD_ARCHIVED_TABLE_BEFORE_ANY_SPLIT",
    "ENUMERATED_DISTINCT_NAMES_IN_SOURCE": "REVIEW_SPLIT_WITH_ARCHIVED_SOURCE",
    "NUMBERED_SERIES_IN_SOURCE": "REVIEW_SPLIT_WITH_ARCHIVED_SOURCE",
    "SOURCE_TEXT_NOT_READ": "READ_AND_ARCHIVE_SOURCE_FIRST",
    "SECONDARY_OR_LIST_SOURCE_ONLY": "FIND_PRIMARY_SOURCE_FIRST",
}
SECONDARY = {"PRESS-LEAD", "INDECI-DDI-LIMA-2023-BALANCE", "ANDINA-TUMBES-2023-04-01", "ANDINA-TUMBES-2024-02-21", "ANDINA-MVCS-2023-02-23"}


def _fold(s: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).split())


def is_compound(name: str) -> bool:
    return bool(COMPOUND.search(name or ""))


def classify(row: dict) -> tuple[str, str]:
    """(category, evidence basis quoted from the row). Order matters: the most specific evidence wins."""
    name = row["documentary_name"]
    ev = row.get("evidence") or []
    texts = [" ".join(str(e.get(k) or "") for k in ("label_in_source", "detail")) for e in ev]
    joined = " | ".join(texts)
    if row.get("split_basis"):
        return "SPLIT_RECORDED_WITH_BASIS", row["split_basis"]["source_text"]
    if row["inventory_id"].endswith("_label") or "label component" in name.lower():
        return "LABEL_COMPONENT_ALREADY_FLAGGED", joined[:200]
    paren = re.search(r"\(([^)]+)\)", name)
    if paren and _fold(paren.group(1)) == _fold(row.get("district")):
        return "DISTRICT_QUALIFIER", paren.group(0)
    if paren and re.match(r"(centro poblado|c\.? ?p\.?)\s", _fold(paren.group(1)) + " "):
        return "LOCALITY_QUALIFIER", paren.group(0)
    head = _fold(re.sub(r"\(.*?\)", " ", name))
    table = [t for t, e in zip(texts, ev) if e.get("source_id") == "ANA-2016-COMPLEMENTACION-NACIONAL"]
    for t in table:
        m = re.search(r"centro poblado '([^']+)', quebrada '([^']+)'", t)
        if m and _fold(m.group(1)) == _fold(m.group(2)):
            return "SOURCE_TABLE_LOCALITY_LABEL", m.group(0)
    if paren:
        return "PARENTHETICAL_ALIAS_OR_SUBNAME_PENDING", paren.group(0)
    if table:
        return "SOURCE_TABLE_SINGLE_CELL_COMPOUND", table[0][:200]
    folded = _fold(joined)
    named_in_text = head and head.replace(" y ", " ").split()[0] in folded.split() and _fold(name.split(" y ")[0].split("-")[0].split(",")[0]) in folded
    if named_in_text and re.search(r"\bquebradas\b", folded):
        return "ENUMERATED_DISTINCT_NAMES_IN_SOURCE", joined[:220]
    if named_in_text and re.search(r"(\b[0-9]\b.*\b(y|e)\b.*\b[0-9]\b)|\b(i y ii|ii y iii)\b", _fold(name)):
        return "NUMBERED_SERIES_IN_SOURCE", joined[:220]
    if ev and all(e.get("source_id") in SECONDARY for e in ev):
        return "SECONDARY_OR_LIST_SOURCE_ONLY", joined[:200]
    return "SOURCE_TEXT_NOT_READ", joined[:200]


def audit(master: dict, r8: dict) -> list[dict]:
    out = []
    for origin, doc in (("main", master), ("r8", r8)):
        for row in doc["candidates"]:
            if not (is_compound(row["documentary_name"]) or row.get("split_basis")):
                continue
            cat, basis = classify(row)
            out.append(dict(inventory_id=row["inventory_id"], origin=origin, documentary_name=row["documentary_name"],
                            department=row.get("department"), district=row.get("district"), category=cat,
                            evidence_basis=basis, recommendation=RECOMMENDATION[cat], split_performed_by_this_audit=False))
    return sorted(out, key=lambda x: (x["origin"], x["inventory_id"]))


def main() -> int:
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    r8 = json.loads(R8.read_text(encoding="utf-8"))
    print(json.dumps(audit(master, r8), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
