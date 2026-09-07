#!/usr/bin/env python3
"""Run the IRFEN potential-episode and continuity controllers as one durable sidecar.

The sidecar is deliberately non-operational. It reads one published
``experimental_state.json`` snapshot, advances the TEST_ONLY continuity state
at most once for that exact source snapshot, and appends an auditable history
record. It does not call the Scientific Episode Gate and cannot create alerts,
publications, messages, risk levels, or threshold changes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import detect_potential_episodes as detector
import episode_continuity_builder as continuity

ROOT = Path(__file__).resolve().parents[1]
DETECTOR_CONTRACT = ROOT / "config" / "potential_episode_contract_v01.json"
CONTINUITY_CONTRACT = ROOT / "config" / "episode_continuity_contract_v01.json"
EXPERIMENTAL = ROOT / "site" / "data" / "experimental_state.json"
POTENTIAL_OUT = ROOT / "site" / "data" / "episodes" / "shadow" / "latest.json"
CONTINUITY_OUT = ROOT / "site" / "data" / "episodes" / "continuity" / "shadow" / "latest.json"
HISTORY_OUT = ROOT / "site" / "data" / "episodes" / "continuity" / "shadow" / "history.json"


class SidecarError(RuntimeError):
    """A fail-closed sidecar contract violation."""


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SidecarError(f"missing required JSON: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SidecarError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SidecarError(f"JSON root must be an object: {path}")
    return value


def load_optional(path: Path) -> dict | None:
    if not path.exists():
        return None
    return load_json(path)


def canonical_sha256(value: Any) -> str:
    return detector.canonical_sha256(value)


def parse_time(value: str | None, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SidecarError(f"{label} missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SidecarError(f"{label} invalid: {value}") from exc
    if parsed.tzinfo is None:
        raise SidecarError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def source_key_from_experimental(experimental_path: Path, experimental: dict) -> tuple[str, str]:
    if experimental.get("production_use") is not False:
        raise SidecarError("experimental_state production_use must remain false")
    if experimental.get("production_ready") is not False:
        raise SidecarError("experimental_state production_ready must remain false")
    generated_at = experimental.get("generated_at")
    parse_time(generated_at, "experimental_state.generated_at")
    return detector.file_sha256(experimental_path), generated_at


def source_key_from_continuity(value: dict) -> tuple[str | None, str | None]:
    source = value.get("source") or {}
    return source.get("potential_source_sha256"), source.get("source_generated_at")


def source_key_from_potential(value: dict) -> tuple[str | None, str | None]:
    source = value.get("source") or {}
    return source.get("sha256"), source.get("generated_at")


def empty_history(contract: dict, now: str) -> dict:
    return {
        "version": contract.get("version"),
        "name": "IRFEN Episode Continuity Durable Shadow History",
        "created_at": now,
        "updated_at": now,
        "mode": "SHADOW_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
        "retention_policy": {
            "mode": "APPEND_ONLY",
            "deduplication_key": [
                "potential_source_sha256",
                "source_generated_at"
            ],
            "automatic_deletion": False,
            "automatic_tombstones": False,
            "main_role": "DURABLE_SOURCE_OF_TRUTH",
            "pages_role": "PUBLISHED_REPLICA_ONLY"
        },
        "record_count": 0,
        "records": []
    }


def assert_false_guards(value: dict, label: str) -> None:
    required_false = (
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "public_social_publishing",
        "scientific_candidate_forwarding_enabled"
    )
    for key in required_false:
        if value.get(key) is not False:
            raise SidecarError(f"{label}.{key} must remain false")


def validate_history(history: dict) -> None:
    assert_false_guards(history, "history")
    if history.get("mode") != "SHADOW_ONLY" or history.get("test_mode") != "TEST_ONLY":
        raise SidecarError("history must remain SHADOW_ONLY / TEST_ONLY")
    policy = history.get("retention_policy") or {}
    if policy.get("mode") != "APPEND_ONLY":
        raise SidecarError("history retention must remain APPEND_ONLY")
    if policy.get("deduplication_key") != ["potential_source_sha256", "source_generated_at"]:
        raise SidecarError("history deduplication key changed")
    if policy.get("automatic_deletion") is not False or policy.get("automatic_tombstones") is not False:
        raise SidecarError("history cannot delete or tombstone automatically")
    if policy.get("main_role") != "DURABLE_SOURCE_OF_TRUTH":
        raise SidecarError("main must remain the durable continuity source")
    if policy.get("pages_role") != "PUBLISHED_REPLICA_ONLY":
        raise SidecarError("Pages must remain a replica")
    records = history.get("records")
    if not isinstance(records, list):
        raise SidecarError("history.records must be a list")
    if history.get("record_count") != len(records):
        raise SidecarError("history.record_count mismatch")
    seen: set[tuple[str, str]] = set()
    previous_time: datetime | None = None
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise SidecarError(f"history record {index} must be an object")
        assert_false_guards(row, f"history.records[{index}]")
        key = (row.get("potential_source_sha256"), row.get("source_generated_at"))
        if not all(isinstance(item, str) and item for item in key):
            raise SidecarError(f"history record {index} has invalid source key")
        if key in seen:
            raise SidecarError(f"duplicate history source key at record {index}")
        seen.add(key)
        current_time = parse_time(key[1], f"history.records[{index}].source_generated_at")
        if previous_time is not None and current_time <= previous_time:
            raise SidecarError("history source timestamps must be strictly increasing")
        previous_time = current_time
        if row.get("sequence") != index + 1:
            raise SidecarError(f"history sequence mismatch at record {index}")
        for hash_key in ("potential_output_sha256", "continuity_output_sha256"):
            value = row.get(hash_key)
            if not isinstance(value, str) or len(value) != 64:
                raise SidecarError(f"history record {index} missing {hash_key}")


def validate_existing_state(
    potential: dict | None,
    previous: dict | None,
    history: dict | None,
    detector_contract: dict,
    continuity_contract: dict
) -> dict:
    values = (potential, previous, history)
    present = sum(value is not None for value in values)
    now = datetime.now(timezone.utc).isoformat()
    if present == 0:
        return empty_history(continuity_contract, now)
    if present != 3:
        raise SidecarError(
            "durable sidecar state is partial; potential latest, continuity latest, "
            "and continuity history must be all present or all absent"
        )

    assert potential is not None and previous is not None and history is not None
    detector.validate_output(potential, detector_contract)
    continuity.validate_output(previous, continuity_contract)
    validate_history(history)
    records = history["records"]
    if not records:
        raise SidecarError("existing durable latest files require at least one history record")
    last = records[-1]
    potential_key = source_key_from_potential(potential)
    continuity_key = source_key_from_continuity(previous)
    history_key = (last.get("potential_source_sha256"), last.get("source_generated_at"))
    if potential_key != continuity_key or continuity_key != history_key:
        raise SidecarError("durable latest/history source keys do not match")
    if last.get("potential_output_sha256") != canonical_sha256(potential):
        raise SidecarError("durable potential latest hash does not match history")
    if last.get("continuity_output_sha256") != canonical_sha256(previous):
        raise SidecarError("durable continuity latest hash does not match history")
    return deepcopy(history)


def build_history_record(potential: dict, state: dict, sequence: int) -> dict:
    source = state.get("source") or {}
    saturation = state.get("global_saturation") or {}
    zones = state.get("zones") or []
    return {
        "sequence": sequence,
        "recorded_at": state.get("generated_at"),
        "potential_source_sha256": source.get("potential_source_sha256"),
        "source_generated_at": source.get("source_generated_at"),
        "potential_output_sha256": canonical_sha256(potential),
        "continuity_output_sha256": canonical_sha256(state),
        "controller_status": state.get("status"),
        "cycle_relation": state.get("cycle_relation"),
        "global_saturation": saturation.get("level"),
        "active_like_zone_count": saturation.get("active_like_zone_count"),
        "summary": deepcopy(state.get("summary") or {}),
        "zone_lifecycle_states": {
            row.get("zone_id"): row.get("lifecycle_state")
            for row in zones
            if isinstance(row, dict) and row.get("zone_id")
        },
        "zone_transitions": {
            row.get("zone_id"): row.get("transition")
            for row in zones
            if isinstance(row, dict) and row.get("zone_id")
        },
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False
    }


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def receipt(
    action: str,
    source_hash: str,
    source_at: str,
    history_count: int,
    generated_at: str,
    **extra: Any
) -> dict:
    value = {
        "version": "0.1",
        "generated_at": generated_at,
        "mode": "SHADOW_ONLY",
        "test_mode": "TEST_ONLY",
        "action": action,
        "potential_source_sha256": source_hash,
        "source_generated_at": source_at,
        "history_record_count": history_count,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
        "alerts_created": 0,
        "publications_created": 0,
        "messages_created": 0
    }
    value.update(extra)
    return value


def run_pipeline(
    *,
    experimental_path: Path,
    detector_contract_path: Path,
    continuity_contract_path: Path,
    potential_path: Path,
    continuity_path: Path,
    history_path: Path,
    receipt_path: Path | None = None,
    generated_at: str | None = None
) -> dict:
    detector_contract = load_json(detector_contract_path)
    continuity_contract = load_json(continuity_contract_path)
    experimental = load_json(experimental_path)
    source_hash, source_at = source_key_from_experimental(experimental_path, experimental)
    now = generated_at or datetime.now(timezone.utc).isoformat()
    parse_time(now, "generated_at")

    existing_potential = load_optional(potential_path)
    previous = load_optional(continuity_path)
    existing_history = load_optional(history_path)
    history = validate_existing_state(
        existing_potential,
        previous,
        existing_history,
        detector_contract,
        continuity_contract
    )

    current_key = (source_hash, source_at)
    if previous is not None:
        previous_key = source_key_from_continuity(previous)
        previous_time = parse_time(previous_key[1], "previous source_generated_at")
        current_time = parse_time(source_at, "current source_generated_at")
        if current_key == previous_key:
            result = receipt(
                "NOOP_DUPLICATE_SOURCE",
                source_hash,
                source_at,
                len(history["records"]),
                now,
                continuity_output_sha256=canonical_sha256(previous)
            )
            if receipt_path:
                atomic_write_json(receipt_path, result)
            return result
        if current_time <= previous_time:
            raise SidecarError(
                "source snapshot is not newer than durable continuity state; "
                "the sidecar refuses to rewind or double-count"
            )

    potential = detector.build_output(experimental, detector_contract, source_hash)
    detector.validate_output(potential, detector_contract)
    if potential.get("status") != "SHADOW_EVALUATION_COMPLETE":
        raise SidecarError(
            "potential episode detector failed its global source gate: "
            + ", ".join(potential.get("global_blockers") or [])
        )

    state = continuity.build_output(
        potential,
        experimental,
        continuity_contract,
        previous,
        generated_at=now
    )
    continuity.validate_output(state, continuity_contract)
    if state.get("status") not in {
        "SHADOW_EVALUATION_COMPLETE",
        "IDEMPOTENT_REPLAY_COMPLETE"
    }:
        raise SidecarError(f"continuity controller did not complete: {state.get('status')}")
    if state.get("cycle_relation") == "IDEMPOTENT_REPLAY":
        raise SidecarError("duplicate source was not intercepted before state mutation")

    existing_keys = {
        (row.get("potential_source_sha256"), row.get("source_generated_at"))
        for row in history["records"]
    }
    if current_key in existing_keys:
        raise SidecarError("source key already exists in history but is not the durable latest record")

    history["records"].append(
        build_history_record(potential, state, len(history["records"]) + 1)
    )
    history["record_count"] = len(history["records"])
    history["updated_at"] = now
    validate_history(history)

    atomic_write_json(potential_path, potential)
    atomic_write_json(continuity_path, state)
    atomic_write_json(history_path, history)

    result = receipt(
        "APPENDED",
        source_hash,
        source_at,
        history["record_count"],
        now,
        potential_output_sha256=canonical_sha256(potential),
        continuity_output_sha256=canonical_sha256(state),
        history_output_sha256=canonical_sha256(history),
        global_saturation=(state.get("global_saturation") or {}).get("level")
    )
    if receipt_path:
        atomic_write_json(receipt_path, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experimental", type=Path, default=EXPERIMENTAL)
    parser.add_argument("--detector-contract", type=Path, default=DETECTOR_CONTRACT)
    parser.add_argument("--continuity-contract", type=Path, default=CONTINUITY_CONTRACT)
    parser.add_argument("--potential-output", type=Path, default=POTENTIAL_OUT)
    parser.add_argument("--continuity-output", type=Path, default=CONTINUITY_OUT)
    parser.add_argument("--history", type=Path, default=HISTORY_OUT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--generated-at")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_pipeline(
            experimental_path=args.experimental,
            detector_contract_path=args.detector_contract,
            continuity_contract_path=args.continuity_contract,
            potential_path=args.potential_output,
            continuity_path=args.continuity_output,
            history_path=args.history,
            receipt_path=args.receipt,
            generated_at=args.generated_at
        )
    except SidecarError as exc:
        print(f"EPISODE_SHADOW_SIDECAR_FAIL_CLOSED: {exc}")
        return 2
    print("IRFEN_EPISODE_SHADOW_SIDECAR=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
