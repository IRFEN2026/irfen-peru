#!/usr/bin/env python3
"""Run the preregistered IRFEN continuity and saturation acceptance pilot.

The pilot uses controlled synthetic replay sequences. It validates controller
mechanics only; it does not validate hydrological skill, rainfall thresholds,
scientific acceptance, operational alerting or public communication.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from episode_continuity_replay import replay_sequence

ROOT = Path(__file__).resolve().parents[1]
PILOT_CONFIG_PATH = ROOT / "config" / "episode_continuity_pilot_v01.json"
CONTROLLER_CONTRACT_PATH = ROOT / "config" / "episode_continuity_contract_v01.json"
REPORT_PATH = ROOT / "site" / "data" / "episodes" / "continuity" / "shadow" / "pilot_report_v01.json"
PILOT_ZONE_IDS = ("san_ildefonso", "chosica", "catacaos")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def safe_marker(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def potential_row(zone_id: str, signal: str, at: str, source_hash: str, frame_index: int) -> dict:
    candidate = signal == "candidate"
    watch = signal == "watch"
    blocked = signal == "blocked"
    if signal not in {"clear", "watch", "candidate", "blocked"}:
        raise ValueError(f"unsupported signal {signal!r} for {zone_id}")

    row = {
        "zone_id": zone_id,
        "name": zone_id,
        "episode_state": "POTENTIAL_EPISODE" if candidate else "NO_EPISODE",
        "detector_status": (
            "PASS"
            if candidate
            else "WATCH_ONLY_NO_EPISODE"
            if watch
            else "BLOCKED_INPUT_GATE"
            if blocked
            else "NO_TRIGGER"
        ),
        "watch_only": watch,
        "source_recommendation_code": (
            "TEST_OBSERVED_THRESHOLD_CROSSING"
            if candidate
            else "TEST_WATCH"
            if watch
            else "TEST_NO_TRIGGER"
        ),
        "source_reason": "controlled synthetic continuity pilot",
        "input_gate_blockers": ["synthetic_pilot_blocked_input"] if blocked else [],
        "upstream_blockers": [],
        "source_test_ready": not blocked,
        "production_use": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "scientific_pass": False,
    }
    if candidate:
        compact = re.sub(r"[^0-9]", "", at)[:14]
        row["episode_id"] = (
            f"PILOT-UPSTREAM-{safe_marker(zone_id)}-{compact}-{frame_index:02d}-{source_hash[:8].upper()}"
        )
    return row


def potential_snapshot(scenario_id: str, frame_index: int, at: str, signals: dict[str, str], profiles: dict[str, str]) -> dict:
    identity = {
        "scenario_id": scenario_id,
        "frame_index": frame_index,
        "at": at,
        "signals": signals,
        "profiles": profiles,
    }
    source_hash = canonical_sha256(identity)
    return {
        "contract_version": "0.1",
        "generated_at": at,
        "mode": "SHADOW_ONLY",
        "status": "SHADOW_EVALUATION_COMPLETE",
        "production_use": False,
        "production_ready": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "thresholds_modified": False,
        "scientific_acceptance_modified": False,
        "source": {
            "path": "site/data/experimental_state.json",
            "sha256": source_hash,
            "generated_at": at,
            "production_use": False,
        },
        "global_blockers": [],
        "zones": [
            potential_row(zone_id, signals.get(zone_id, "clear"), at, source_hash, frame_index)
            for zone_id in PILOT_ZONE_IDS
        ],
    }


def experimental_snapshot(at: str, profiles: dict[str, str], frame_index: int) -> dict:
    zones = []
    for zone_offset, zone_id in enumerate(PILOT_ZONE_IDS):
        profile = profiles.get(zone_id, "complete")
        if profile not in {"complete", "partial"}:
            raise ValueError(f"unsupported temporal profile {profile!r} for {zone_id}")
        base = float(frame_index + zone_offset + 1)
        observation = {
            "rain24": round(10.0 + base, 2),
            "rain72": round(22.0 + base, 2),
            "rain7d": round(38.0 + base, 2),
        }
        temporal_features: dict[str, Any] = {}
        if profile == "complete":
            observation.update({
                "rain1h": round(1.0 + base / 10.0, 2),
                "rain3h": round(2.5 + base / 10.0, 2),
                "rain6h": round(4.5 + base / 10.0, 2),
            })
            temporal_features = {
                "wet_streak_days": min(frame_index + 1, 7),
                "antecedent_moisture": "SYNTHETIC_AVAILABLE_NOT_CALIBRATED",
                "response_rate": round(0.5 + base / 20.0, 3),
                "data_confidence": "SYNTHETIC_DECLARED_ONLY",
            }
        zones.append({
            "zone_id": zone_id,
            "production_use": False,
            "observation": observation,
            "temporal_features": temporal_features,
        })
    return {
        "version": "pilot-synthetic-0.1",
        "generated_at": at,
        "production_use": False,
        "production_ready": False,
        "zones": zones,
    }


def build_frames(scenario: dict) -> list[dict]:
    frames: list[dict] = []
    for frame_index, spec in enumerate(scenario.get("frames") or []):
        if "duplicate_of" in spec:
            duplicate_index = int(spec["duplicate_of"])
            if duplicate_index < 0 or duplicate_index >= len(frames):
                raise ValueError(f"invalid duplicate_of={duplicate_index} at frame {frame_index}")
            frames.append(deepcopy(frames[duplicate_index]))
            continue

        at = spec.get("at")
        if not isinstance(at, str):
            raise ValueError(f"frame {frame_index} is missing at")
        signals = dict(spec.get("signals") or {})
        default_profile = spec.get("temporal_profile") or "complete"
        profiles = {zone_id: default_profile for zone_id in PILOT_ZONE_IDS}
        profiles.update(spec.get("temporal_profiles_by_zone") or {})
        frames.append({
            "generated_at": at,
            "potential": potential_snapshot(
                scenario["scenario_id"], frame_index, at, signals, profiles
            ),
            "experimental": experimental_snapshot(at, profiles, frame_index),
        })
    if not frames:
        raise ValueError(f"scenario {scenario.get('scenario_id')} has no frames")
    return frames


def resolve_path(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(f"cannot descend into {part!r} within {dotted_path!r}")
    return current


def evaluate_checkpoint(replay: dict, checkpoint: dict) -> dict:
    path = checkpoint["path"]
    observed = resolve_path(replay, path)
    result = {
        "check_id": checkpoint["check_id"],
        "path": path,
    }
    if "equals" in checkpoint:
        expected = checkpoint["equals"]
        result.update({"operator": "equals", "expected": expected, "observed": observed, "passed": observed == expected})
    elif "same_as" in checkpoint:
        comparison_path = checkpoint["same_as"]
        comparison = resolve_path(replay, comparison_path)
        result.update({
            "operator": "same_as",
            "comparison_path": comparison_path,
            "passed": observed == comparison,
        })
    elif "not_equal_to" in checkpoint:
        comparison_path = checkpoint["not_equal_to"]
        comparison = resolve_path(replay, comparison_path)
        result.update({
            "operator": "not_equal_to",
            "comparison_path": comparison_path,
            "passed": observed != comparison,
        })
    elif "contains" in checkpoint:
        expected = checkpoint["contains"]
        passed = expected in observed if isinstance(observed, (list, tuple, set, str, dict)) else False
        result.update({"operator": "contains", "expected": expected, "observed": observed, "passed": passed})
    elif "set_equals" in checkpoint:
        expected = sorted(checkpoint["set_equals"])
        observed_sorted = sorted(observed)
        result.update({
            "operator": "set_equals",
            "expected": expected,
            "observed": observed_sorted,
            "passed": observed_sorted == expected,
        })
    else:
        raise ValueError(f"checkpoint {checkpoint.get('check_id')} has no supported operator")
    return result


def scenario_guards(replay: dict) -> dict:
    final_state = replay["final_state"]
    preview = final_state.get("notification_preview") or {}
    guards = {
        "production_use_false": replay.get("production_use") is False and final_state.get("production_use") is False,
        "production_ready_false": replay.get("production_ready") is False and final_state.get("production_ready") is False,
        "operational_alerting_disabled": replay.get("operational_alerting_enabled") is False and final_state.get("operational_alerting_enabled") is False,
        "public_social_publishing_disabled": replay.get("public_social_publishing") is False and final_state.get("public_social_publishing") is False,
        "scientific_candidate_forwarding_disabled": replay.get("scientific_candidate_forwarding_enabled") is False and final_state.get("scientific_candidate_forwarding_enabled") is False,
        "alerts_created_zero": replay["metrics"].get("alerts_created") == 0 and preview.get("alerts_created") == 0,
        "publications_created_zero": replay["metrics"].get("publications_created") == 0 and preview.get("publications_created") == 0,
        "messages_created_zero": preview.get("messages_created") == 0,
        "email_not_sent": preview.get("email_sent") is False,
    }
    return guards


def run_scenario(scenario: dict, controller_contract: dict) -> dict:
    replay = replay_sequence({"frames": build_frames(scenario)}, controller_contract)
    expected_metrics = scenario.get("expected_metrics") or {}
    metric_checks = {
        key: {
            "expected": expected,
            "observed": replay["metrics"].get(key),
            "passed": replay["metrics"].get(key) == expected,
        }
        for key, expected in expected_metrics.items()
    }
    checkpoints = [evaluate_checkpoint(replay, item) for item in scenario.get("checkpoints") or []]
    guards = scenario_guards(replay)
    passed = (
        all(item["passed"] for item in metric_checks.values())
        and all(item["passed"] for item in checkpoints)
        and all(guards.values())
    )
    final_state = replay["final_state"]
    return {
        "scenario_id": scenario["scenario_id"],
        "mode": scenario["mode"],
        "description": scenario["description"],
        "status": "PASS" if passed else "FAIL",
        "metrics": replay["metrics"],
        "metric_checks": metric_checks,
        "checkpoints": checkpoints,
        "guards": guards,
        "final": {
            "global_saturation": final_state["global_saturation"]["level"],
            "open_continuity_episode_count": final_state["summary"]["open_continuity_episode_count"],
            "zone_states": {
                row["zone_id"]: {
                    "lifecycle_state": row["lifecycle_state"],
                    "transition": row["transition"],
                    "continuity_open": row["continuity_open"],
                }
                for row in final_state["zones"]
            },
        },
        "timeline": replay["timeline"],
    }


def build_report(pilot_config: dict, controller_contract: dict) -> dict:
    scenarios = [run_scenario(item, controller_contract) for item in pilot_config.get("scenarios") or []]
    metric_check_count = sum(len(item["metric_checks"]) for item in scenarios)
    metric_checks_passed = sum(
        check["passed"]
        for item in scenarios
        for check in item["metric_checks"].values()
    )
    checkpoint_count = sum(len(item["checkpoints"]) for item in scenarios)
    checkpoints_passed = sum(
        check["passed"]
        for item in scenarios
        for check in item["checkpoints"]
    )
    scenario_pass_count = sum(item["status"] == "PASS" for item in scenarios)
    overall_pass = bool(scenarios) and scenario_pass_count == len(scenarios)
    interpretation = (
        pilot_config["acceptance_policy"]["interpretation_on_pass"]
        if overall_pass
        else "CONTROL_LOGIC_PILOT_FAILED"
    )
    report = {
        "version": pilot_config["version"],
        "name": pilot_config["name"],
        "generated_at": pilot_config["report_generated_at"],
        "pilot_type": pilot_config["pilot_type"],
        "mode": "SHADOW_ONLY",
        "test_mode": "TEST_ONLY",
        "status": "PASS" if overall_pass else "FAIL",
        "interpretation": interpretation,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "scientific_candidate_forwarding_enabled": False,
        "hydrological_skill_validated": False,
        "rainfall_thresholds_validated": False,
        "operational_readiness_validated": False,
        "summary": {
            "scenarios_executed": len(scenarios),
            "scenarios_passed": scenario_pass_count,
            "metric_checks_passed": metric_checks_passed,
            "metric_checks_total": metric_check_count,
            "checkpoints_passed": checkpoints_passed,
            "checkpoints_total": checkpoint_count,
            "alerts_created": sum(item["metrics"]["alerts_created"] for item in scenarios),
            "publications_created": sum(item["metrics"]["publications_created"] for item in scenarios),
        },
        "scope": pilot_config["scope"],
        "scenarios": scenarios,
        "limitations": [
            "controlled synthetic inputs do not validate hydrological detection skill",
            "cycle counts are mechanical test parameters and are not calibrated hours or days",
            "the pilot does not validate station-level simultaneity or operational staffing capacity",
            "the controller remains disconnected from the Scientific Episode Gate",
        ],
    }
    validate_report(report)
    return report


def validate_report(report: dict) -> None:
    for key in (
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "public_social_publishing",
        "scientific_candidate_forwarding_enabled",
        "hydrological_skill_validated",
        "rainfall_thresholds_validated",
        "operational_readiness_validated",
    ):
        if report.get(key) is not False:
            raise ValueError(f"pilot guard violation: {key} must remain false")
    if report["summary"]["alerts_created"] != 0 or report["summary"]["publications_created"] != 0:
        raise ValueError("pilot cannot create alerts or publications")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-config", type=Path, default=PILOT_CONFIG_PATH)
    parser.add_argument("--controller-contract", type=Path, default=CONTROLLER_CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(load_json(args.pilot_config), load_json(args.controller_contract))
    if args.check:
        if not args.output.exists():
            print(f"PILOT_REPORT_MISSING: {args.output}")
            return 2
        existing = load_json(args.output)
        if existing != report:
            print("PILOT_REPORT_OUT_OF_DATE")
            return 2
        print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
        return 0 if report["status"] == "PASS" else 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
