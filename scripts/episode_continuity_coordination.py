"""Regional coordination, saturation preview and output validation."""
from __future__ import annotations

from episode_continuity_common import *
from episode_continuity_inputs import *
from episode_continuity_state import *

def previous_group_index(previous: dict | None) -> dict[str, dict]:
    return {
        row.get("group_id"): row
        for row in ((previous or {}).get("coordination_groups") or [])
        if isinstance(row, dict) and row.get("group_id")
    }


def concurrency_level(active_count: int, total: int, minimum: int, fraction: float) -> str:
    active_fraction = active_count / total if total else 0.0
    if total >= minimum and active_count >= minimum and active_fraction >= fraction:
        return "REGIONAL_SATURATION_TEST"
    if active_count >= 2:
        return "ELEVATED_CONCURRENCY"
    if active_count == 1:
        return "LOCALIZED_ACTIVITY"
    return "NORMAL_LOAD"


def build_coordination_groups(
    zones: list[dict], previous: dict | None, contract: dict, source_hash: str, source_at: str
) -> list[dict]:
    by_zone = {row["zone_id"]: row for row in zones}
    previous_groups = previous_group_index(previous)
    active_like = set(contract["active_like_states"])
    groups = []
    for cfg in contract.get("coordination_groups") or []:
        members = [by_zone[zid] for zid in cfg["zone_ids"] if zid in by_zone]
        open_members = [row for row in members if row.get("lifecycle_state") in active_like]
        total = len(cfg["zone_ids"])
        active_count = len(open_members)
        level = concurrency_level(
            active_count,
            total,
            int(cfg["minimum_active_zones_for_saturation"]),
            float(cfg["minimum_active_fraction_for_saturation"]),
        )
        previous_group = previous_groups.get(cfg["group_id"]) or {}
        if active_count:
            cluster_id = previous_group.get("coordination_cluster_id") or deterministic_id(
                "COORD", cfg["group_id"], source_at, source_hash
            )
        else:
            cluster_id = None
        groups.append({
            "group_id": cfg["group_id"],
            "relationship": cfg["relationship"],
            "shared_hydrologic_event": False,
            "coordination_cluster_id": cluster_id,
            "cluster_open": bool(active_count),
            "concurrency_level": level,
            "zone_count": total,
            "active_like_zone_count": active_count,
            "active_like_fraction": round(active_count / total, 4) if total else 0.0,
            "active_like_zone_ids": [row["zone_id"] for row in open_members],
            "member_lifecycle_states": {row["zone_id"]: row["lifecycle_state"] for row in members},
            "interpretation": "COORDINATION_ONLY_NOT_A_SHARED_HYDROLOGIC_EVENT",
            "production_use": False,
            "operational_priority_assigned": False,
        })
    return groups


def build_global_saturation(zones: list[dict], contract: dict) -> dict:
    cfg = contract["global_saturation_control"]
    active_like = set(contract["active_like_states"])
    open_rows = [row for row in zones if row.get("lifecycle_state") in active_like]
    total = len(zones)
    active_count = len(open_rows)
    level = concurrency_level(
        active_count,
        total,
        int(cfg["minimum_active_zones_for_saturation"]),
        float(cfg["minimum_active_fraction_for_saturation"]),
    )
    return {
        "level": level,
        "zone_count": total,
        "active_like_zone_count": active_count,
        "active_like_fraction": round(active_count / total, 4) if total else 0.0,
        "active_like_zone_ids": [row["zone_id"] for row in open_rows],
        "recovery_counted_as_active_like": bool(cfg["count_recovery_as_active_like_to_avoid_flicker"]),
        "operational_priority_assigned": False,
        "production_use": False,
    }


def transition_exceptions(zones: list[dict]) -> list[dict]:
    silent = {"NO_CHANGE", "WATCH_CONTINUES", "ACTIVE_CONTINUES", "PERSISTENT_CONTINUES", "RECOVERY_CONTINUES", "IDEMPOTENT_REPLAY"}
    return [
        {
            "zone_id": row["zone_id"],
            "transition": row.get("transition"),
            "lifecycle_state": row.get("lifecycle_state"),
            "continuity_episode_id": row.get("continuity_episode_id") or row.get("last_closed_episode_id"),
        }
        for row in zones
        if row.get("transition") not in silent
    ]


def build_notification_preview(zones: list[dict], saturation: dict) -> dict:
    if saturation["level"] == "REGIONAL_SATURATION_TEST":
        mode = "ONE_REGIONAL_DIGEST_PREVIEW_NO_POINT_MESSAGES"
    elif saturation["level"] in {"ELEVATED_CONCURRENCY", "LOCALIZED_ACTIVITY"}:
        mode = "EXCEPTION_DIGEST_PREVIEW"
    else:
        mode = "NO_MESSAGE_PREVIEW"
    open_count = saturation["active_like_zone_count"]
    return {
        "mode": mode,
        "exceptions": transition_exceptions(zones),
        "point_messages_that_would_be_suppressed_in_saturation": max(open_count - 1, 0) if saturation["level"] == "REGIONAL_SATURATION_TEST" else 0,
        "messages_created": 0,
        "alerts_created": 0,
        "publications_created": 0,
        "email_sent": False,
        "preview_only": True,
    }


def validate_output(output: dict, contract: dict) -> None:
    for key in (
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "public_social_publishing",
        "scientific_candidate_forwarding_enabled",
    ):
        if output.get(key) is not False:
            raise ValueError(f"guard violation: {key} must remain false")

    lifecycle_states = set(contract["lifecycle_states"])
    active_like = set(contract["active_like_states"])
    seen_ids = set()
    for row in output.get("zones") or []:
        state = row.get("lifecycle_state")
        if state not in lifecycle_states:
            raise ValueError(f"invalid lifecycle state: {state}")
        is_open = state in active_like
        if bool(row.get("continuity_open")) != is_open:
            raise ValueError(f"continuity_open mismatch for {row.get('zone_id')}")
        event_id = row.get("continuity_episode_id")
        if is_open and not event_id:
            raise ValueError(f"open state missing episode id: {row.get('zone_id')}")
        if not is_open and event_id is not None:
            raise ValueError(f"closed state retained episode id: {row.get('zone_id')}")
        if event_id:
            if event_id in seen_ids:
                raise ValueError("continuity episode ids must be unique per zone")
            seen_ids.add(event_id)
        for key in (
            "production_use",
            "production_ready",
            "operational_alerting_enabled",
            "public_social_publishing",
            "scientific_candidate_forwarding_enabled",
        ):
            if row.get(key) is not False:
                raise ValueError(f"zone guard violation: {key}")

    for group in output.get("coordination_groups") or []:
        if group.get("shared_hydrologic_event") is not False:
            raise ValueError("coordination group cannot assert a shared hydrologic event")
        if group.get("operational_priority_assigned") is not False:
            raise ValueError("controller cannot assign operational priority")

    preview = output.get("notification_preview") or {}
    for key in ("messages_created", "alerts_created", "publications_created"):
        if preview.get(key) != 0:
            raise ValueError(f"notification preview guard violation: {key}")
    if preview.get("email_sent") is not False:
        raise ValueError("controller cannot send email")

    forbidden = set(contract.get("forbidden_output_fields") or [])

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            overlap = forbidden.intersection(value)
            if overlap:
                raise ValueError(f"forbidden output fields: {sorted(overlap)}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(output)


