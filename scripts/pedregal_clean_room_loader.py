#!/usr/bin/env python3
"""Cargador fail-closed para evidencia sellada del clean room de Pedregal.

Este módulo protege INTEGRIDAD DE PROCESO, no confidencialidad: el archivo
fuente que hoy contiene el subárbol sellado de Pedregal sigue siendo legible
por cualquiera con acceso normal al repositorio. Lo que este cargador impide
es que un consumidor no autorizado obtenga ese subárbol *a través de este
módulo* sin que exista una decisión humana canónica y verificable que
autorice el safe-unblind, y sin que ese consumidor específico esté en la
lista cerrada de consumidores autorizados para esa misma decisión.

Ninguna función de este módulo retorna `None` ni datos parciales ante un
fallo de autorización o de integridad: siempre lanza una excepción explícita
de la jerarquía `CleanRoomAuthorizationError`. Quien llame a este módulo debe
dejar que esas excepciones se propaguen — nunca capturarlas para continuar
con una salida degradada silenciosa (eso violaría UNKNOWN_NOT_LOW_RISK).

Hoy, `entries` y `consumers` están vacíos por diseño (ver
`site/data/validation/phase2_sealed_evidence/pedregal/README.md`): ningún
dato real ha sido migrado todavía. Este módulo queda listo para cuando eso
ocurra, en una PR futura y separada, sin necesitar reescritura.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import inspect
import json

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "site/data/validation/phase2_sealed_evidence/pedregal/manifest.json"
CONSUMERS_PATH = ROOT / "config/pedregal_clean_room_authorized_consumers.json"


class CleanRoomAuthorizationError(Exception):
    """Base de toda denegación fail-closed del clean room de Pedregal."""


class SafeUnblindNotAuthorizedError(CleanRoomAuthorizationError):
    """El manifiesto no autoriza (todavía) un safe-unblind válido."""


class ConsumerNotAuthorizedError(CleanRoomAuthorizationError):
    """El consumidor no figura en la lista cerrada, o no coincide con la
    decisión canónica vigente en el manifiesto."""


class SealedEvidenceNotFoundError(CleanRoomAuthorizationError):
    """El `evidence_id` solicitado no existe en el manifiesto."""


class SealedEvidenceIntegrityError(CleanRoomAuthorizationError):
    """El contenido en `source_path`/`source_key_path` no coincide con el
    hash de integridad registrado — posible manipulación o desincronización."""


def _load_json(path: Path) -> dict:
    if not path.exists():
        # Un manifiesto o lista de consumidores ausente es un error de
        # despliegue/programación, no una ausencia de evidencia: se
        # propaga tal cual, nunca se interpreta como "sin restricciones".
        raise FileNotFoundError(f"Archivo requerido del clean room no encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_decision(manifest: dict) -> dict:
    decision = manifest.get("canonical_unblind_decision")
    if (
        manifest.get("safe_unblind_authorized") is not True
        or not isinstance(decision, dict)
        or decision.get("verifiable") is not True
        or not str(decision.get("decision_record_ref") or "").strip()
        or not str(decision.get("decision_id") or "").strip()
        or not str(decision.get("decided_by_role") or "").strip()
    ):
        raise SafeUnblindNotAuthorizedError(
            "safe_unblind_authorized=true exige un canonical_unblind_decision "
            "verificable con decision_id, decided_by_role y decision_record_ref "
            "no vacíos. Una entrada de unblind_log por sí sola nunca es suficiente."
        )
    return decision


def _caller_script_path() -> str:
    """Return the repository-relative path of the direct consumer.

    The path is derived at runtime instead of trusted from user input so one
    script cannot impersonate another authorized consumer by reusing its
    consumer_id.
    """
    stack = inspect.stack()
    if len(stack) < 3:
        raise ConsumerNotAuthorizedError("No se pudo determinar el script consumidor.")
    caller = Path(stack[2].filename).resolve()
    try:
        return caller.relative_to(ROOT).as_posix()
    except ValueError:
        return caller.as_posix()


def _authorized_consumer(
    consumer_id: str,
    decision_id: str,
    consumers_path: Path,
    caller_script_path: str,
) -> dict:
    consumers_doc = _load_json(consumers_path)
    for entry in consumers_doc.get("consumers", []):
        if entry.get("consumer_id") == consumer_id:
            if entry.get("canonical_decision_ref") != decision_id:
                raise ConsumerNotAuthorizedError(
                    f"El consumidor '{consumer_id}' está registrado pero su "
                    f"canonical_decision_ref ('{entry.get('canonical_decision_ref')}') "
                    f"no coincide con la decisión vigente ('{decision_id}')."
                )
            registered_script = str(entry.get("script_path") or "").replace("\\", "/")
            actual_script = str(caller_script_path or "").replace("\\", "/")
            if registered_script != actual_script:
                raise ConsumerNotAuthorizedError(
                    f"El consumidor '{consumer_id}' está autorizado únicamente para "
                    f"'{registered_script}', pero la llamada provino de '{actual_script}'. "
                    "Un script no puede suplantar a otro reutilizando su consumer_id."
                )
            return entry
    raise ConsumerNotAuthorizedError(
        f"El consumidor '{consumer_id}' no figura en la lista cerrada de "
        f"consumidores autorizados ({consumers_path})."
    )


def _find_entry(manifest: dict, evidence_id: str) -> dict:
    for entry in manifest.get("entries", []):
        if entry.get("evidence_id") == evidence_id:
            return entry
    raise SealedEvidenceNotFoundError(
        f"'{evidence_id}' no está registrado en el manifiesto del clean room "
        f"de Pedregal. Ningún dato real ha sido migrado todavía, o el id es "
        f"incorrecto."
    )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")


def load_sealed_entry(
    consumer_id: str,
    evidence_id: str,
    *,
    manifest_path: Path = MANIFEST_PATH,
    consumers_path: Path = CONSUMERS_PATH,
) -> dict:
    """Devuelve el subárbol sellado registrado como `evidence_id`, solo si:

    1. `safe_unblind_authorized` es `true` en el manifiesto, respaldado por un
       `canonical_unblind_decision` verificable (no un `unblind_log` suelto).
    2. `consumer_id` figura en la lista cerrada de consumidores autorizados,
       y su `canonical_decision_ref` coincide con la decisión vigente.
    3. `evidence_id` existe en el manifiesto.
    4. El hash SHA-256 del subárbol leído coincide con el registrado —
       protegiendo integridad de proceso, no confidencialidad.

    Cualquier fallo lanza una subclase de `CleanRoomAuthorizationError` y no
    retorna nada. No hay una ruta de "degradar a UNKNOWN y continuar": quien
    llama debe manejar el fallo explícitamente, nunca silenciarlo.
    """
    manifest = _load_json(manifest_path)
    decision = _canonical_decision(manifest)
    caller_script_path = _caller_script_path()
    _authorized_consumer(
        consumer_id,
        decision["decision_id"],
        consumers_path,
        caller_script_path,
    )
    entry = _find_entry(manifest, evidence_id)

    source_path = ROOT / entry["source_path"]
    source_doc = _load_json(source_path)
    node: Any = source_doc
    for key in str(entry["source_key_path"]).split("."):
        if not isinstance(node, dict) or key not in node:
            raise SealedEvidenceIntegrityError(
                f"source_key_path '{entry['source_key_path']}' ya no existe en "
                f"{source_path} — el manifiesto está desincronizado del origen."
            )
        node = node[key]

    computed = hashlib.sha256(_canonical_bytes(node)).hexdigest()
    if computed != entry.get("sha256"):
        raise SealedEvidenceIntegrityError(
            f"Hash de integridad no coincide para '{evidence_id}': "
            f"esperado {entry.get('sha256')}, calculado {computed}. "
            f"Esto protege integridad de proceso, no confidencialidad: "
            f"el subárbol cambió respecto a lo registrado en el manifiesto."
        )
    return node


def is_safe_unblind_authorized(*, manifest_path: Path = MANIFEST_PATH) -> bool:
    """Chequeo de solo-lectura, sin lanzar excepción, para reportes de estado
    (p. ej. el scorecard). Nunca se usa para decidir si servir evidencia —
    para eso siempre se pasa por `load_sealed_entry`."""
    manifest = _load_json(manifest_path)
    try:
        _canonical_decision(manifest)
        return True
    except SafeUnblindNotAuthorizedError:
        return False
