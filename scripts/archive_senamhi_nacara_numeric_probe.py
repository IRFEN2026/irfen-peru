#!/usr/bin/env python3
"""Archiva disponibilidad y lecturas TEST_ONLY de Puente Ñácara.

Recupera versiones previas del probe desde Git para no perder intentos cuando
el JSON vivo se sobrescribe. Los fallos se conservan como fallos; nunca se
convierten en caudal cero ni en evidencia de riesgo bajo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "site/data/hydrology/senamhi_nacara_numeric_probe.json"
OUT = ROOT / "site/data/hydrology/senamhi_nacara_numeric_archive.json"
PROBE_REPO_PATH = PROBE.relative_to(ROOT).as_posix()
MAX_PROBE_RECORDS = 2000
MAX_OBSERVATIONS = 1000


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def valid_reading(probe):
    reading = probe.get("reading") if isinstance(probe, dict) else None
    if probe.get("numeric_river_state_available") is not True or not isinstance(reading, dict):
        return None
    try:
        value = float(reading.get("value"))
    except (TypeError, ValueError):
        return None
    if (
        reading.get("station_id") != "47E0415A"
        or reading.get("variable") != "CAUDAL"
        or reading.get("unit") != "m3/s"
        or value < 0
    ):
        return None
    return {**reading, "value": value}


def probe_record(probe):
    generated_at = probe.get("generated_at")
    requested_at = (probe.get("query") or {}).get("requested_observation_time")
    if not parse_time(generated_at):
        return None
    reading = valid_reading(probe)
    return {
        "generated_at": generated_at,
        "requested_observation_time": requested_at,
        "status": probe.get("status"),
        "numeric_river_state_available": reading is not None,
        "http_status": (probe.get("http") or {}).get("status"),
        "rejection_reason": probe.get("rejection_reason"),
        "value": reading.get("value") if reading else None,
        "unit": reading.get("unit") if reading else None,
        "missing_data_interpretation": "UNKNOWN_NOT_ZERO" if reading is None else None,
    }


def consecutive_metrics(observations, latest_probe_record=None):
    times = sorted({parse_time(x.get("requested_observation_time")) for x in observations} - {None})
    if not times:
        return {"longest_consecutive_hours": 0, "current_consecutive_hours": 0}
    longest = 1
    run = 1
    for previous, item in zip(times, times[1:]):
        if (item - previous).total_seconds() == 3600:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
    # "Current" must be anchored to the latest probe, not merely to the most
    # recent successful observation retained in the archive. Otherwise an old
    # isolated success remains reported as a live streak while newer probes
    # are failing, which overstates channel continuity.
    current = 0
    if latest_probe_record and latest_probe_record.get("numeric_river_state_available") is True:
        latest_requested = parse_time(latest_probe_record.get("requested_observation_time"))
        if latest_requested in times:
            current = 1
            observed = set(times)
            previous = latest_requested
            while True:
                candidate = previous - timedelta(hours=1)
                if candidate not in observed:
                    break
                current += 1
                previous = candidate
    return {"longest_consecutive_hours": longest, "current_consecutive_hours": current}


def build_archive(probes, generated_at=None):
    unique = {}
    for probe in probes:
        record = probe_record(probe)
        if record:
            unique[record["generated_at"]] = record
    records = sorted(unique.values(), key=lambda x: parse_time(x["generated_at"]))[-MAX_PROBE_RECORDS:]

    observations_by_time = {}
    source_by_generated_at = {str(p.get("generated_at")): p for p in probes if isinstance(p, dict)}
    for record in records:
        if not record["numeric_river_state_available"]:
            continue
        probe = source_by_generated_at.get(record["generated_at"], {})
        reading = valid_reading(probe)
        requested_at = record.get("requested_observation_time")
        if not reading or not parse_time(requested_at):
            continue
        observations_by_time[requested_at] = {
            "requested_observation_time": requested_at,
            "probe_generated_at": record["generated_at"],
            "station_id": reading["station_id"],
            "station_name": reading.get("station_name"),
            "variable": "CAUDAL",
            "value": reading["value"],
            "unit": "m3/s",
            "trend_code": reading.get("trend_code"),
            "response_echoes_observation_time": False,
            "time_basis": "REQUEST_SELECTOR_NOT_RESPONSE_FIELD",
            "use": "TEST_ONLY_CHANNEL_CONTINUITY_EVIDENCE",
        }
    observations = sorted(
        observations_by_time.values(),
        key=lambda x: parse_time(x["requested_observation_time"]),
    )[-MAX_OBSERVATIONS:]

    successes = sum(1 for x in records if x["numeric_river_state_available"])
    failures = len(records) - successes
    latest_success = next((x for x in reversed(records) if x["numeric_river_state_available"]), None)
    status = (
        "INTERMITTENT_OFFICIAL_NUMERIC_CHANNEL"
        if successes and failures
        else "OFFICIAL_NUMERIC_CHANNEL_OBSERVED"
        if successes
        else "NO_SUCCESSFUL_GITHUB_OBSERVATION_YET"
    )
    return {
        "version": "0.8-experimental",
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "production_use": False,
        "production_ready": False,
        "integration_mode": "TEST_ONLY",
        "station": {"id": "47E0415A", "name": "PUENTE ÑACARA", "river": "RÍO PIURA"},
        "status": status,
        "summary": {
            "probe_record_count": len(records),
            "successful_numeric_count": successes,
            "failed_or_missing_count": failures,
            "availability_pct": round(100 * successes / len(records), 1) if records else 0.0,
            "observation_count": len(observations),
            "first_probe_generated_at": records[0]["generated_at"] if records else None,
            "latest_probe_generated_at": records[-1]["generated_at"] if records else None,
            "latest_success_generated_at": latest_success["generated_at"] if latest_success else None,
            **consecutive_metrics(observations, records[-1] if records else None),
        },
        "probe_records": records,
        "observations": observations,
        "scientific_gate": {
            "status": "ACCUMULATING_TEST_ONLY_CHANNEL_EVIDENCE",
            "response_timestamp_echo_pending": True,
            "hydraulic_transfer_to_catacaos_validated": False,
            "official_threshold_promoted_to_irfen": False,
            "missing_data_rule": "A failed or absent reading is UNKNOWN, never zero flow or low risk.",
            "remaining_gap": "Confirm temporal semantics, improve GitHub access reliability, and validate travel time and hydraulic transfer from Ñácara to Bajo Piura.",
        },
    }


def git_probe_history():
    probes = []
    try:
        commits = subprocess.run(
            ["git", "log", "--format=%H", "--", PROBE_REPO_PATH],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        commits = []
    for commit in commits:
        try:
            raw = subprocess.run(
                ["git", "show", f"{commit}:{PROBE_REPO_PATH}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            probes.append(json.loads(raw))
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            continue
    return probes


def main():
    probes = git_probe_history()
    if PROBE.exists():
        probes.append(json.loads(PROBE.read_text(encoding="utf-8")))
    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding="utf-8"))
        # Retener intentos anteriores aunque un checkout superficial no conserve todo Git.
        for row in previous.get("probe_records", []):
            synthetic = {
                "generated_at": row.get("generated_at"),
                "status": row.get("status"),
                "numeric_river_state_available": row.get("numeric_river_state_available") is True,
                "rejection_reason": row.get("rejection_reason"),
                "http": {"status": row.get("http_status")},
                "query": {"requested_observation_time": row.get("requested_observation_time")},
                "reading": ({
                    "station_id": "47E0415A",
                    "station_name": "PUENTE ÑACARA",
                    "variable": "CAUDAL",
                    "value": row.get("value"),
                    "unit": row.get("unit"),
                } if row.get("numeric_river_state_available") else None),
            }
            probes.append(synthetic)
    result = build_archive(probes)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
