#!/usr/bin/env python3
"""Apply a conservative, auditable real-world review to one shadow day.

The command never changes model inputs or recommendations. It only annotates
an existing pre-outcome snapshot with official evidence gathered later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import argparse
import json


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "site/data/validation/shadow_runs.json"
ALLOWED_LABELS = {"NONE", "EVENT", "UNCERTAIN"}
OFFICIAL_HOST_SUFFIXES = (
    "senamhi.gob.pe",
    "ana.gob.pe",
    "indeci.gob.pe",
    "gob.pe",
)


def is_official_url(url: str):
    host = (urlparse(url).hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES)


def apply_review(
    archive: dict,
    snapshot_date: str,
    label: str,
    official_sources: list[str],
    notes: str,
    verified_event: str | None = None,
    comprehensive_none_coverage: bool = False,
    reviewed_at: str | None = None,
):
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Etiqueta no permitida: {label}")
    if not official_sources or not all(is_official_url(url) for url in official_sources):
        raise ValueError("Cada revisión requiere al menos una URL institucional oficial permitida")
    if not notes.strip():
        raise ValueError("La revisión requiere notas de cobertura temporal y espacial")
    if label == "EVENT" and not (verified_event or "").strip():
        raise ValueError("EVENT requiere describir el evento oficial verificado")
    if label == "NONE" and not comprehensive_none_coverage:
        raise ValueError("NONE requiere confirmar cobertura oficial suficiente; falta de datos no equivale a NONE")
    if label == "UNCERTAIN":
        verified_event = None

    records = archive.get("records") or []
    record = next((row for row in records if row.get("snapshot_date_utc") == snapshot_date), None)
    if record is None:
        raise ValueError(f"No existe fotografía previa para {snapshot_date}")
    if record.get("production_use") is not False:
        raise ValueError("La fotografía no conserva production_use=false")

    record["outcome_verification"] = {
        "status": "REVIEWED_REAL_WORLD_OUTCOME",
        "label": label,
        "verified_event": verified_event,
        "official_source": official_sources,
        "notes": notes.strip(),
        "reviewed_at": reviewed_at or datetime.now(timezone.utc).isoformat(),
        "review_method": "POST_SNAPSHOT_OFFICIAL_EVIDENCE_REVIEW",
        "counts_toward_closeout": label in {"NONE", "EVENT"},
    }
    archive["updated_at"] = datetime.now(timezone.utc).isoformat()
    archive["record_count"] = len(records)
    archive["production_use"] = False
    archive["production_ready"] = False
    return record["outcome_verification"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Fecha UTC YYYY-MM-DD de una fotografía existente")
    parser.add_argument("--label", required=True, choices=sorted(ALLOWED_LABELS))
    parser.add_argument("--source", action="append", required=True, help="URL oficial; se puede repetir")
    parser.add_argument("--notes", required=True)
    parser.add_argument("--verified-event")
    parser.add_argument("--comprehensive-none-coverage", action="store_true")
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()

    archive = json.loads(args.archive.read_text(encoding="utf-8"))
    review = apply_review(
        archive,
        snapshot_date=args.date,
        label=args.label,
        official_sources=args.source,
        notes=args.notes,
        verified_event=args.verified_event,
        comprehensive_none_coverage=args.comprehensive_none_coverage,
    )
    args.archive.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"snapshot_date_utc": args.date, **review}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
