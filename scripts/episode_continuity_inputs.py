"""Input validation, ordering and guarded source interpretation."""
from __future__ import annotations

from copy import deepcopy

from episode_continuity_common import *

def previous_state_blockers(previous: dict | None) -> list[str]:
    if not previous:
        return []
    blockers = []
    if previous.get("mode") != "SHADOW_ONLY":
        blockers.append("previous_mode_not_shadow_only")
    for key in (
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "public_social_publishing",
        "scientific_candidate_forwarding_enabled",
    ):
        if previous.get(key) is not False:
            blockers.append(f"previous_{key}_not_false")
    if not isinstance(previous.get("zones"), list):
        blockers.append("previous_zones_missing")
    return blockers


def cycle_relation(potential: dict, previous: dict | None) -> tuple[str, list[str]]:
    if not previous:
        return "NEW_SOURCE", []
    current_hash, current_at = source_identity(potential)
    previous_source = previous.get("source") or {}
    previous_hash = previous_source.get("potential_source_sha256")
    previous_at = previous_source.get("source_generated_at")

    if current_hash == previous_hash:
        if current_at == previous_at:
            return "IDEMPOTENT_REPLAY", []
        return "BLOCKED_RETAIN_PREVIOUS", ["same_source_hash_different_timestamp"]

    current_time = parse_time(current_at)
    previous_time = parse_time(previous_at)
    if current_time is None or previous_time is None:
        return "BLOCKED_RETAIN_PREVIOUS", ["source_order_cannot_be_verified"]
    if current_time < previous_time:
        return "BLOCKED_RETAIN_PREVIOUS", ["out_of_order_source"]
    if current_time == previous_time and current_hash != previous_hash:
        return "BLOCKED_RETAIN_PREVIOUS", ["same_timestamp_different_source_hash"]
    return "NEW_SOURCE", []


def potential_zone_index(potential: dict) -> dict[str, dict]:
    return {
        row.get("zone_id"): row
        for row in (potential.get("zones") or [])
        if isinstance(row, dict) and row.get("zone_id")
    }


def previous_zone_index(previous: dict | None) -> dict[str, dict]:
    return {
        row.get("zone_id"): row
        for row in ((previous or {}).get("zones") or [])
        if isinstance(row, dict) and row.get("zone_id")
    }


def initial_zone_state(zone_id: str, name: str | None = None) -> dict:
    return {
        "zone_id": zone_id,
        "name": name,
        "lifecycle_state": "NORMAL",
        "continuity_episode_id": None,
        "continuity_open": False,
        "candidate_streak": 0,
        "clear_streak": 0,
        "open_cycle_count": 0,
        "persistent_reached": False,
        "first_seen_at": None,
        "last_candidate_at": None,
        "last_transition_at": None,
        "last_closed_episode_id": None,
        "last_closed_at": None,
    }


def zone_signal(row: dict | None) -> dict:
    if not isinstance(row, dict):
        return {
            "candidate": False,
            "watch": False,
            "blocked": True,
            "blockers": ["pilot_zone_missing_from_potential_detector"],
            "input_episode_state": None,
            "input_candidate_id": None,
            "source_recommendation_code": None,
        }

    blockers = []
    for key in ("production_use", "operational_alert", "public_social_publishing", "scientific_pass"):
        if row.get(key) is not False:
            blockers.append(f"zone_{key}_not_false")
    state = row.get("episode_state")
    if state not in {"NO_EPISODE", "POTENTIAL_EPISODE"}:
        blockers.append("unknown_input_episode_state")
    detector_status = str(row.get("detector_status") or "")
    input_gate_blockers = row.get("input_gate_blockers") or []
    if detector_status.startswith("BLOCKED") or input_gate_blockers:
        blockers.append("upstream_detector_blocked")

    candidate = state == "POTENTIAL_EPISODE" and not blockers
    watch = bool(row.get("watch_only")) and state == "NO_EPISODE" and not blockers
    return {
        "candidate": candidate,
        "watch": watch,
        "blocked": bool(blockers),
        "blockers": list(dict.fromkeys(blockers)),
        "input_episode_state": state,
        "input_candidate_id": row.get("episode_id"),
        "source_recommendation_code": row.get("source_recommendation_code"),
        "source_reason": row.get("source_reason"),
    }


def retained_zone(prev: dict, signal: dict, temporal: dict, blockers: list[str], relation: str) -> dict:
    out = deepcopy(prev)
    out.update({
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
        "input_episode_state": signal.get("input_episode_state"),
        "input_candidate_id": signal.get("input_candidate_id"),
        "source_recommendation_code": signal.get("source_recommendation_code"),
        "source_reason": signal.get("source_reason"),
        "candidate_present": signal.get("candidate", False),
        "watch_present": signal.get("watch", False),
        "transition": relation,
        "controller_status": "BLOCKED_RETAINED_PREVIOUS",
        "controller_blockers": list(dict.fromkeys(blockers + signal.get("blockers", []))),
        "temporal_evidence": temporal,
    })
    return out


