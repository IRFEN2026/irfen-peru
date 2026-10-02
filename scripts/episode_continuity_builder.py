#!/usr/bin/env python3
"""Assemble one continuity-controller shadow state."""
from __future__ import annotations

from datetime import datetime, timezone

from episode_continuity_common import *
from episode_continuity_inputs import *
from episode_continuity_state import *
from episode_continuity_coordination import *

def build_output(
    potential: dict,
    experimental: dict,
    contract: dict,
    previous: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    validate_contract(contract)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    source_hash, source_at = source_identity(potential)
    blockers = global_source_blockers(potential, experimental, contract)
    previous_blockers = previous_state_blockers(previous)
    if previous_blockers:
        blockers.extend(previous_blockers)
        previous = None
    relation, relation_blockers = cycle_relation(potential, previous)
    blockers = list(dict.fromkeys(blockers + relation_blockers))

    potential_by = potential_zone_index(potential)
    experimental_by = experimental_zone_index(experimental)
    previous_by = previous_zone_index(previous)
    zones = [
        transition_zone(
            zone_id,
            potential_by.get(zone_id),
            experimental_by.get(zone_id),
            previous_by.get(zone_id),
            contract,
            source_hash,
            source_at or generated_at,
            relation,
            blockers,
        )
        for zone_id in contract["pilot_zone_ids"]
    ]
    groups = build_coordination_groups(zones, previous, contract, source_hash, source_at or generated_at)
    saturation = build_global_saturation(zones, contract)
    preview = build_notification_preview(zones, saturation)

    status = "SHADOW_EVALUATION_COMPLETE"
    if blockers:
        status = "BLOCKED_RETAINED_PREVIOUS" if previous else "BLOCKED_FAIL_CLOSED"
    elif relation == "IDEMPOTENT_REPLAY":
        status = "IDEMPOTENT_REPLAY_COMPLETE"

    output = {
        "version": contract["version"],
        "name": contract["name"],
        "generated_at": generated_at,
        "mode": "SHADOW_ONLY",
        "test_mode": "TEST_ONLY",
        "status": status,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
        "thresholds_modified": False,
        "scientific_acceptance_modified": False,
        "cycle_relation": relation,
        "source": {
            "potential_episode_path": contract["sources"]["potential_episode"]["path"],
            "potential_output_sha256": canonical_sha256(potential),
            "potential_source_sha256": source_hash,
            "source_generated_at": source_at,
            "experimental_state_sha256": canonical_sha256(experimental),
            "previous_controller_state_sha256": canonical_sha256(previous) if previous else None,
        },
        "global_blockers": blockers,
        "summary": {
            "pilots_evaluated": len(zones),
            "normal_count": sum(row["lifecycle_state"] == "NORMAL" for row in zones),
            "watch_count": sum(row["lifecycle_state"] == "WATCH" for row in zones),
            "active_count": sum(row["lifecycle_state"] == "ACTIVE" for row in zones),
            "persistent_count": sum(row["lifecycle_state"] == "PERSISTENT" for row in zones),
            "recovery_count": sum(row["lifecycle_state"] == "RECOVERY" for row in zones),
            "open_continuity_episode_count": sum(bool(row.get("continuity_open")) for row in zones),
            "new_event_count": sum(row.get("transition") == "NEW_EVENT" for row in zones),
            "same_event_reactivation_count": sum(row.get("transition") == "REACTIVATED_SAME_EVENT" for row in zones),
            "event_closed_count": sum(str(row.get("transition", "")).startswith("EVENT_CLOSED") for row in zones),
            "regional_saturation": saturation["level"] == "REGIONAL_SATURATION_TEST",
            "alerts_created": 0,
            "publications_created": 0,
        },
        "zones": zones,
        "coordination_groups": groups,
        "global_saturation": saturation,
        "notification_preview": preview,
        "rules": {
            "continuity_episode_is_not_scientific_event": True,
            "coordination_cluster_is_not_shared_hydrologic_event": True,
            "recovery_is_hysteresis_not_clearance": True,
            "missing_data_is_not_no_event": True,
            "no_scientific_candidate_forwarding": True,
        },
    }
    validate_output(output, contract)
    return output
