#!/usr/bin/env python3
"""Read-only query of the national inventory of documented quebradas (completeness audit, 400 identities).

Documentary consultation only. It never writes, never promotes an identity or an event, and does not need a
geometry: rows without geometry are listed like any other. Each row carries a provenance status computed at query
time from the audit's own verification contract (see scripts/validate_phase2_national_inventory_audit.py):

    VERIFICADA_SHA256          source verification_record points to a file archived in this repository whose
                               SHA-256, recomputed now, equals archived_sha256, AND the evidence item carries
                               its own locator + verified_statement.
    SHA256_DISTINTO            the archived file exists but its recomputed SHA-256 differs from the record.
    ARCHIVO_AUSENTE            the record names a repository path that does not exist.
    REGISTRO_SIN_ARCHIVO_LOCAL the record exists but its locator is not a safe archive path in this repository
                               (URL, absolute, outside data/ or site/data/, traversal, symbolic link leaving the
                               archive root, control characters) or its hash is malformed: not verified.
    SIN_VERIFICAR              no verification record (source_text_verified is false): a lead, not evidence.
    FUENTE_NO_CATALOGADA       the evidence names a source_id missing from the audit's source catalog.

A row is VERIFICADA_SHA256 only if at least one of its evidence items is. A recorded hash alone, or the age or
reputation of a source, never verifies anything. Standard library only.

    python scripts/query_phase2_national_inventory.py --name banchero
    python scripts/query_phase2_national_inventory.py --department Tumbes --without-geometry --format json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
GUARD_KEYS = ("deployment_status", "test_mode", "production_use", "production_ready", "operational_alerting_enabled",
              "activation_gate", "missing_data_rule", "decision_thresholds", "hydraulic_factors")
EXPECTED_GUARDS = {"deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False,
                   "production_ready": False, "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
                   "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "decision_thresholds": None, "hydraulic_factors": None}
PROVENANCE = ("VERIFICADA_SHA256", "SHA256_DISTINTO", "ARCHIVO_AUSENTE", "REGISTRO_SIN_ARCHIVO_LOCAL",
              "SIN_VERIFICAR", "FUENTE_NO_CATALOGADA")
# Row status precedence: a verified item wins; otherwise integrity problems are surfaced before plain "unverified".
ROW_ORDER = ("VERIFICADA_SHA256", "SHA256_DISTINTO", "ARCHIVO_AUSENTE", "FUENTE_NO_CATALOGADA",
             "REGISTRO_SIN_ARCHIVO_LOCAL", "SIN_VERIFICAR")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NOTICE = ("Consulta documental RESEARCH_ONLY / TEST_ONLY. No promueve identidades ni eventos, no crea geometrías "
          "ni outlets y no es un mapa de riesgo ni de alertas. Sin dato = UNKNOWN, nunca riesgo bajo.")


def fold(value) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").casefold()


def load(path: Path = AUDIT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def guards_of(audit: dict) -> dict:
    guards = {k: audit.get(k) for k in GUARD_KEYS}
    if guards != EXPECTED_GUARDS:
        raise ValueError(f"audit guards changed; refusing to query: {guards}")
    return guards


ARCHIVE_ROOTS = (("data",), ("site", "data"))


def repo_file(locator, root: Path) -> Path | None:
    """A repository-relative archived file, or None when the locator is not a safe local archive path.

    Accepted only under data/ or site/data/; rejects URLs, absolute paths, backslashes, control characters,
    empty / "." / ".." segments, and anything whose resolved real path (symbolic links followed) leaves the
    archive root. None means "not reproducible here", never "verified".
    """
    if not isinstance(locator, str) or not locator or "://" in locator or "\\" in locator:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in locator) or locator.startswith("/"):
        return None
    parts = locator.split("/")
    if any(seg in ("", ".", "..") for seg in parts):
        return None
    base = next((r for r in ARCHIVE_ROOTS if tuple(parts[:len(r)]) == r and len(parts) > len(r)), None)
    if base is None:
        return None
    root_real = root.resolve()
    allowed = root_real.joinpath(*base)
    candidate = root.joinpath(*parts)
    try:
        real = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if real != allowed and allowed not in real.parents:
        return None
    return candidate


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_status(source: dict | None, root: Path) -> str:
    if source is None:
        return "FUENTE_NO_CATALOGADA"
    record = source.get("verification_record")
    if not (source.get("source_text_verified") is True and isinstance(record, dict)):
        return "SIN_VERIFICAR"
    expected = str(record.get("archived_sha256", ""))
    path = repo_file(record.get("archive_locator"), root)
    if path is None or not SHA256_RE.match(expected):
        return "REGISTRO_SIN_ARCHIVO_LOCAL"
    if not path.is_file():
        return "ARCHIVO_AUSENTE"
    return "VERIFICADA_SHA256" if sha256_file(path) == expected else "SHA256_DISTINTO"


def item_status(item: dict, sources: dict, root: Path) -> str:
    status = source_status(sources.get(item.get("source_id")), root)
    if status != "VERIFICADA_SHA256":
        return status
    record = item.get("verification")
    item_ok = (item.get("source_text_verified") is True and isinstance(record, dict)
               and str(record.get("locator") or "").strip() and str(record.get("verified_statement") or "").strip())
    # Archived bytes match, but this statement was not located in them: the item stays unverified.
    return "VERIFICADA_SHA256" if item_ok else "SIN_VERIFICAR"


def rows(audit: dict, root: Path = ROOT) -> list[dict]:
    guards_of(audit)
    sources = audit.get("sources") or {}
    out = []
    for r in audit["candidates"]:
        items = [dict(source_id=e.get("source_id"), evidence_type=e.get("evidence_type"),
                      provenance=item_status(e, sources, root)) for e in r.get("evidence") or []]
        statuses = {i["provenance"] for i in items}
        row_status = next((s for s in ROW_ORDER if s in statuses), "SIN_VERIFICAR")
        out.append(dict(
            inventory_id=r["inventory_id"], documentary_name=r.get("documentary_name"),
            name_variants=list(r.get("name_variants_observed") or []), row_role=r.get("row_role"),
            department=r.get("department"), province=r.get("province"), district=r.get("district"),
            corridor=r.get("corridor"), suggested_state=r.get("suggested_state"),
            state_flags=list(r.get("state_flags") or []), priority=r.get("priority"),
            irfen_presence=(r.get("irfen_presence") or {}).get("status"),
            has_reproducible_geometry=bool((r.get("reproducible_geometry") or {}).get("exists")),
            has_reproducible_outlet=bool((r.get("reproducible_outlet_or_confluence") or {}).get("exists")),
            map_eligible=r.get("map_eligible") is True,
            provenance=row_status, evidence=items,
            verified_event_dates=list(r.get("verified_event_dates") or []),
            event_lead_dates_unverified=list(r.get("event_lead_dates_unverified") or []),
        ))
    return out


def query(all_rows: list[dict], name=None, department=None, province=None, corridor=None, state=None,
          provenance=None, without_geometry=False) -> list[dict]:
    q = fold(name)
    keep = []
    for r in all_rows:
        if q and not any(q in fold(x) for x in [r["documentary_name"], r["inventory_id"], *r["name_variants"]]):
            continue
        if department and fold(r["department"]) != fold(department):
            continue
        if province and fold(r["province"]) != fold(province):
            continue
        if corridor and r["corridor"] != corridor:
            continue
        if state and state != r["suggested_state"] and state not in r["state_flags"]:
            continue
        if provenance and r["provenance"] != provenance:
            continue
        if without_geometry and r["has_reproducible_geometry"]:
            continue
        keep.append(r)
    return keep


def summary(selected: list[dict]) -> dict:
    return dict(rows=len(selected), by_provenance=dict(sorted(Counter(r["provenance"] for r in selected).items())),
                without_reproducible_geometry=sum(not r["has_reproducible_geometry"] for r in selected),
                by_suggested_state=dict(sorted(Counter(r["suggested_state"] for r in selected).items())))


def table(selected: list[dict]) -> str:
    lines = ["inventory_id\tnombre documental\tdepartamento\tprovincia\testado sugerido\tprocedencia\tgeometría"]
    for r in selected:
        lines.append("\t".join(str(x or "") for x in (
            r["inventory_id"], r["documentary_name"], r["department"], r["province"], r["suggested_state"],
            r["provenance"], "reproducible" if r["has_reproducible_geometry"] else "sin geometría reproducible")))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name"), ap.add_argument("--department"), ap.add_argument("--province")
    ap.add_argument("--corridor"), ap.add_argument("--state")
    ap.add_argument("--provenance", choices=PROVENANCE)
    ap.add_argument("--without-geometry", action="store_true")
    ap.add_argument("--format", choices=("table", "json"), default="table")
    a = ap.parse_args(argv)
    audit = load()
    selected = query(rows(audit), a.name, a.department, a.province, a.corridor, a.state, a.provenance,
                     a.without_geometry)
    if a.format == "json":
        print(json.dumps(dict(notice=NOTICE, guards=guards_of(audit), registry_id=audit.get("registry_id"),
                              summary=summary(selected), rows=selected), ensure_ascii=False, indent=1))
    else:
        print(NOTICE)
        print(json.dumps(summary(selected), ensure_ascii=False))
        print(table(selected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
