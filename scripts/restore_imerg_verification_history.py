#!/usr/bin/env python3
"""Restore the scientific IMERG ledger from its versioned Git source.

GitHub Pages is treated only as an optional published replica. A missing,
invalid, or regressed Pages candidate can never replace the committed ledger.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

try:
    from verify_geos_against_imerg import canonical_sha256, validate_history
except ImportError:  # Imported as scripts.restore_imerg_verification_history.
    from scripts.verify_geos_against_imerg import canonical_sha256, validate_history


class HistoryRestoreError(ValueError):
    pass


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def load_bytes(path):
    payload = path.read_bytes()
    return payload, json.loads(payload.decode("utf-8"))


def require_durable_contract(history):
    durable = history.get("durable_store") or {}
    if durable.get("mode") != "GIT_VERSIONED_REPOSITORY":
        raise HistoryRestoreError("El histórico durable debe estar versionado en Git")
    if durable.get("repository_path") != "site/data/forecast/imerg_verification_history.json":
        raise HistoryRestoreError("Ruta durable del histórico IMERG inesperada")
    if durable.get("pages_role") != "OPTIONAL_PUBLISHED_REPLICA_NOT_SOURCE_OF_TRUTH":
        raise HistoryRestoreError("GitHub Pages no puede declararse fuente durable")
    validate_history(history)


def keyed(rows, fields, label):
    result = {}
    for row in rows:
        key = tuple(row.get(field) for field in fields)
        if None in key or key in result:
            raise HistoryRestoreError(f"{label} duplicado o incompleto: {key}")
        result[key] = row
    return result


def require_monotonic_replica(durable, candidate):
    """Require every durable record to remain byte-semantically represented."""
    validate_history(candidate)
    collections = (
        ("observations", ("zone_id", "sampling_method", "valid_date_utc")),
        ("source_evidence", ("evidence_id",)),
        ("withdrawals", ("withdrawal_id",)),
        ("change_log", ("event_id",)),
    )
    for name, fields in collections:
        durable_rows = keyed(durable.get(name) or [], fields, f"durable {name}")
        candidate_rows = keyed(candidate.get(name) or [], fields, f"Pages {name}")
        missing = sorted(set(durable_rows) - set(candidate_rows))
        if missing:
            raise HistoryRestoreError(f"Pages omite registros durables de {name}: {missing}")
        changed = [
            key for key, row in durable_rows.items()
            if canonical_sha256(row) != canonical_sha256(candidate_rows[key])
        ]
        if changed:
            raise HistoryRestoreError(f"Pages altera registros durables de {name}: {changed}")


def restore(durable_path, destination, pages_candidate=None, receipt_path=None):
    durable_bytes, durable = load_bytes(durable_path)
    require_durable_contract(durable)
    selected_bytes = durable_bytes
    selected = durable
    mode = "GIT_VERSIONED_DURABLE_RESTORE"
    pages_status = "UNAVAILABLE"
    pages_hash = None

    if pages_candidate is not None and pages_candidate.is_file():
        try:
            candidate_bytes, candidate = load_bytes(pages_candidate)
            pages_hash = sha256_bytes(candidate_bytes)
            require_monotonic_replica(durable, candidate)
            selected_bytes = candidate_bytes
            selected = candidate
            mode = "PAGES_MONOTONIC_REPLICA_ACCEPTED"
            pages_status = "VALID_MONOTONIC_REPLICA"
        except Exception as exc:
            pages_status = f"REJECTED:{type(exc).__name__}:{exc}"

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.restore-{os.getpid()}")
    temporary.write_bytes(selected_bytes)
    os.replace(temporary, destination)
    receipt = {
        "schema_version": "1.0.0",
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "restoration_mode": mode,
        "durable_source": {
            "path": str(durable_path),
            "sha256": sha256_bytes(durable_bytes),
            "store_mode": "GIT_VERSIONED_REPOSITORY",
        },
        "pages_candidate": {
            "path": str(pages_candidate) if pages_candidate else None,
            "status": pages_status,
            "sha256": pages_hash,
        },
        "destination": {
            "path": str(destination),
            "sha256": sha256_bytes(selected_bytes),
        },
        "scientific_fallback_used": False,
        "observation_count": len(selected.get("observations") or []),
    }
    if receipt_path:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return receipt


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--durable", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--pages-candidate", type=Path)
    parser.add_argument("--receipt", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    receipt = restore(
        args.durable, args.destination,
        pages_candidate=args.pages_candidate, receipt_path=args.receipt,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
