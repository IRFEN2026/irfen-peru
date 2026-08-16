#!/usr/bin/env python3
"""Record a conservative human review of one v0.8 external-evidence item.

This command only updates the external-evidence ledger. It never changes model
inputs, thresholds, hydraulic factors, recommendations, or production state.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import argparse
import json


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/v08_external_validation_contract.json"
LEDGER = ROOT / "site/data/validation/v08_external_evidence.json"
ALLOWED_DECISIONS = {"ACCEPTED", "REJECTED"}
OFFICIAL_HOST_SUFFIXES = (
    "senamhi.gob.pe",
    "ana.gob.pe",
    "indeci.gob.pe",
    "cenepred.gob.pe",
    "concytec.gob.pe",
    "igp.gob.pe",
    "mef.gob.pe",
    "regionpiura.gob.pe",
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


def required_items_by_zone(contract: dict):
    return {
        row.get("zone_id"): set(row.get("required_evidence_ids") or [])
        for row in contract.get("pilots", [])
    }


def apply_review(
    contract: dict,
    ledger: dict,
    zone_id: str,
    evidence_id: str,
    decision: str,
    reviewer: str,
    notes: str,
    official_sources: list[str] | None = None,
    reviewed_at: str | None = None,
    confirm_requirement_fully_satisfied: bool = False,
    replace_existing_review: bool = False,
):
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Decisión no permitida: {decision}")
    if ledger.get("production_use") is not False or contract.get("production_use") is not False:
        raise ValueError("Contrato y registro deben conservar production_use=false")
    if not reviewer.strip():
        raise ValueError("La revisión requiere el nombre o identificador del revisor humano")
    if not notes.strip():
        raise ValueError("La revisión requiere una justificación técnica")

    required = required_items_by_zone(contract)
    if evidence_id not in required.get(zone_id, set()):
        raise ValueError("El elemento no pertenece al contrato del piloto indicado")

    pilot = next((row for row in ledger.get("pilots", []) if row.get("zone_id") == zone_id), None)
    if pilot is None:
        raise ValueError(f"No existe el piloto {zone_id} en el registro")
    item = next((row for row in pilot.get("items", []) if row.get("evidence_id") == evidence_id), None)
    if item is None:
        raise ValueError(f"No existe el elemento {evidence_id} en el registro")

    review_time = parse_utc_timestamp(reviewed_at) if reviewed_at else datetime.now(timezone.utc)
    sources = list(dict.fromkeys((item.get("official_sources") or []) + (official_sources or [])))
    if not sources or not all(is_official_url(url) for url in sources):
        raise ValueError("La revisión requiere al menos una URL institucional oficial permitida")
    if decision == "ACCEPTED" and not confirm_requirement_fully_satisfied:
        raise ValueError("ACCEPTED requiere confirmar que el requisito completo está satisfecho")

    previous_review = item.get("review") or {}
    if previous_review:
        if not replace_existing_review:
            raise ValueError("El elemento ya tiene una revisión; use reemplazo explícito para corregirla")
        previous_reviewed_at = previous_review.get("reviewed_at")
        if previous_reviewed_at and review_time <= parse_utc_timestamp(previous_reviewed_at):
            raise ValueError("La corrección debe tener un reviewed_at posterior a la revisión existente")
        archived = deepcopy(previous_review)
        archived["superseded_at"] = review_time.isoformat()
        archived["superseded_status"] = item.get("status")
        item.setdefault("review_history", []).append(archived)

    item["official_sources"] = sources
    item["status"] = decision
    item["review"] = {
        "reviewed_by": reviewer.strip(),
        "reviewed_at": review_time.isoformat(),
        "automatic": False,
        "decision": decision,
        "notes": notes.strip(),
        "requirement_fully_satisfied": decision == "ACCEPTED",
    }
    if decision == "ACCEPTED":
        previous_gap = item.pop("remaining_gap", None)
        if previous_gap:
            item["resolved_gap"] = previous_gap

    required_by_zone = required_items_by_zone(contract)
    for row in ledger.get("pilots", []):
        accepted = {
            candidate.get("evidence_id")
            for candidate in row.get("items", [])
            if candidate.get("status") == "ACCEPTED"
        }
        row["status"] = (
            "EVIDENCE_ACCEPTED"
            if required_by_zone.get(row.get("zone_id"), set()) <= accepted
            else "BLOCKED"
        )
    ledger["status"] = (
        "EVIDENCE_ACCEPTED"
        if ledger.get("pilots") and all(row.get("status") == "EVIDENCE_ACCEPTED" for row in ledger["pilots"])
        else "BLOCKED"
    )
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
    return item["review"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone-id", required=True)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--decision", required=True, choices=sorted(ALLOWED_DECISIONS))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument("--source", action="append", help="URL oficial adicional; se puede repetir")
    parser.add_argument("--reviewed-at", help="Instante ISO-8601 con zona horaria")
    parser.add_argument(
        "--confirm-requirement-fully-satisfied",
        action="store_true",
        help="Confirmación humana obligatoria para ACCEPTED",
    )
    parser.add_argument("--replace-existing-review", action="store_true")
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    review = apply_review(
        contract,
        ledger,
        zone_id=args.zone_id,
        evidence_id=args.evidence_id,
        decision=args.decision,
        reviewer=args.reviewer,
        notes=args.notes,
        official_sources=args.source,
        reviewed_at=args.reviewed_at,
        confirm_requirement_fully_satisfied=args.confirm_requirement_fully_satisfied,
        replace_existing_review=args.replace_existing_review,
    )
    args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"zone_id": args.zone_id, "evidence_id": args.evidence_id, **review}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
