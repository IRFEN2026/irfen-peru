#!/usr/bin/env python3
"""Run the IRFEN potential-episode and continuity controllers as one durable sidecar.

The sidecar is deliberately non-operational. It combines one published
``experimental_state.json`` snapshot with the publication status from
``latest.json``, advances the TEST_ONLY continuity state at most once for that
exact source envelope, and appends an auditable history record. It does not
call the Scientific Episode Gate and cannot create alerts, publications,
messages, risk levels, or threshold changes.
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
DATASET_STATUS = ROOT / "site" / "data" / "latest.json"
POTENTIAL_OUT = ROOT / "site" / "data" / "episodes" / "shadow" / "latest.json"
CONTINUITY_OUT = ROOT / "site" / "data" / "episodes" / "continuity" / "shadow" / "latest.json"
HISTORY_OUT = ROOT / "site" / "data" / "episodes" / "continuity" / "shadow" / "history.json"

EXPECTED_DATASET_SOURCE = "NASA GPM IMERG Late Daily"
EXPECTED_DATASET_PRODUCT = "GPM_3IMERGDL"
DATASET_STATUSES = {"updated": "FRESH", "stale": "STALE"}


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


def file_sha256(path: Path) -> str:
    return detector.file_sha256(path)


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


def validate_dataset_status(dataset: dict) -> dict:
    if dataset.get("source") != EXPECTED_DATASET_SOURCE:
        raise SidecarError("latest.json source is not the canonical NASA IMERG source")
    if dataset.get("product") != EXPECTED_DATASET_PRODUCT:
        raise SidecarError("latest.json product is not GPM_3IMERGDL")
    version = dataset.get("product_version")
    if not isinstance(version, str) or not version.strip() or version in {"—", "DEMO"}:
        raise SidecarError("latest.json product_version is missing or demonstrative")
    status = dataset.get("operational_status")
    if status not in DATASET_STATUSES:
        raise SidecarError("latest.json operational_status must be updated or stale")
    generated_at = dataset.get("generated_at")
    last_attempt = dataset.get("last_update_attempt")
    parse_time(generated_at, "latest.json.generated_at")
    parse_time(last_attempt, "latest.json.last_update_attempt")
    return {
        "dataset_operational_status": status,
        "dataset_freshness_status": DATASET_STATUSES[status],
        "dataset_generated_at": generated_at,
        "dataset_last_update_attempt": last_attempt,
        "dataset_source": dataset.get("source"),
        "dataset_product": dataset.get("product"),
        "dataset_product_version": version,
    }


def prepare_detector_source(
    experimental_path: Path,
    experimental: dict,
    dataset_status_path: Path,
    dataset_status: dict,
) -> tuple[dict, str, str, dict]:
    if experimental.get("production_use") is not False:
        raise SidecarError("experimental_state production_use must remain false")
    if experimental.get("production_ready") is not False:
        raise SidecarError("experimental_state production_ready must remain false")
    generated_at = experimental.get("generated_at")
    parse_time(generated_at, "experimental_state.generated_at")
    zones = experimental.get("zones")
    if not isinstance(zones, list):
        raise SidecarError("experimental_state.zones must be a list")

    dataset_meta = validate_dataset_status(dataset_status)
    experimental_hash = file_sha256(experimental_path)
    dataset_hash = file_sha256(dataset_status_path)
    provenance = {
        "source_type": "EXPERIMENTAL_STATE_WITH_DATASET_STATUS_ENVELOPE",
        "experimental_state_path": "site/data/experimental_state.json",
        "experimental_state_sha256": experimental_hash,
        "dataset_status_path": "site/data/latest.json",
        "dataset_status_sha256": dataset_hash,
        **dataset_meta,
    }
    detector_source = deepcopy(experimental)
    detector_source["episode_sidecar_source"] = deepcopy(provenance)
    detector_source["dataset_freshness_status"] = dataset_meta["dataset_freshness_status"]
    detector_source["dataset_operational_status"] = dataset_meta["dataset_operational_status"]
    for index, zone in enumerate(detector_source["zones"]):
        if not isinstance(zone, dict):
            raise SidecarError(f"experimental_state.zones[{index}] must be an object")
        zone["sidecar_dataset_freshness_status"] = dataset_meta["dataset_freshness_status"]
        zone["sidecar_dataset_operational_status"] = dataset_meta["dataset_operational_status"]
        zone["sidecar_dataset_last_update_attempt"] = dataset_meta["dataset_last_update_attempt"]

    source_hash = canonical_sha256(
        {
            "experimental_state_sha256": experimental_hash,
            "dataset_status_sha256": dataset_hash,
            "source_generated_at": generated_at,
            "dataset_operational_status": dataset_meta["dataset_operational_status"],
            "dataset_last_update_attempt": dataset_meta["dataset_last_update_attempt"],
        }
    )
    return detector_source, source_hash, generated_at, provenance


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
                "source_generated_at",
            ],
            "automatic_deletion": False,
            "automatic_tombstones": False,
            "main_role": "DURABLE_SOURCE_OF_TRUTH",
            "pages_role": "PUBLISHED_REPLICA_ONLY",
        },
        "record_count": 0,
        "records": [],
    }


def assert_false_guards(value: dict, label: str) -> None:
    required_false = (
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "public_social_publishing",
        "scientific_candidate_forwarding_enabled",
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
    if policy.get("deduplication_key") != [
        "potential_source_sha256",
        "source_generated_at",
    ]:
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

        current_time = parse_time(
            key[1],
            f"history.records[{index}].source_generated_at",
        )
        if previous_time is not None and current_time <= previous_time:
            raise SidecarError("history source timestamps must be strictly increasing")
        previous_time = current_time

        if row.get("sequence") != index + 1:
            raise SidecarError(f"history sequence mismatch at record {index}")
        for hash_key in (
            "potential_output_sha256",
            "continuity_output_sha256",
            "experimental_state_sha256",
            "dataset_status_sha256",
        ):
            value = row.get(hash_key)
            if not isinstance(value, str) or len(value) != 64:
                raise SidecarError(f"history record {index} missing {hash_key}")
        if row.get("dataset_operational_status") not in DATASET_STATUSES:
            raise SidecarError(f"history record {index} has invalid dataset status")
        if row.get("dataset_freshness_status") != DATASET_STATUSES[
            row["dataset_operational_status"]
        ]:
            raise SidecarError(f"history record {index} freshness/status mismatch")


def validate_existing_state(
    potential: dict | None,
    previous: dict | None,
    history: dict | None,
    detector_contract: dict,
    continuity_contract: dict,
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
    history_key = (
        last.get("potential_source_sha256"),
        last.get("source_generated_at"),
    )
    if potential_key != continuity_key or continuity_key != history_key:
        raise SidecarError("durable latest/history source keys do not match")
    if last.get("potential_output_sha256") != canonical_sha256(potential):
        raise SidecarError("durable potential latest hash does not match history")
    if last.get("continuity_output_sha256") != canonical_sha256(previous):
        raise SidecarError("durable continuity latest hash does not match history")
    return deepcopy(history)


def build_history_record(potential: dict, state: dict, sequence: int) -> dict:
    source = state.get("source") or {}
    potential_source = potential.get("source") or {}
    saturation = state.get("global_saturation") or {}
    zones = state.get("zones") or []
    potential_zones = {
        row.get("zone_id"): row
        for row in (potential.get("zones") or [])
        if isinstance(row, dict) and row.get("zone_id")
    }
    return {
        "sequence": sequence,
        "recorded_at": state.get("generated_at"),
        "potential_source_sha256": source.get("potential_source_sha256"),
        "source_generated_at": source.get("source_generated_at"),
        "experimental_state_sha256": potential_source.get("experimental_state_sha256"),
        "dataset_status_sha256": potential_source.get("dataset_status_sha256"),
        "dataset_operational_status": potential_source.get("dataset_operational_status"),
        "dataset_freshness_status": potential_source.get("dataset_freshness_status"),
        "dataset_generated_at": potential_source.get("dataset_generated_at"),
        "dataset_last_update_attempt": potential_source.get("dataset_last_update_attempt"),
        "potential_output_sha256": canonical_sha256(potential),
        "continuity_output_sha256": canonical_sha256(state),
        "controller_status": state.get("status"),
        "cycle_relation": state.get("cycle_relation"),
        "global_saturation": saturation.get("level"),
        "active_like_zone_count": saturation.get("active_like_zone_count"),
        "summary": deepcopy(state.get("summary") or {}),
        "zone_inputs": {
            row.get("zone_id"): {
                "input_episode_state": row.get("input_episode_state"),
                "input_candidate_id": row.get("input_candidate_id"),
                "source_recommendation_code": row.get("source_recommendation_code"),
                "candidate_present": row.get("candidate_present"),
                "watch_present": row.get("watch_present"),
                "controller_status": row.get("controller_status"),
                "controller_blockers": deepcopy(row.get("controller_blockers") or []),
                "upstream_detector_status": (potential_zones.get(row.get("zone_id")) or {}).get("detector_status"),
                "upstream_input_gate_blockers": deepcopy(
                    (potential_zones.get(row.get("zone_id")) or {}).get("input_gate_blockers") or []
                ),
            }
            for row in zones
            if isinstance(row, dict) and row.get("zone_id")
        },
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
        "scientific_candidate_forwarding_enabled": False,
    }


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
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
    **extra: Any,
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
        "messages_created": 0,
    }
    value.update(extra)
    return value


def run_pipeline(
    *,
    experimental_path: Path,
    dataset_status_path: Path,
    detector_contract_path: Path,
    continuity_contract_path: Path,
    potential_path: Path,
    continuity_path: Path,
    history_path: Path,
    receipt_path: Path | None = None,
    generated_at: str | None = None,
) -> dict:
    detector_contract = load_json(detector_contract_path)
    continuity_contract = load_json(continuity_contract_path)
    experimental = load_json(experimental_path)
    dataset_status = load_json(dataset_status_path)
    detector_source, source_hash, source_at, provenance = prepare_detector_source(
        experimental_path,
        experimental,
        dataset_status_path,
        dataset_status,
    )
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
        continuity_contract,
    )

    current_key = (source_hash, source_at)
    if previous is not None:
        previous_key = source_key_from_continuity(previous)
        previous_time = parse_time(
            previous_key[1],
            "previous source_generated_at",
        )
        current_time = parse_time(source_at, "current source_generated_at")
        if current_key == previous_key:
            result = receipt(
                "NOOP_DUPLICATE_SOURCE",
                source_hash,
                source_at,
                len(history["records"]),
                now,
                dataset_operational_status=provenance["dataset_operational_status"],
                dataset_freshness_status=provenance["dataset_freshness_status"],
                continuity_output_sha256=canonical_sha256(previous),
            )
            if receipt_path:
                atomic_write_json(receipt_path, result)
            return result
        if current_time <= previous_time:
            raise SidecarError(
                "source snapshot is not newer than durable continuity state; "
                "the sidecar refuses to rewind or double-count"
            )

    potential = detector.build_output(
        detector_source,
        detector_contract,
        source_hash,
    )
    potential_source = potential.get("source") or {}
    potential_source.update(deepcopy(provenance))
    potential["source"] = potential_source
    detector.validate_output(potential, detector_contract)
    if potential.get("status") != "SHADOW_EVALUATION_COMPLETE":
        raise SidecarError(
            "potential episode detector failed its global source gate: "
            + ", ".join(potential.get("global_blockers") or [])
        )

    state = continuity.build_output(
        potential,
        detector_source,
        continuity_contract,
        previous,
        generated_at=now,
    )
    continuity.validate_output(state, continuity_contract)
    if state.get("status") not in {
        "SHADOW_EVALUATION_COMPLETE",
        "IDEMPOTENT_REPLAY_COMPLETE",
    }:
        raise SidecarError(
            f"continuity controller did not complete: {state.get('status')}"
        )
    if state.get("cycle_relation") == "IDEMPOTENT_REPLAY":
        raise SidecarError(
            "duplicate source was not intercepted before state mutation"
        )

    existing_keys = {
        (
            row.get("potential_source_sha256"),
            row.get("source_generated_at"),
        )
        for row in history["records"]
    }
    if current_key in existing_keys:
        raise SidecarError(
            "source key already exists in history but is not the durable latest record"
        )

    history["records"].append(
        build_history_record(
            potential,
            state,
            len(history["records"]) + 1,
        )
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
        dataset_operational_status=provenance["dataset_operational_status"],
        dataset_freshness_status=provenance["dataset_freshness_status"],
        potential_output_sha256=canonical_sha256(potential),
        continuity_output_sha256=canonical_sha256(state),
        history_output_sha256=canonical_sha256(history),
        global_saturation=(state.get("global_saturation") or {}).get("level"),
    )
    if receipt_path:
        atomic_write_json(receipt_path, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experimental", type=Path, default=EXPERIMENTAL)
    parser.add_argument("--dataset-status", type=Path, default=DATASET_STATUS)
    parser.add_argument(
        "--detector-contract",
        type=Path,
        default=DETECTOR_CONTRACT,
    )
    parser.add_argument(
        "--continuity-contract",
        type=Path,
        default=CONTINUITY_CONTRACT,
    )
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
            dataset_status_path=args.dataset_status,
            detector_contract_path=args.detector_contract,
            continuity_contract_path=args.continuity_contract,
            potential_path=args.potential_output,
            continuity_path=args.continuity_output,
            history_path=args.history,
            receipt_path=args.receipt,
            generated_at=args.generated_at,
        )
    except SidecarError as exc:
        print(f"EPISODE_SHADOW_SIDECAR_FAIL_CLOSED: {exc}")
        return 2
    print(
        "IRFEN_EPISODE_SHADOW_SIDECAR="
        + json.dumps(result, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
