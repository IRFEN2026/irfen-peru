#!/usr/bin/env python3
"""Validador estático del clean room de Pedregal, para CI.

Complementa (no reemplaza) al cargador fail-closed
(`scripts/pedregal_clean_room_loader.py`): el cargador impide el acceso en
tiempo de ejecución; este validador impide que el repositorio *llegue* a un
estado inconsistente o a un bypass del cargador, en cada commit.

Comprueba:
  1. Forma e invariantes del manifiesto y de la lista de consumidores
     (equivalente, sin depender del paquete `jsonschema`, a los schemas en
     `config/pedregal_sealed_evidence_manifest.schema.json` y
     `config/pedregal_clean_room_authorized_consumers.schema.json`).
  2. Si `safe_unblind_authorized` es `true`, que exista una decisión canónica
     verificable — nunca solo un log.
  3. Que cada consumidor autorizado apunte a la decisión vigente.
  4. Que ningún script del repo (fuera del propio cargador y de este
     validador) importe o abra directamente el `source_path` de una entrada
     sellada sin pasar por `pedregal_clean_room_loader`.
  5. Si hay entradas registradas, que el hash de integridad declarado
     coincida con el contenido real — nunca se imprime ni se usa el
     contenido, solo se compara el hash.

Este script nunca imprime el contenido sellado. Sale con código distinto de
cero si hay CUALQUIER error; las advertencias no bloquean CI pero se
imprimen para visibilidad.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "site/data/validation/phase2_sealed_evidence/pedregal/manifest.json"
CONSUMERS_PATH = ROOT / "config/pedregal_clean_room_authorized_consumers.json"
LOADER_PATH = ROOT / "scripts/pedregal_clean_room_loader.py"
SCRIPTS_DIR = ROOT / "scripts"

ERRORS: list[str] = []
WARNINGS: list[str] = []


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        ERRORS.append(f"Falta archivo requerido: {path.relative_to(ROOT)}")
        return None
    except Exception as exc:  # JSON malformado es un error de repositorio real
        ERRORS.append(f"JSON inválido en {path.relative_to(ROOT)}: {exc}")
        return None


def check_manifest_shape(manifest: dict) -> None:
    if manifest.get("version") != "pedregal-sealed-evidence-manifest-v1":
        ERRORS.append("manifest.version debe ser 'pedregal-sealed-evidence-manifest-v1'")

    policy = manifest.get("clean_room_policy", {})
    expected_policy = {
        "outcome_bearing": True,
        "sealed_from_candidate_matching_and_reranking": True,
        "protects": "PROCESS_INTEGRITY_NOT_CONFIDENTIALITY",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "requires_canonical_decision_for_unblind": True,
    }
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            ERRORS.append(f"clean_room_policy.{key} debe ser {expected!r}, es {policy.get(key)!r}")

    if manifest.get("authorized_consumers_ref") != "config/pedregal_clean_room_authorized_consumers.json":
        ERRORS.append("authorized_consumers_ref debe apuntar a config/pedregal_clean_room_authorized_consumers.json")

    if not isinstance(manifest.get("entries"), list):
        ERRORS.append("manifest.entries debe ser una lista (vacía por defecto)")


def check_unblind_authorization(manifest: dict) -> dict | None:
    authorized = manifest.get("safe_unblind_authorized")
    decision = manifest.get("canonical_unblind_decision")

    if authorized is not True and authorized is not False:
        ERRORS.append("safe_unblind_authorized debe ser exactamente true o false")
        return None

    if authorized is False:
        if decision is not None:
            WARNINGS.append(
                "safe_unblind_authorized=false con canonical_unblind_decision presente: "
                "permitido como borrador pendiente, pero no autoriza ningún acceso."
            )
        return None

    # authorized is True: aquí la barra sube.
    if not isinstance(decision, dict):
        ERRORS.append(
            "safe_unblind_authorized=true exige canonical_unblind_decision como objeto "
            "(nunca null, nunca solo una entrada de unblind_log)."
        )
        return None

    required_fields = ["decision_id", "decision_type", "decided_by_role", "decision_date", "decision_record_ref", "verifiable"]
    for field in required_fields:
        if not str(decision.get(field, "") or "").strip() and decision.get(field) is not True:
            ERRORS.append(f"canonical_unblind_decision.{field} es requerido y no puede estar vacío")

    if decision.get("decision_type") != "SAFE_UNBLIND_AUTHORIZATION":
        ERRORS.append("canonical_unblind_decision.decision_type debe ser 'SAFE_UNBLIND_AUTHORIZATION'")
    if decision.get("verifiable") is not True:
        ERRORS.append("canonical_unblind_decision.verifiable debe ser true")

    ref = str(decision.get("decision_record_ref") or "")
    is_url = ref.startswith("https://")
    is_canonical_github_url = ref.startswith("https://github.com/IRFEN2026/irfen-peru/")
    is_repo_path = (ROOT / ref).exists() if ref and not is_url else False
    if ref and is_url and not is_canonical_github_url:
        ERRORS.append(
            "canonical_unblind_decision.decision_record_ref URL debe pertenecer "
            "al repositorio canónico https://github.com/IRFEN2026/irfen-peru/."
        )
    if ref and not is_url and not is_repo_path:
        ERRORS.append(
            f"canonical_unblind_decision.decision_record_ref ('{ref}') no es una ruta "
            "existente del repositorio — no es verificable de forma independiente."
        )
    if not re.match(r"^[a-z0-9_-]+$", str(decision.get("decision_id") or "")):
        ERRORS.append("canonical_unblind_decision.decision_id debe cumplir ^[a-z0-9_-]+$")

    return decision if not ERRORS else None


def check_consumers(consumers_doc: dict, decision: dict | None) -> None:
    if consumers_doc.get("version") != "pedregal-clean-room-authorized-consumers-v1":
        ERRORS.append("authorized_consumers.version debe ser 'pedregal-clean-room-authorized-consumers-v1'")
    if consumers_doc.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK":
        ERRORS.append("authorized_consumers.missing_data_rule debe ser 'UNKNOWN_NOT_LOW_RISK'")

    consumers = consumers_doc.get("consumers", [])
    if not isinstance(consumers, list):
        ERRORS.append("authorized_consumers.consumers debe ser una lista")
        return

    decision_id = decision.get("decision_id") if decision else None
    for entry in consumers:
        cid = entry.get("consumer_id", "<sin id>")
        for field in ["consumer_id", "script_path", "purpose", "authorized_since", "canonical_decision_ref"]:
            if not str(entry.get(field, "") or "").strip():
                ERRORS.append(f"consumidor '{cid}': falta el campo requerido '{field}'")
        script_path = entry.get("script_path")
        if script_path and not (ROOT / script_path).exists():
            ERRORS.append(f"consumidor '{cid}': script_path '{script_path}' no existe en el repositorio")
        if entry.get("canonical_decision_ref") and entry.get("canonical_decision_ref") != decision_id:
            ERRORS.append(
                f"consumidor '{cid}': canonical_decision_ref ('{entry.get('canonical_decision_ref')}') "
                f"no coincide con la decisión vigente del manifiesto ('{decision_id}')."
            )

    if consumers and decision is None:
        ERRORS.append(
            "hay consumidores registrados pero el manifiesto no tiene una decisión de "
            "safe-unblind válida — ningún consumidor puede estar autorizado sin ella."
        )


def check_entries_integrity(entries: list) -> list[str]:
    """Verifica forma + hash de integridad de cada entrada registrada.
    Devuelve la lista de source_path referenciados, para el chequeo de bypass."""
    referenced_paths: list[str] = []
    seen_ids: set[str] = set()
    for entry in entries:
        eid = entry.get("evidence_id", "<sin id>")
        if eid in seen_ids:
            ERRORS.append(f"evidence_id duplicado en manifest.entries: '{eid}'")
        seen_ids.add(eid)

        for field in ["evidence_id", "source_path", "source_key_path", "sha256", "sealed_since"]:
            if not str(entry.get(field, "") or "").strip():
                ERRORS.append(f"entrada '{eid}': falta el campo requerido '{field}'")
        if entry.get("outcome_bearing") is not True:
            ERRORS.append(f"entrada '{eid}': outcome_bearing debe ser true")
        if entry.get("sealed_from_candidate_matching_and_reranking") is not True:
            ERRORS.append(f"entrada '{eid}': sealed_from_candidate_matching_and_reranking debe ser true")
        if entry.get("sha256") and not re.match(r"^[0-9a-f]{64}$", str(entry["sha256"])):
            ERRORS.append(f"entrada '{eid}': sha256 no tiene forma de hash hexadecimal de 64 caracteres")

        source_path = entry.get("source_path")
        if source_path:
            referenced_paths.append(source_path)
            full = ROOT / source_path
            key_path = str(entry.get("source_key_path", ""))
            if full.exists() and key_path and entry.get("sha256"):
                doc = load(full)
                if doc is not None:
                    node = doc
                    ok = True
                    for key in key_path.split("."):
                        if not isinstance(node, dict) or key not in node:
                            ERRORS.append(
                                f"entrada '{eid}': source_key_path '{key_path}' no existe en {source_path}"
                            )
                            ok = False
                            break
                        node = node[key]
                    if ok:
                        computed = hashlib.sha256(
                            json.dumps(node, sort_keys=True, ensure_ascii=False).encode("utf-8")
                        ).hexdigest()
                        if computed != entry["sha256"]:
                            ERRORS.append(
                                f"entrada '{eid}': sha256 no coincide con el contenido actual de "
                                f"{source_path}#{key_path} (integridad de proceso comprometida, "
                                f"no se imprime el contenido)"
                            )
            elif not full.exists():
                ERRORS.append(f"entrada '{eid}': source_path '{source_path}' no existe")
    return referenced_paths


BYPASS_IGNORE = {
    Path("scripts/pedregal_clean_room_loader.py"),
    Path("scripts/validate_pedregal_clean_room.py"),
}


def check_no_direct_bypass(referenced_paths: list[str]) -> None:
    """Ningún script fuera del loader debe abrir directamente un source_path
    sellado. Con entries vacío hoy, esto es vacuo pero queda activo para
    cuando se migre evidencia real."""
    if not referenced_paths:
        return
    for py_file in SCRIPTS_DIR.rglob("*.py"):
        try:
            rel_path = py_file.relative_to(ROOT)
        except ValueError:
            rel_path = py_file
        if rel_path in BYPASS_IGNORE:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        display_path = rel_path
        for source_path in referenced_paths:
            filename = Path(source_path).name
            if filename in text:
                ERRORS.append(
                    f"posible bypass del clean room: '{display_path}' referencia "
                    f"'{filename}' directamente en lugar de pasar por pedregal_clean_room_loader"
                )


def main() -> int:
    ERRORS.clear()
    WARNINGS.clear()
    manifest = load(MANIFEST_PATH)
    consumers_doc = load(CONSUMERS_PATH)
    if manifest is None or consumers_doc is None:
        for e in ERRORS:
            print(f"ERROR: {e}")
        return 1

    check_manifest_shape(manifest)
    decision = check_unblind_authorization(manifest)
    check_consumers(consumers_doc, decision)
    referenced_paths = check_entries_integrity(manifest.get("entries", []))
    check_no_direct_bypass(referenced_paths)

    for w in WARNINGS:
        print(f"WARNING: {w}")
    for e in ERRORS:
        print(f"ERROR: {e}")

    if ERRORS:
        print(f"\nvalidate_pedregal_clean_room: FALLÓ con {len(ERRORS)} error(es).")
        return 1
    print("validate_pedregal_clean_room: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
