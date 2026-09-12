#!/usr/bin/env python3
"""IRFEN Episode Continuity and Regional Saturation Controller v0.1.

This SHADOW_ONLY / TEST_ONLY sidecar sits downstream of the Potential Episode
Detector. It tests state continuity, hysteresis, stable episode identities,
regional concurrency and digest-by-exception behaviour. It cannot create an
operational alert, a scientific pass, a publication, a risk level or a new
rainfall threshold.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "episode_continuity_contract_v01.json"
POTENTIAL_PATH = ROOT / "site" / "data" / "episodes" / "shadow" / "latest.json"
EXPERIMENTAL_PATH = ROOT / "site" / "data" / "experimental_state.json"
OUT_PATH = ROOT / "site" / "data" / "episodes" / "continuity" / "shadow" / "latest.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def parse_time(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_marker(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def deterministic_id(prefix: str, item_id: str, source_at: str | None, source_hash: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", source_at or "")[:14] or "UNDATED"
    return f"IRFEN-{prefix}-{safe_marker(item_id)}-{timestamp}-{source_hash[:8].upper()}"


def get_path(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def first_value(value: dict, paths: list[str], numeric_only: bool = False) -> tuple[Any, str | None]:
    for path in paths:
        candidate = get_path(value, path)
        if candidate is None:
            continue
        if numeric_only and not is_number(candidate):
            continue
        return candidate, path
    return None, None


def experimental_zone_index(experimental: dict) -> dict[str, dict]:
    return {
        row.get("zone_id"): row
        for row in (experimental.get("zones") or [])
        if isinstance(row, dict) and row.get("zone_id")
    }


def extract_temporal_evidence(zone: dict | None, contract: dict) -> dict:
    cfg = contract.get("temporal_evidence") or {}
    zone = zone or {}
    windows = {}
    available_count = 0
    for name, paths in (cfg.get("window_paths") or {}).items():
        value, source_path = first_value(zone, list(paths), numeric_only=True)
        if value is None:
            windows[name] = {
                "value_mm": None,
                "status": "MISSING_NOT_INFERRED",
                "source_path": None,
            }
        else:
            available_count += 1
            windows[name] = {
                "value_mm": float(value),
                "status": "AVAILABLE_UPSTREAM",
                "source_path": source_path,
            }

    context = {}
    for name, paths in (cfg.get("context_paths") or {}).items():
        value, source_path = first_value(zone, list(paths), numeric_only=False)
        context[name] = {
            "value": value,
            "status": "AVAILABLE_UPSTREAM" if value is not None else "UNKNOWN_NOT_INFERRED",
            "source_path": source_path,
        }

    expected_count = len(windows)
    completeness = round(available_count / expected_count, 4) if expected_count else 0.0
    return {
        "windows": windows,
        "context": context,
        "availability": {
            "available_window_count": available_count,
            "expected_window_count": expected_count,
            "completeness_fraction": completeness,
            "interpretation": "DATA_COMPLETENESS_ONLY_NOT_RISK_NOT_CONFIDENCE",
        },
        "missing_policy": cfg.get("missing_policy"),
        "thresholds_created": False,
        "interpolation_applied": False,
    }


def source_identity(potential: dict) -> tuple[str, str | None]:
    source = potential.get("source") or {}
    source_hash = source.get("sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source_hash):
        source_hash = canonical_sha256(potential)
    source_at = source.get("generated_at") or potential.get("generated_at")
    return source_hash.lower(), source_at


def global_source_blockers(potential: dict, experimental: dict, contract: dict) -> list[str]:
    blockers: list[str] = []
    if potential.get("mode") != contract["sources"]["potential_episode"]["required_mode"]:
        blockers.append("potential_mode_not_shadow_only")
    for key in ("production_use", "production_ready", "operational_alert", "public_social_publishing"):
        if potential.get(key) is not False:
            blockers.append(f"potential_{key}_not_false")
    if potential.get("status") == "BLOCKED_SOURCE_GATE":
        blockers.append("potential_detector_source_gate_blocked")
    if not isinstance(potential.get("zones"), list):
        blockers.append("potential_zones_missing")
    if experimental.get("production_use") is not False:
        blockers.append("experimental_production_use_not_false")
    if not isinstance(experimental.get("zones"), list):
        blockers.append("experimental_zones_missing")
    _, source_at = source_identity(potential)
    if parse_time(source_at) is None:
        blockers.append("source_generated_at_missing_or_invalid")
    return list(dict.fromkeys(blockers))


def validate_contract(contract: dict) -> None:
    for key in (
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "public_social_publishing",
        "scientific_candidate_forwarding_enabled",
    ):
        if contract.get(key) is not False:
            raise ValueError(f"contract guard violation: {key} must remain false")
    lifecycle = set(contract.get("lifecycle_states") or [])
    active_like = set(contract.get("active_like_states") or [])
    if not active_like or not active_like.issubset(lifecycle):
        raise ValueError("active_like_states must be a non-empty lifecycle subset")
    temporal = contract.get("temporal_control") or {}
    persistent_after = int(temporal.get("persistent_after_consecutive_candidates") or 0)
    recovery_after = int(temporal.get("recovery_after_consecutive_clear") or 0)
    close_after = int(temporal.get("close_after_consecutive_clear") or 0)
    same_event = int(temporal.get("same_event_reactivation_max_clear_cycles") or -1)
    if persistent_after < 2:
        raise ValueError("persistent transition must require at least two candidate cycles")
    if recovery_after != 1:
        raise ValueError("v0.1 requires recovery on the first clear cycle")
    if close_after <= recovery_after:
        raise ValueError("closure must occur after recovery")
    if same_event != close_after - 1:
        raise ValueError("same-event reactivation window must equal close_after - 1")
    pilots = set(contract.get("pilot_zone_ids") or [])
    for group in contract.get("coordination_groups") or []:
        if not set(group.get("zone_ids") or []).issubset(pilots):
            raise ValueError(f"coordination group contains a non-pilot zone: {group.get('group_id')}")
        if group.get("shared_hydrologic_event") is not False:
            raise ValueError("coordination groups cannot assert shared hydrologic events")


