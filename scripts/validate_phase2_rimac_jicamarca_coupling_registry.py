#!/usr/bin/env python3
"""Validate the unified fail-closed Rimac/Jicamarca collector-coupling registry."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/phase2_rimac_jicamarca_coupling_registry_v0_1.json"
RIMAC = ROOT / "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_2.json"
JIC = ROOT / "config/phase2_jicamarca_collector_coupling_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

EXPECTED = {
    "cashahuacra",
    "shingolay",
    "quirio",
    "pedregal_san_antonio",
    "huaycoloro",
    "rio_seco",
    "canto_grande_upper_branch",
    "media_luna",
}

NULL_FIELDS = ("travel_time_tau", "q_i_t", "receiver_response")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require_safe(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise AssertionError(f"{label}:{key}:guard_drift")


def by_id(rows):
    return {row["local_unit_id"]: row for row in rows}


def validate_registry(reg: dict, rimac: dict, jic: dict) -> None:
    require_safe(reg, "registry")
    require_safe(rimac, "rimac")
    require_safe(jic, "jicamarca")

    units = by_id(reg.get("local_units") or [])
    assert set(units) == EXPECTED
    assert len(units) == 8

    rimac_rows = by_id(rimac.get("tributaries") or [])
    jic_rows = by_id(jic.get("tributaries") or [])

    for unit_id in ("cashahuacra", "shingolay", "quirio", "pedregal_san_antonio"):
        row = units[unit_id]
        source = rimac_rows[unit_id]
        assert row["source_contract"] == "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_2.json"
        assert row["collector_effect_state"] == source["collector_effect_state"]
        assert row["connectivity"] == source["connectivity"]
        assert row["validation_status"] == source["validation_status"]
        for field in NULL_FIELDS:
            assert row.get(field) is None

    for unit_id in ("huaycoloro", "rio_seco", "canto_grande_upper_branch", "media_luna"):
        row = units[unit_id]
        source = jic_rows[unit_id]
        assert row["source_contract"] == "config/phase2_jicamarca_collector_coupling_v0_1.json"
        assert row["collector_effect_state"] == source["collector_effect_state"]
        assert row["validation_status"] == source["validation_status"]
        for field in NULL_FIELDS:
            assert row.get(field) is None

    gates = reg.get("coupling_gates") or {}
    required = {
        "tributary_activation_implies_receiver_overflow",
        "same_day_events_imply_peak_coincidence",
        "imerg_may_decide_local_activation",
        "travel_time_estimation_enabled",
        "routing_enabled",
        "hydraulic_model_enabled",
    }
    assert set(gates) == required
    assert all(gates[key] is False for key in required)


def build_report() -> dict:
    reg, rimac, jic = map(load, (REGISTRY, RIMAC, JIC))
    validate_registry(reg, rimac, jic)
    units = reg["local_units"]
    return {
        "status": "PASS_PHASE2_RIMAC_JICAMARCA_COUPLING_REGISTRY",
        **SAFE,
        "local_unit_count": len(units),
        "static_connected_count": sum(x["collector_effect_state"] == "HYDROLOGICALLY_CONNECTED" for x in units),
        "no_evidence_count": sum(x["collector_effect_state"] == "NO_EVIDENCE" for x in units),
        "receiver_overflow_states_assigned": 0,
        "travel_times_assigned": 0,
        "routing_models_run": 0,
        "hydraulic_models_run": 0,
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
