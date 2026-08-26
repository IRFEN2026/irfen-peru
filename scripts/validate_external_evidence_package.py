#!/usr/bin/env python3
"""Validate one external-evidence package without scientific promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "site/data/validation/v08_external_evidence.json"
ALLOWED_PACKAGE_VALIDATION = {"VALID", "INVALID"}
ALLOWED_SCIENTIFIC = {"RECEIVED_UNREVIEWED", "CANDIDATE", "PARTIAL", "ACCEPTED", "REJECTED"}
MANIFEST_VERSION = "external-evidence-package-v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def package_hash(file_rows: list[dict]) -> str:
    """Canonical package hash over ordered path:sha256 pairs, excluding manifest bytes."""
    material = "\n".join(f"{row['path']}:{row['sha256']}" for row in sorted(file_rows, key=lambda r: r["path"]))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def canonical_accepted_item(ledger: dict, package_id: str, reference: dict) -> dict | None:
    """Return the canonical ACCEPTED item only when the ledger explicitly traces it to this package."""
    zone_id = reference.get("zone_id")
    evidence_id = reference.get("evidence_id")
    for pilot in ledger.get("pilots", []):
        if pilot.get("zone_id") != zone_id:
            continue
        for item in pilot.get("items", []):
            if item.get("evidence_id") != evidence_id or item.get("status") != "ACCEPTED":
                continue
            review = item.get("review") or {}
            if review.get("automatic") is not False or review.get("decision") != "ACCEPTED":
                continue
            if review.get("reviewed_at") != reference.get("reviewed_at"):
                continue
            if review.get("reviewed_by") != reference.get("reviewed_by"):
                continue
            if review.get("source_evidence_package_id") != package_id:
                continue
            return item
    return None


def validate_manifest(manifest: dict, package_dir: Path, ledger: dict | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    _require(manifest.get("manifest_version") == MANIFEST_VERSION, "manifest_version inválida", errors)
    package_id = manifest.get("evidence_package_id")
    _require(bool(package_id), "falta evidence_package_id", errors)
    _require(manifest.get("package_validation") in ALLOWED_PACKAGE_VALIDATION, "package_validation inválido", errors)
    declared_disposition = manifest.get("scientific_disposition")
    _require(declared_disposition in ALLOWED_SCIENTIFIC, "scientific_disposition inválido", errors)
    _require(bool(manifest.get("ingested_by")), "falta ingested_by", errors)
    _require(isinstance(manifest.get("provenance"), dict), "falta provenance", errors)
    technical = manifest.get("technical_coverage") or {}
    _require(isinstance(technical, dict), "falta technical_coverage", errors)
    files = manifest.get("files") or []
    _require(isinstance(files, list) and bool(files), "files debe contener al menos un archivo", errors)

    original_hashes: set[str] = set()
    computed_rows: list[dict] = []
    for row in files if isinstance(files, list) else []:
        rel = row.get("path")
        if not rel:
            errors.append("archivo sin path")
            continue
        candidate = (package_dir / rel).resolve()
        try:
            candidate.relative_to(package_dir.resolve())
        except ValueError:
            errors.append(f"ruta fuera del paquete: {rel}")
            continue
        if not candidate.is_file():
            errors.append(f"archivo faltante: {rel}")
            continue
        actual_size = candidate.stat().st_size
        actual_hash = sha256_file(candidate)
        if actual_size != row.get("size_bytes"):
            errors.append(f"size_bytes no coincide: {rel}")
        if actual_hash != row.get("sha256"):
            errors.append(f"sha256 no coincide: {rel}")
        guessed_mime = mimetypes.guess_type(row.get("original_name") or candidate.name)[0] or "application/octet-stream"
        if row.get("mime") != guessed_mime:
            errors.append(f"MIME no coincide: {rel} (declarado={row.get('mime')}, esperado={guessed_mime})")
        if row.get("is_original") is True:
            original_hashes.add(actual_hash)
            if row.get("transformation") not in (None, {}):
                errors.append(f"un original no puede declarar transformación: {rel}")
        else:
            transformation = row.get("transformation") or {}
            source_hash = transformation.get("source_sha256")
            if not source_hash:
                errors.append(f"derivado sin source_sha256: {rel}")
            elif source_hash not in original_hashes and source_hash not in {r.get("sha256") for r in files}:
                errors.append(f"source_sha256 no pertenece al paquete: {rel}")
        computed_rows.append({"path": rel, "sha256": actual_hash})

    if computed_rows:
        expected_package_hash = package_hash(computed_rows)
        if manifest.get("package_sha256") != expected_package_hash:
            errors.append("package_sha256 no coincide con el contenido")

    if technical.get("crs") is None:
        warnings.append("CRS unknown/not_provided")
    if technical.get("timezone") is None:
        warnings.append("timezone unknown/not_provided")
    if technical.get("qa_qc") is None:
        warnings.append("QA/QC not_provided")

    review = manifest.get("review") or {}
    effective_disposition = declared_disposition
    acceptance_reconciled = False
    if declared_disposition == "ACCEPTED":
        _require(review.get("automatic") is False, "ACCEPTED prohíbe revisión automática", errors)
        _require(bool(review.get("reviewer")), "ACCEPTED requiere revisor humano identificado", errors)
        _require(bool(review.get("reviewed_at")), "ACCEPTED requiere fecha de revisión", errors)
        _require(review.get("decision") == "ACCEPTED", "ACCEPTED requiere decisión explícita", errors)
        _require(bool(review.get("justification")), "ACCEPTED requiere justificación", errors)
        _require(bool(technical.get("requirement_ids")), "ACCEPTED requiere requisito IRFEN específico", errors)
        _require(review.get("requirement_fully_satisfied") is True, "ACCEPTED requiere confirmación explícita de requisito satisfecho", errors)
        reference = review.get("ledger_reference") or {}
        _require(bool(reference.get("zone_id")), "ACCEPTED requiere ledger_reference.zone_id", errors)
        _require(bool(reference.get("evidence_id")), "ACCEPTED requiere ledger_reference.evidence_id", errors)
        _require(bool(reference.get("reviewed_at")), "ACCEPTED requiere ledger_reference.reviewed_at", errors)
        _require(bool(reference.get("reviewed_by")), "ACCEPTED requiere ledger_reference.reviewed_by", errors)
        if not errors and ledger is not None:
            accepted_item = canonical_accepted_item(ledger, package_id, reference)
            acceptance_reconciled = accepted_item is not None
        if not acceptance_reconciled:
            effective_disposition = "CANDIDATE"
            warnings.append("UNRECONCILED_ACCEPTED_DECLARATION: el ledger canónico no acredita ACCEPTED para este paquete")
    elif review.get("automatic") is True and review.get("decision") == "ACCEPTED":
        errors.append("ningún proceso automático puede asignar ACCEPTED")

    valid = not errors
    if manifest.get("package_validation") == "VALID" and not valid:
        errors.append("manifiesto declara VALID pero fallan las comprobaciones estructurales")
        valid = False
    return {
        "evidence_package_id": package_id,
        "package_validation": "VALID" if valid else "INVALID",
        "declared_scientific_disposition": declared_disposition,
        "scientific_disposition": effective_disposition,
        "scientific_acceptance_reconciled": acceptance_reconciled,
        "errors": errors,
        "warnings": warnings,
    }


def validate_package(package_dir: Path, ledger_path: Path = LEDGER) -> dict:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        return {"evidence_package_id": None, "package_validation": "INVALID", "declared_scientific_disposition": None, "scientific_disposition": None, "scientific_acceptance_reconciled": False, "errors": ["manifest.json faltante"], "warnings": []}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"evidence_package_id": None, "package_validation": "INVALID", "declared_scientific_disposition": None, "scientific_disposition": None, "scientific_acceptance_reconciled": False, "errors": [f"entrada JSON inválida: {exc}"], "warnings": []}
    return validate_manifest(manifest, package_dir, ledger)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate_package(args.package_dir, args.ledger)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["package_validation"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
