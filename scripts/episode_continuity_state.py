"""Per-zone continuity and hysteresis state machine."""
from __future__ import annotations

from copy import deepcopy

from episode_continuity_common import *
from episode_continuity_inputs import *

def transition_zone(
    zone_id: str,
    row: dict | None,
    experimental_zone: dict | None,
    previous_zone: dict | None,
    contract: dict,
    source_hash: str,
    source_at: str,
    relation: str,
    global_blockers: list[str],
) -> dict:
    signal = zone_signal(row)
    previous_zone = deepcopy(previous_zone or initial_zone_state(zone_id, (row or {}).get("name")))
    previous_zone.setdefault("zone_id", zone_id)
    previous_zone.setdefault("name", (row or {}).get("name"))
    temporal = extract_temporal_evidence(experimental_zone, contract)

    if global_blockers or signal["blocked"] or relation == "BLOCKED_RETAIN_PREVIOUS":
        blockers = list(global_blockers)
        if relation == "BLOCKED_RETAIN_PREVIOUS":
            blockers.append("cycle_relation_blocked")
        return retained_zone(previous_zone, signal, temporal, blockers, "BLOCKED_RETAIN_PREVIOUS")

    if relation == "IDEMPOTENT_REPLAY":
        out = retained_zone(previous_zone, signal, temporal, [], "IDEMPOTENT_REPLAY")
        out["controller_status"] = "IDEMPOTENT_NO_COUNTER_INCREMENT"
        out["controller_blockers"] = []
        return out

    cfg = contract["temporal_control"]
    persistent_after = int(cfg["persistent_after_consecutive_candidates"])
    close_after = int(cfg["close_after_consecutive_clear"])
    active_like = set(contract["active_like_states"])
    prev_state = previous_zone.get("lifecycle_state")
    if prev_state not in set(contract["lifecycle_states"]):
        return retained_zone(
            initial_zone_state(zone_id, (row or {}).get("name")),
            signal,
            temporal,
            ["previous_lifecycle_state_invalid"],
            "BLOCKED_RETAIN_PREVIOUS",
        )

    out = deepcopy(previous_zone)
    out["name"] = (row or {}).get("name") or out.get("name")
    out["controller_status"] = "EVALUATED"
    out["controller_blockers"] = []

    if signal["candidate"]:
        if prev_state in {"NORMAL", "WATCH"}:
            event_id = deterministic_id("CONT", zone_id, source_at, source_hash)
            state = "ACTIVE"
            transition = "NEW_EVENT"
            candidate_streak = 1
            open_cycle_count = 1
            persistent_reached = False
            first_seen_at = source_at
        else:
            event_id = previous_zone.get("continuity_episode_id")
            if not event_id:
                return retained_zone(
                    previous_zone,
                    signal,
                    temporal,
                    ["open_previous_state_missing_continuity_episode_id"],
                    "BLOCKED_RETAIN_PREVIOUS",
                )
            candidate_streak = 1 if prev_state == "RECOVERY" else int(previous_zone.get("candidate_streak") or 0) + 1
            open_cycle_count = int(previous_zone.get("open_cycle_count") or 0) + 1
            persistent_reached = bool(previous_zone.get("persistent_reached")) or prev_state == "PERSISTENT"
            first_seen_at = previous_zone.get("first_seen_at") or source_at
            if prev_state == "RECOVERY":
                state = "PERSISTENT" if persistent_reached else "ACTIVE"
                transition = "REACTIVATED_SAME_EVENT"
            elif persistent_reached or candidate_streak >= persistent_after:
                state = "PERSISTENT"
                transition = "BECAME_PERSISTENT" if prev_state != "PERSISTENT" else "PERSISTENT_CONTINUES"
                persistent_reached = True
            else:
                state = "ACTIVE"
                transition = "ACTIVE_CONTINUES"

        out.update({
            "lifecycle_state": state,
            "continuity_episode_id": event_id,
            "continuity_open": True,
            "candidate_streak": candidate_streak,
            "clear_streak": 0,
            "open_cycle_count": open_cycle_count,
            "persistent_reached": persistent_reached,
            "first_seen_at": first_seen_at,
            "last_candidate_at": source_at,
            "last_transition_at": source_at if transition not in {"ACTIVE_CONTINUES", "PERSISTENT_CONTINUES"} else previous_zone.get("last_transition_at"),
            "transition": transition,
        })
    else:
        if prev_state in {"NORMAL", "WATCH"}:
            state = "WATCH" if signal["watch"] else "NORMAL"
            transition = "WATCH_CONTINUES" if prev_state == state == "WATCH" else (
                "ENTERED_WATCH" if state == "WATCH" else ("WATCH_CLEARED" if prev_state == "WATCH" else "NO_CHANGE")
            )
            out.update({
                "lifecycle_state": state,
                "continuity_episode_id": None,
                "continuity_open": False,
                "candidate_streak": 0,
                "clear_streak": 0,
                "open_cycle_count": 0,
                "persistent_reached": False,
                "first_seen_at": None,
                "last_candidate_at": None,
                "last_transition_at": source_at if state != prev_state else previous_zone.get("last_transition_at"),
                "transition": transition,
            })
        elif prev_state in active_like:
            clear_streak = int(previous_zone.get("clear_streak") or 0) + 1
            if clear_streak >= close_after:
                closed_id = previous_zone.get("continuity_episode_id")
                state = "WATCH" if signal["watch"] else "NORMAL"
                out.update({
                    "lifecycle_state": state,
                    "continuity_episode_id": None,
                    "continuity_open": False,
                    "candidate_streak": 0,
                    "clear_streak": 0,
                    "open_cycle_count": 0,
                    "persistent_reached": False,
                    "first_seen_at": None,
                    "last_candidate_at": previous_zone.get("last_candidate_at"),
                    "last_transition_at": source_at,
                    "last_closed_episode_id": closed_id,
                    "last_closed_at": source_at,
                    "transition": "EVENT_CLOSED_TO_WATCH" if state == "WATCH" else "EVENT_CLOSED",
                })
            else:
                out.update({
                    "lifecycle_state": "RECOVERY",
                    "continuity_episode_id": previous_zone.get("continuity_episode_id"),
                    "continuity_open": True,
                    "candidate_streak": 0,
                    "clear_streak": clear_streak,
                    "open_cycle_count": int(previous_zone.get("open_cycle_count") or 0) + 1,
                    "persistent_reached": bool(previous_zone.get("persistent_reached")) or prev_state == "PERSISTENT",
                    "first_seen_at": previous_zone.get("first_seen_at"),
                    "last_candidate_at": previous_zone.get("last_candidate_at"),
                    "last_transition_at": source_at if prev_state != "RECOVERY" else previous_zone.get("last_transition_at"),
                    "transition": "ENTERED_RECOVERY" if prev_state != "RECOVERY" else "RECOVERY_CONTINUES",
                })
        else:  # defensive, already validated above
            return retained_zone(previous_zone, signal, temporal, ["unhandled_lifecycle_state"], "BLOCKED_RETAIN_PREVIOUS")

    out.update({
        "input_episode_state": signal.get("input_episode_state"),
        "input_candidate_id": signal.get("input_candidate_id"),
        "source_recommendation_code": signal.get("source_recommendation_code"),
        "source_reason": signal.get("source_reason"),
        "candidate_present": signal["candidate"],
        "watch_present": signal["watch"],
        "temporal_evidence": temporal,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
    })
    return out


