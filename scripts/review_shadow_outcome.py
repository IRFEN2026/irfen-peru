#!/usr/bin/env python3
"""Apply a conservative, auditable real-world review to one shadow day.

The command never changes model inputs or recommendations. It only annotates
an existing pre-outcome snapshot with official evidence gathered later.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import argparse
import json

try:
    from archive_shadow_validation import validate_shadow_integrity
except ImportError:  # Imported as scripts.review_shadow_outcome in unit tests.
    from scripts.archive_shadow_validation import validate_shadow_integrity


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


def parse_utc_timestamp(value: str):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at requiere zona horaria explícita")
    return parsed.astimezone(timezone.utc)


def review_window_closed_at(snapshot_date: str):
    day = date.fromisoformat(snapshot_date)
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)


def apply_review(
    archive: dict,
    snapshot_date: str,
    label: str,
    official_sources: list[str],
    notes: str,
    verified_event: str | None = None,
    reviewed_by: str | None = None,
    comprehensive_none_coverage: bool = False,
    reviewed_at: str | None = None,
    replace_existing_review: bool = False,
):
    integrity_before = validate_shadow_integrity(archive.get("records") or [])
    if not integrity_before["valid"]:
        raise ValueError(
            "La revisión se bloquea porque la evidencia previa no conserva integridad: "
            + ", ".join(integrity_before["errors"])
        )
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
    if label in {"EVENT", "NONE"} and not (reviewed_by or "").strip():
        raise ValueError("EVENT/NONE requiere identificar al revisor humano")
    if label == "UNCERTAIN":
        verified_event = None

    records = archive.get("records") or []
    record = next((row for row in records if row.get("snapshot_date_utc") == snapshot_date), None)
    if record is None:
        raise ValueError(f"No existe fotografía previa para {snapshot_date}")
    if record.get("production_use") is not False:
        raise ValueError("La fotografía no conserva production_use=false")

    review_time = parse_utc_timestamp(reviewed_at) if reviewed_at else datetime.now(timezone.utc)
    window_closed_at = review_window_closed_at(snapshot_date)
    if review_time < window_closed_at:
        raise ValueError("La jornada UTC aún no ha cerrado; no se permite revisar un resultado parcial")

    previous_review = record.get("outcome_verification") or {}
    previous_status = previous_review.get("status")
    if previous_status and previous_status != "PENDING_REAL_WORLD_OUTCOME_REVIEW":
        if not replace_existing_review:
            raise ValueError(
                "La fotografía ya tiene una revisión; use reemplazo explícito para corregirla"
            )
        previous_reviewed_at = previous_review.get("reviewed_at")
        if previous_reviewed_at and review_time <= parse_utc_timestamp(previous_reviewed_at):
            raise ValueError("La corrección debe tener un reviewed_at posterior a la revisión existente")
        archived_review = deepcopy(previous_review)
        archived_review["superseded_at"] = review_time.isoformat()
        record.setdefault("outcome_verification_history", []).append(archived_review)

    record["outcome_verification"] = {
        "status": "REVIEWED_REAL_WORLD_OUTCOME",
        "label": label,
        "verified_event": verified_event,
        "official_source": official_sources,
        "notes": notes.strip(),
        "reviewed_at": review_time.isoformat(),
        "reviewed_by": (reviewed_by or "").strip() or None,
        "automatic": False,
        "review_window_closed_utc": window_closed_at.isoformat(),
        "review_method": "POST_SNAPSHOT_OFFICIAL_EVIDENCE_REVIEW",
        "comprehensive_none_coverage": label == "NONE" and comprehensive_none_coverage,
        "counts_toward_closeout": label in {"NONE", "EVENT"},
    }
    archive["updated_at"] = datetime.now(timezone.utc).isoformat()
    archive["record_count"] = len(records)
    archive["production_use"] = False
    archive["production_ready"] = False
    integrity_after = validate_shadow_integrity(records)
    if not integrity_after["valid"]:
        raise ValueError(
            "La revisión alteró evidencia previa protegida: "
            + ", ".join(integrity_after["errors"])
        )
    return record["outcome_verification"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Fecha UTC YYYY-MM-DD de una fotografía existente")
    parser.add_argument("--label", required=True, choices=sorted(ALLOWED_LABELS))
    parser.add_argument("--source", action="append", required=True, help="URL oficial; se puede repetir")
    parser.add_argument("--notes", required=True)
    parser.add_argument("--verified-event")
    parser.add_argument("--reviewed-by", required=True, help="Nombre o identificador del revisor humano")
    parser.add_argument("--comprehensive-none-coverage", action="store_true")
    parser.add_argument(
        "--replace-existing-review",
        action="store_true",
        help="Corrige una revisión previa y conserva su versión en el historial",
    )
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
        reviewed_by=args.reviewed_by,
        comprehensive_none_coverage=args.comprehensive_none_coverage,
        replace_existing_review=args.replace_existing_review,
    )
    args.archive.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"snapshot_date_utc": args.date, **review}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
