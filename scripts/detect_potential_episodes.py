#!/usr/bin/env python3
"""Build the IRFEN potential-episode shadow state.

This component is intentionally downstream of ``experimental_state.json``.
It does not calculate risk, modify thresholds, perform scientific acceptance,
or publish anything. A POTENTIAL_EPISODE only means that an existing TEST_ONLY
recommendation is eligible for a later scientific episode review.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "potential_episode_contract_v01.json"
SOURCE_PATH = ROOT / "site" / "data" / "experimental_state.json"
OUT_PATH = ROOT / "site" / "data" / "episodes" / "shadow" / "latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def normalize_marker(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def has_explicit_stale_marker(value, markers) -> bool:
    """Return True only for explicit stale/expired/outdated status-like strings.

    No age threshold is invented here. Temporal freshness belongs to upstream
    scientific assets until a separate evidence-backed freshness contract exists.
    """
    wanted = {normalize_marker(m) for m in markers}

    def walk(obj, key=""):
        if isinstance(obj, dict):
            for child_key, child_value in obj.items():
                if walk(child_value, str(child_key)):
                    return True
            return False
        if isinstance(obj, list):
            return any(walk(item, key) for item in obj)
        if isinstance(obj, str):
            key_norm = normalize_marker(key)
            if not any(token in key_norm for token in ("STATUS", "FRESH", "VALID", "AGE")):
                return False
            value_norm = normalize_marker(obj)
            return any(marker == value_norm or marker in value_norm.split("_") for marker in wanted)
        return False

    return walk(value)


def input_gate(zone: dict, recommendation: dict, contract: dict) -> list[str]:
    gate = contract.get("candidate_input_gate") or {}
    blockers: list[str] = []

    if gate.get("require_zone_test_ready") and zone.get("test_ready") is not True:
        blockers.append("zone_not_test_ready")
    if gate.get("require_zone_production_use_false") and zone.get("production_use") is not False:
        blockers.append("zone_production_use_not_false")
    if gate.get("require_recommendation_mode_test_only") and recommendation.get("mode") != "TEST_ONLY":
        blockers.append("recommendation_mode_not_test_only")
    if gate.get("require_operational_alert_false") and recommendation.get("operational_alert") is not False:
        blockers.append("operational_alert_not_false")
    if gate.get("require_thresholds_modified_false") and recommendation.get("thresholds_modified") is not False:
        blockers.append("thresholds_modified_not_false")
    if gate.get("block_on_explicit_stale_status") and has_explicit_stale_marker(
        zone, contract.get("explicit_stale_markers") or []
    ):
        blockers.append("explicit_stale_input")

    return blockers


def deterministic_episode_id(zone_id: str, source_generated_at: str | None, source_hash: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", source_generated_at or "")[:14] or "UNDATED"
    safe_zone = re.sub(r"[^A-Z0-9]+", "-", zone_id.upper()).strip("-")
    return f"IRFEN-{safe_zone}-{timestamp}-{source_hash[:8].upper()}"


def classify_zone(zone: dict, contract: dict, source_generated_at: str | None, source_hash: str) -> dict:
    zone_id = zone.get("zone_id")
    recommendation = zone.get("test_recommendation") or {}
    code = recommendation.get("code")
    mapping = contract.get("recommendation_mapping") or {}
    mapped_state = mapping.get(code)
    blockers = input_gate(zone, recommendation, contract)
    detector_status = "PASS"

    if mapped_state is None:
        mapped_state = "NO_EPISODE"
        detector_status = "BLOCKED_UNKNOWN_RECOMMENDATION"
        blockers.append("unknown_test_recommendation")
    elif mapped_state == "POTENTIAL_EPISODE" and blockers:
        mapped_state = "NO_EPISODE"
        detector_status = "BLOCKED_INPUT_GATE"
    elif mapped_state == "NO_EPISODE" and code in set(contract.get("watch_only_codes") or []):
        detector_status = "WATCH_ONLY_NO_EPISODE"
    elif mapped_state == "NO_EPISODE":
        detector_status = "NO_TRIGGER"

    result = {
        "zone_id": zone_id,
        "name": zone.get("name"),
        "episode_state": mapped_state,
        "detector_status": detector_status,
        "watch_only": code in set(contract.get("watch_only_codes") or []),
        "source_recommendation_code": code,
        "source_reason": recommendation.get("reason"),
        "input_gate_blockers": list(dict.fromkeys(blockers)),
        "upstream_blockers": zone.get("blockers") or [],
        "source_test_ready": zone.get("test_ready"),
        "production_use": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "scientific_pass": False,
    }
    if mapped_state == "POTENTIAL_EPISODE":
        result["episode_id"] = deterministic_episode_id(zone_id, source_generated_at, source_hash)
    return result


def blocked_zone(zone_id: str, reason: str) -> dict:
    return {
        "zone_id": zone_id,
        "name": None,
        "episode_state": "NO_EPISODE",
        "detector_status": "BLOCKED",
        "watch_only": False,
        "source_recommendation_code": None,
        "source_reason": None,
        "input_gate_blockers": [reason],
        "upstream_blockers": [],
        "source_test_ready": False,
        "production_use": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "scientific_pass": False,
    }


def build_output(source: dict | None, contract: dict, source_hash: str | None = None) -> dict:
    pilots = list(contract.get("pilot_zone_ids") or [])
    source = source or {}
    source_hash = source_hash or canonical_sha256(source)
    source_generated_at = source.get("generated_at")
    global_blockers: list[str] = []

    if source.get("production_use") is not False:
        global_blockers.append("source_production_use_not_false")
    source_zones = source.get("zones")
    if not isinstance(source_zones, list):
        global_blockers.append("source_zones_missing")
        source_zones = []

    by_zone = {
        z.get("zone_id"): z
        for z in source_zones
        if isinstance(z, dict) and z.get("zone_id") in pilots
    }

    zones = []
    for zone_id in pilots:
        if global_blockers:
            zones.append(blocked_zone(zone_id, global_blockers[0]))
        elif zone_id not in by_zone:
            zones.append(blocked_zone(zone_id, "pilot_zone_missing_from_source"))
        else:
            zones.append(classify_zone(by_zone[zone_id], contract, source_generated_at, source_hash))

    candidate_count = sum(z.get("episode_state") == "POTENTIAL_EPISODE" for z in zones)
    output = {
        "contract_version": contract.get("version"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_ONLY",
        "status": "BLOCKED_SOURCE_GATE" if global_blockers else "SHADOW_EVALUATION_COMPLETE",
        "production_use": False,
        "production_ready": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "thresholds_modified": False,
        "scientific_acceptance_modified": False,
        "source": {
            "path": contract.get("source", {}).get("path"),
            "sha256": source_hash,
            "generated_at": source_generated_at,
            "production_use": source.get("production_use"),
        },
        "global_blockers": global_blockers,
        "summary": {
            "pilots_evaluated": len(zones),
            "potential_episode_count": candidate_count,
            "publications_created": 0,
            "alerts_created": 0,
        },
        "zones": zones,
        "rules": {
            "potential_episode_is_not_alert": True,
            "scientific_pass_not_implemented_here": True,
            "no_publication_path": True,
        },
    }
    return output


def validate_output(output: dict, contract: dict) -> None:
    if output.get("mode") != "SHADOW_ONLY":
        raise ValueError("mode must remain SHADOW_ONLY")
    for key in ("production_use", "production_ready", "operational_alert", "public_social_publishing"):
        if output.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    serialized = json.dumps(output, ensure_ascii=False)
    forbidden = contract.get("forbidden_output_fields") or []
    for field in forbidden:
        pattern = f'"{field}"'
        if pattern in serialized:
            raise ValueError(f"forbidden output field present: {field}")
    for zone in output.get("zones", []):
        if zone.get("episode_state") not in set(contract.get("states") or []):
            raise ValueError(f"invalid episode state for {zone.get('zone_id')}")
        if zone.get("episode_state") == "POTENTIAL_EPISODE" and zone.get("input_gate_blockers"):
            raise ValueError(f"candidate cannot bypass input gate: {zone.get('zone_id')}")
        if zone.get("operational_alert") is not False or zone.get("public_social_publishing") is not False:
            raise ValueError(f"publication/alert guard broken: {zone.get('zone_id')}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    if SOURCE_PATH.exists():
        source = load_json(SOURCE_PATH)
        source_hash = file_sha256(SOURCE_PATH)
    else:
        source = {}
        source_hash = canonical_sha256(source)

    output = build_output(source, contract, source_hash)
    validate_output(output, contract)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if output.get("status") != "SHADOW_EVALUATION_COMPLETE":
        print(f"Potential episode detector BLOCKED: {output.get('global_blockers')}")
        return 2
    print(
        "Potential episode detector SHADOW_ONLY: "
        f"{output['summary']['potential_episode_count']} candidate(s), 0 alerts, 0 publications"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
