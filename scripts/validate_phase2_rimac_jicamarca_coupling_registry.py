#!/usr/bin/env python3
"""Validate the unified fail-closed Rimac/Jicamarca collector-coupling registry."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/phase2_rimac_jicamarca_coupling_registry_v0_1.json"
RIMAC = ROOT / "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_2.json"
JIC = ROOT / "config/phase2_jicamarca_collector_coupling_v0_1.json"
EVIDENCE = ROOT / "config/phase2_jicamarca_historical_coupling_evidence_v0_1.json"

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
    "jicamarca_named_channel",
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
    assert len(units) == 9

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

    for unit_id in ("huaycoloro", "rio_seco", "canto_grande_upper_branch", "media_luna", "jicamarca_named_channel"):
        row = units[unit_id]
        source = jic_rows[unit_id]
        assert row["source_contract"] == "config/phase2_jicamarca_collector_coupling_v0_1.json"
        assert row["collector_effect_state"] == source["collector_effect_state"]
        assert row["validation_status"] == source["validation_status"]
        if unit_id != "media_luna":
            assert row["connectivity"] == source.get("ultimate_receiver_connection_status", "UNRESOLVED_NOT_ASSUMED")
        else:
            assert row["connectivity"] == "DOCUMENTARY_TOPOLOGY_ONLY_EXACT_NODE_UNRESOLVED"
        for field in NULL_FIELDS:
            assert row.get(field) is None

    assert jic_rows["jicamarca_named_channel"]["ultimate_receiver"] is None
    assert jic_rows["jicamarca_named_channel"]["source_local_geometry_contract_or_explicit_missing_status"]["synthetic_unit_forbidden"] is True

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


BLOCKER_STATES = {
    "routing_topology": "PARTIAL_DOCUMENTARY_CHAIN_ESTABLISHED_EXACT_NODES_UNRESOLVED",
    "routing_temporal": "BLOCKED_UNCHANGED",
    "capacity": "BLOCKED_UNCHANGED",
    "overflow": "PARTIAL_HISTORICAL_OCCURRENCE_ONLY",
}


def validate_blockers(reg: dict, ev: dict, units: dict) -> None:
    """Routing topology, capacity and overflow are adjudicated independently.

    Historical evidence may only establish documentary topology and qualitative
    occurrence; it must never populate hydraulic parameters.
    """
    require_safe(ev, "historical_evidence")
    status = reg.get("blocker_status") or {}
    assert status.get("evidence_ref") == "config/phase2_jicamarca_historical_coupling_evidence_v0_1.json"
    assert status.get("unit_states_changed") is False
    for key, expected in BLOCKER_STATES.items():
        assert status.get(key) == expected, f"blocker_status:{key}"

    adj = ev["blocker_adjudication"]
    routing, capacity, overflow = adj["routing"], adj["capacity"], adj["overflow"]
    assert routing["topology_state"] == status["routing_topology"]
    assert routing["temporal_routing_state"] == status["routing_temporal"]
    assert capacity["state"] == status["capacity"]
    assert overflow["state"] == status["overflow"]

    # Routing: documentary edges only, no exact nodes, no temporal parameters.
    assert routing["routing_enabled"] is False
    for edge in routing["documentary_chain"]:
        assert edge["exact_node"] is None
        assert (ROOT / edge["basis_ref"]).is_file(), edge["basis_ref"]
    assert routing["documentary_chain"][-1]["to"] == "rimac_mainstem_receiver"
    assert routing["event_corroboration"]["may_add_edges"] is False
    assert {"q_i_t", "travel_time_tau", "attenuation_or_storage", "flow_partition"} <= set(routing["not_established"])

    # Capacity: nothing counted, nothing assigned.
    assert capacity["channel_capacity"] is None
    assert capacity["structure_capacity"] is None
    assert capacity["evidence_counted_toward_capacity"] == 0

    # Overflow: qualitative occurrence only.
    assert overflow["overflow_threshold"] is None
    assert overflow["return_period"] is None
    assert overflow["frequency_inferred"] is False
    assert overflow["receiver_overflow_state_assigned_to_units"] is False
    assert overflow["tributary_activation_implies_receiver_overflow"] is False
    assert [o["year"] for o in overflow["documented_occurrences"]] == [1998]

    impact = ev["documented_1998_receiver_impact"]
    for key in ("discharge", "flow_depth", "sediment_volume", "overflow_location", "structure_location"):
        assert impact[key] is None, f"1998:{key}"
    for key in ("is_channel_capacity_observation", "is_structure_capacity_observation",
                "may_define_overflow_threshold", "may_define_return_period",
                "may_calibrate_routing_or_travel_time", "child_attribution_resolved"):
        assert impact[key] is False, f"1998:{key}"

    material = ev["rio_seco_material_contribution"]
    assert material["numeric_value_use"] == "PROVENANCE_ONLY"
    assert all(material[k] is False for k in material if k.startswith("may_be_used_as_"))

    events = ev["parent_context_events"]
    assert events["child_attribution_resolved"] is False
    assert events["may_estimate_return_period"] is False
    assert events["may_estimate_frequency"] is False

    # Historical context (e.g. Tambo de Viso 1998): kept as context only, never
    # as a transferable hydraulic parameter for Jicamarca or any other quebrada.
    context = {row["context_id"]: row for row in ev["historical_context"]}
    assert set(context) == set(status["historical_context_ids"])
    for row in context.values():
        assert row["classification"] == "HISTORICAL_CONTEXT_ONLY_NOT_TRANSFERABLE"
        assert row["is_hydraulic_parameter"] is False
        assert row["numeric_value_use"] == "PROVENANCE_ONLY"
        assert all(row[k] is False for k in row if k.startswith("may_")), row["context_id"]
    tambo = context["TAMBO_DE_VISO_1998"]
    assert tambo["in_jicamarca_system"] is False
    assert tambo["in_rimac_corridor_mouth_to_santa_eulalia"] is False
    assert tambo["numeric_value_verified"] is False
    assert tambo["primary_event_source_pinned"] is False

    # Unit-level hydraulic fields stay empty regardless of blocker progress.
    for unit in units.values():
        for field in NULL_FIELDS:
            assert unit.get(field) is None


def build_report() -> dict:
    reg, rimac, jic, ev = map(load, (REGISTRY, RIMAC, JIC, EVIDENCE))
    validate_registry(reg, rimac, jic)
    validate_blockers(reg, ev, by_id(reg["local_units"]))
    units = reg["local_units"]
    overflow = ev["blocker_adjudication"]["overflow"]
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
        "blocker_status": {k: reg["blocker_status"][k] for k in BLOCKER_STATES},
        "documentary_routing_edges": len(ev["blocker_adjudication"]["routing"]["documentary_chain"]),
        "historical_overflow_occurrences": len(overflow["documented_occurrences"]),
        "capacity_values_assigned": 0,
        "historical_context_count": len(ev["historical_context"]),
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
