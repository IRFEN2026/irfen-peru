#!/usr/bin/env python3
"""Offline, fail-closed QA for the Rímac/Santa Eulalia/Jicamarca documentary index.

Run: python scripts/validate_phase2_rimac_corridor_inventory.py
Negative-control tests: python scripts/validate_phase2_rimac_corridor_inventory.py --self-test

This script intentionally lives outside tests/ to avoid silently changing the
pinned pytest collection manifest. It neither fetches sources nor promotes
documentary names, GIS lines, monitoring activations or fajas into hydrology.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json"
)
GUARDS = {
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
UNVERIFIED_UNIT_IDS = {
    "lima_lurigancho_quirio",
    "lima_santa_eulalia_cashahuacra",
    "lima_huaycoloro",
    "jicamarca_rio_seco",
}
MEMBERSHIP = {
    "PRESENT_IN_NATIONAL_MASTER_BY_EXACT_INVENTORY_ID": "national_master_corridor_documentary_rows",
    "EXTERNAL_DOS_BARRIOS_DOCUMENTARY_ROW_NOT_IN_MAIN_NATIONAL_MASTER": "additional_dos_barrios_documentary_rows_not_in_main",
    "JICAMARCA_CONTEXT_ROW_NOT_IN_MAIN_NATIONAL_MASTER": "jicamarca_context_documentary_rows_not_in_national_master",
}


def validate(document: dict) -> list[str]:
    errors: list[str] = []
    for key, expected in GUARDS.items():
        if document.get(key, object()) != expected:
            errors.append(f"guard {key} changed")
    units = document.get("units", [])
    counts = document.get("counts", {})
    ids = [unit.get("id") for unit in units]
    if len(ids) != len(set(ids)) or any(not identifier for identifier in ids):
        errors.append("missing/duplicate inventory_id")
    if counts.get("total_documentary_rows") != len(units):
        errors.append("documentary row count does not match units")
    if counts.get("confirmed_unique_hydrologic_unit_count") is not None:
        errors.append("documentary row count cannot certify unique hydrologic units")
    if counts.get("possible_alias_double_count_unresolved") is not True:
        errors.append("alias uncertainty lost")
    for membership, count_key in MEMBERSHIP.items():
        observed = sum(u.get("national_master_membership") == membership for u in units)
        if counts.get(count_key) != observed:
            errors.append(f"national-master membership mismatch: {membership}")
    if sum(counts.get(k, -1) for k in MEMBERSHIP.values()) != len(units):
        errors.append("national-master partitions do not sum to total")
    if document.get("map_updates") != {
        "new_geometries_published": 0,
        "new_outlets_published": 0,
        "new_collector_reaches_published": 0,
    }:
        errors.append("map update promotion requires separate review")
    semantics = document.get("collector_semantics", {})
    for key in (
        "no_child_activation_implies_collector_overflow",
        "works_are_not_capacity",
        "design_is_not_measured_capacity",
        "regulatory_faja_is_not_channel_or_event_footprint",
        "station_activation_is_not_discharge",
        "imerg_context_only",
        "missing_data_is_not_negative",
        "all_exact_outlets_unresolved_in_this_inventory",
    ):
        if semantics.get(key) is not True:
            errors.append(f"collector separation lost: {key}")
    id_set = set(ids)
    for group in document.get("pending_identity_groups", []):
        if not set(group.get("inventory_ids", [])).issubset(id_set):
            errors.append("alias group references missing inventory_id")
    for unit in units:
        uid = unit.get("id", "<unknown>")
        if unit.get("map_publishable") is not False:
            errors.append(f"{uid}: map publication without independent gate")
        if unit.get("outlet_coordinate") is not None or unit.get("exact_confluence_coordinate") is not None:
            errors.append(f"{uid}: exact outlet/confluence not substantiated")
        if unit.get("travel_time_tau") is not None or unit.get("discharge_q_i") is not None:
            errors.append(f"{uid}: unverified travel time/discharge")
        if unit.get("collector_capacity") is not None or unit.get("collector_overflow_evidence") is not None:
            errors.append(f"{uid}: capacity/overflow promotion")
        if unit.get("reproducible_geometry_ref") is not None and not unit.get("channel_or_catchment_geometry", "").startswith("OFFICIAL_IGP_LINE_CONTEXT"):
            errors.append(f"{uid}: GIS reference is not adjudicated IGP line context")
        if any(lead.get("usable_as_confirmed_unit_event") is not False
               for lead in unit.get("unverified_event_leads", [])):
            errors.append(f"{uid}: unverified lead promoted to confirmed event")
        if uid in UNVERIFIED_UNIT_IDS:
            if unit.get("verified_event_refs"):
                errors.append(f"{uid}: unverified unit event marked verified")
            if unit.get("flow_or_stage_observation_refs"):
                errors.append(f"{uid}: station activation/lead promoted to flow or stage")
    for lead in document.get("official_unmaterialized_name_leads", []):
        name = lead.get("documentary_name", "<unknown>")
        for key in ("catchment_geometry", "channel_geometry", "outlet_coordinate",
                    "exact_confluence_coordinate", "travel_time_tau",
                    "collector_capacity", "collector_overflow_evidence"):
            if lead.get(key) is not None:
                errors.append(f"{name}: unmaterialized lead has {key}")
        if lead.get("map_publishable") is not False:
            errors.append(f"{name}: unmaterialized lead promoted to map")
        if lead.get("counted_as_confirmed_unique_hydrologic_unit") is not False:
            errors.append(f"{name}: documentary lead counted as unique unit")
        if lead.get("verified_event_refs"):
            errors.append(f"{name}: unverified lead promoted to event")
    return errors


class NegativeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_current_snapshot(self) -> None:
        self.assertEqual(validate(self.base), [])

    def test_operational_gate_fails_closed(self) -> None:
        candidate = copy.deepcopy(self.base)
        candidate["activation_gate"] = "OPEN"
        self.assertTrue(validate(candidate))

    def test_alias_cannot_reference_invented_id(self) -> None:
        candidate = copy.deepcopy(self.base)
        candidate["pending_identity_groups"][0]["inventory_ids"].append("invented_unit")
        self.assertTrue(validate(candidate))

    def test_unverified_event_cannot_be_confirmed(self) -> None:
        candidate = copy.deepcopy(self.base)
        next(u for u in candidate["units"] if u["id"] == "lima_lurigancho_quirio")["verified_event_refs"] = ["unproven"]
        self.assertTrue(validate(candidate))

    def test_station_activation_is_not_flow(self) -> None:
        candidate = copy.deepcopy(self.base)
        next(u for u in candidate["units"] if u["id"] == "jicamarca_rio_seco")["flow_or_stage_observation_refs"] = ["station_activation"]
        self.assertTrue(validate(candidate))

    def test_no_synthetic_outlet_or_map(self) -> None:
        candidate = copy.deepcopy(self.base)
        candidate["units"][0]["outlet_coordinate"] = [0, 0]
        candidate["units"][0]["map_publishable"] = True
        self.assertTrue(validate(candidate))

    def test_count_cannot_inflate(self) -> None:
        candidate = copy.deepcopy(self.base)
        candidate["counts"]["total_documentary_rows"] += 1
        self.assertTrue(validate(candidate))


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        unittest.main(argv=[sys.argv[0]])
    elif sys.argv[1:]:
        raise SystemExit("Usage: python scripts/validate_phase2_rimac_corridor_inventory.py [--self-test]")
    else:
        problems = validate(json.loads(REGISTRY.read_text(encoding="utf-8")))
        if problems:
            print("\n".join(problems), file=sys.stderr)
            raise SystemExit(1)
        print("PASS: documentary inventory remains fail-closed; no map, event, or hydraulic promotion")
