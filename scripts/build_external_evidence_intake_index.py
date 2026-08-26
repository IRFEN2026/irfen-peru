#!/usr/bin/env python3
"""Build a read-only, fail-closed index of external evidence intake packages."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.validate_external_evidence_package import validate_package
except ModuleNotFoundError:
    from validate_external_evidence_package import validate_package

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "site/data/validation/external_evidence_intake_index.json"
CONTRACT = ROOT / "config/v08_external_validation_contract.json"
LEDGER = ROOT / "site/data/validation/v08_external_evidence.json"
EMPTY_CHECK_ROOT = ROOT / ".external_evidence_intake_check_empty"


def allowed_requirements(contract: dict) -> set[str]:
    out: set[str] = set()
    for pilot in contract.get("pilots", []):
        out.update(pilot.get("required_evidence_ids") or [])
    return out


def accepted_requirements(ledger: dict) -> set[str]:
    out: set[str] = set()
    for pilot in ledger.get("pilots", []):
        for item in pilot.get("items", []):
            if item.get("status") == "ACCEPTED":
                out.add(item.get("evidence_id"))
    return out


def build_index(packages_root: Path, contract_path: Path = CONTRACT, ledger_path: Path = LEDGER) -> dict:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    allowed = allowed_requirements(contract)
    unlocked = accepted_requirements(ledger)

    rows: list[dict] = []
    hash_to_packages: dict[str, list[str]] = defaultdict(list)
    name_to_hashes: dict[str, set[str]] = defaultdict(set)

    package_dirs = sorted({p.parent for p in packages_root.rglob("manifest.json")}) if packages_root.exists() else []
    for package_dir in package_dirs:
        validation = validate_package(package_dir, ledger_path)
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        package_id = manifest.get("evidence_package_id")
        requirement_ids = manifest.get("technical_coverage", {}).get("requirement_ids") or []
        unknown_requirements = sorted(set(requirement_ids) - allowed)
        if unknown_requirements:
            validation["package_validation"] = "INVALID"
            validation["errors"].append(f"requisitos fuera del contrato v0.8: {unknown_requirements}")

        scientific = validation.get("scientific_disposition")
        declared_scientific = validation.get("declared_scientific_disposition")
        reconciled = validation.get("scientific_acceptance_reconciled") is True
        ledger_reference = (manifest.get("review") or {}).get("ledger_reference") or {}
        referenced_requirement = ledger_reference.get("evidence_id")
        package_unlocked = (
            [referenced_requirement]
            if reconciled and referenced_requirement in unlocked and referenced_requirement in requirement_ids
            else []
        )

        file_rows = manifest.get("files") or []
        duplicate_flags = set(manifest.get("duplicate_status") or [])
        for f in file_rows:
            sha = f.get("sha256")
            name = f.get("original_name")
            if sha:
                hash_to_packages[sha].append(package_id)
            if name and sha:
                name_to_hashes[name].add(sha)

        rows.append({
            "evidence_package_id": package_id,
            "received_at": manifest.get("received_at"),
            "package_validation": validation["package_validation"],
            "declared_scientific_disposition": declared_scientific,
            "scientific_disposition": scientific,
            "scientific_acceptance_reconciled": reconciled,
            "potential_requirement_ids": sorted(set(requirement_ids) & allowed),
            "unlocked_requirement_ids": package_unlocked,
            "duplicate_status": sorted(duplicate_flags),
            "version_relation": manifest.get("version_relation"),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "files": [{"original_name": f.get("original_name"), "sha256": f.get("sha256")} for f in file_rows],
        })

    for row in rows:
        flags = set(row["duplicate_status"])
        for f in row["files"]:
            sha = f.get("sha256")
            name = f.get("original_name")
            if sha and len(set(hash_to_packages[sha])) > 1:
                flags.add("EXACT_CONTENT_DUPLICATE")
            if name and len(name_to_hashes[name]) > 1:
                flags.add("SAME_NAME_DIFFERENT_BYTES")
                relation = (row.get("version_relation") or {}).get("relation")
                if relation in {None, "NONE"}:
                    flags.add("UNDECLARED_REPLACEMENT")
        if (row.get("version_relation") or {}).get("relation") == "NEW_VERSION":
            flags.add("DECLARED_NEW_VERSION")
        row["duplicate_status"] = sorted(flags)
        row.pop("files", None)

    counts = Counter(row.get("scientific_disposition") for row in rows)
    return {
        "version": "external-evidence-intake-index-v1",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "source_contract": "config/v08_external_validation_contract.json",
        "source_ledger": "site/data/validation/v08_external_evidence.json",
        "acceptance_rule": "ACCEPTED is only a traced projection of the canonical human ledger; intake never originates acceptance",
        "summary": {
            "packages_received": len(rows),
            "packages_structurally_valid": sum(row["package_validation"] == "VALID" for row in rows),
            "candidates": counts.get("CANDIDATE", 0),
            "partials": counts.get("PARTIAL", 0),
            "accepted": sum(row["scientific_acceptance_reconciled"] for row in rows),
            "rejected": counts.get("REJECTED", 0),
            "received_unreviewed": counts.get("RECEIVED_UNREVIEWED", 0),
            "potential_requirements": sorted({r for row in rows for r in row["potential_requirement_ids"]}),
            "actually_unlocked_requirements": sorted(unlocked),
        },
        "packages": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages-root", type=Path, help="Explicit non-public root containing evidence packages")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.packages_root is None:
        if args.check:
            packages_root = EMPTY_CHECK_ROOT
        else:
            parser.error("--packages-root es obligatorio para evidencia real; no se usa site/ como raíz por defecto")
    else:
        packages_root = args.packages_root
    payload = build_index(packages_root, args.contract, args.ledger)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("external evidence intake index is stale")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
