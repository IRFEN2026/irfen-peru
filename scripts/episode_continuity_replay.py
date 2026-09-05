#!/usr/bin/env python3
"""Replay sealed episode sequences and calculate validation metrics."""
from __future__ import annotations

from episode_continuity_builder import *

def replay_sequence(sequence: dict, contract: dict) -> dict:
    frames = sequence.get("frames") or []
    if not isinstance(frames, list) or not frames:
        raise ValueError("replay sequence requires a non-empty frames list")
    previous = None
    timeline = []
    metrics = {
        "cycles": 0,
        "events_opened": 0,
        "events_closed": 0,
        "same_event_reactivations": 0,
        "persistent_transitions": 0,
        "upstream_candidate_id_churn_absorbed": 0,
        "maximum_concurrent_open_zones": 0,
        "regional_saturation_cycles": 0,
        "alerts_created": 0,
        "publications_created": 0,
    }
    previous_input_ids: dict[str, str | None] = {}
    previous_continuity_ids: dict[str, str | None] = {}

    for index, frame in enumerate(frames):
        potential = frame.get("potential") or {}
        experimental = frame.get("experimental") or sequence.get("experimental") or {
            "production_use": False,
            "zones": [],
        }
        generated_at = frame.get("generated_at") or (potential.get("source") or {}).get("generated_at")
        output = build_output(potential, experimental, contract, previous, generated_at)
        metrics["cycles"] += 1
        metrics["events_opened"] += output["summary"]["new_event_count"]
        metrics["events_closed"] += output["summary"]["event_closed_count"]
        metrics["same_event_reactivations"] += output["summary"]["same_event_reactivation_count"]
        metrics["persistent_transitions"] += sum(row.get("transition") == "BECAME_PERSISTENT" for row in output["zones"])
        metrics["maximum_concurrent_open_zones"] = max(
            metrics["maximum_concurrent_open_zones"], output["summary"]["open_continuity_episode_count"]
        )
        metrics["regional_saturation_cycles"] += int(output["summary"]["regional_saturation"])

        for row in output["zones"]:
            zid = row["zone_id"]
            current_input = row.get("input_candidate_id")
            current_continuity = row.get("continuity_episode_id")
            if (
                row.get("candidate_present")
                and previous_input_ids.get(zid)
                and current_input
                and current_input != previous_input_ids[zid]
                and current_continuity
                and current_continuity == previous_continuity_ids.get(zid)
            ):
                metrics["upstream_candidate_id_churn_absorbed"] += 1
            previous_input_ids[zid] = current_input
            previous_continuity_ids[zid] = current_continuity

        timeline.append({
            "cycle_index": index,
            "source_generated_at": output["source"]["source_generated_at"],
            "status": output["status"],
            "global_saturation": output["global_saturation"]["level"],
            "open_zone_ids": output["global_saturation"]["active_like_zone_ids"],
            "transitions": {row["zone_id"]: row["transition"] for row in output["zones"]},
            "lifecycle_states": {row["zone_id"]: row["lifecycle_state"] for row in output["zones"]},
        })
        previous = output

    report = {
        "version": contract["version"],
        "mode": "SHADOW_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
        "metrics": metrics,
        "timeline": timeline,
        "final_state": previous,
    }
    return report
