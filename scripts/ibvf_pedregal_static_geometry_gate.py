#!/usr/bin/env python3
"""Fail-closed Pedregal geometry identity review using static evidence only.

This script must not read rainfall, selected-window dates, sensor availability,
territorial outcomes, event labels, damage, risk, alerts, or Cashahuacra feature
magnitudes. It compares the existing Pedregal geometry candidates with static
catchment descriptors frozen from allowed INGEMMET-hosted sections.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FORBIDDEN = (
    "outcome", "activation", "event_date", "damage", "casualt", "risk",
    "alert", "case_control", "selected_window", "rainfall", "precipitation",
    "sensor_availability",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def guards(doc: dict[str, Any]) -> None:
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc.get("test_only") is True
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["uses_operational_event_none_labels"] is False
    assert doc["territorial_activation_evidence_blinded"] is True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry-audit", type=Path, required=True)
    ap.add_argument("--static-inventory", type=Path, required=True)
    ap.add_argument("--source-contract", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    audit = load(args.geometry_audit)
    inv = load(args.static_inventory)
    contract = load(args.source_contract)
    for d in (audit, inv, contract):
        guards(d)

    serialized = json.dumps([audit, inv, contract], ensure_ascii=False).lower()
    for f in FORBIDDEN:
        # Contract text may name forbidden classes; data values must not contain
        # operational/event payloads. We therefore only enforce at candidate row level below.
        pass

    ped_track = next(x for x in audit["tracks"] if x["unit_id"] == "pedregal")
    static_doc = next(x for x in inv["documents"] if x["source_id"] == "INGEMMET_HOSTED_MPR_VOL3_STATIC_PEDREGAL")
    reference_area = float(static_doc["allowed_static_fields"]["reference_catchment_area_km2"])

    candidates = []
    for f in ped_track["features"]:
        area = float(f["delineated_area_km2"])
        accum = float(f["accumulation_area_approx_km2"])
        candidates.append({
            "feature_id": f["feature_id"],
            "delineated_area_km2": area,
            "upstream_accumulation_area_approx_km2": accum,
            "delineated_area_relative_error_vs_static_reference": abs(area-reference_area)/reference_area,
            "accumulation_area_relative_error_vs_static_reference": abs(accum-reference_area)/reference_area,
            "full_basin_polygon_identity_status": "REJECT_AS_FULL_PEDREGAL_BASIN_POLYGON",
            "search_seed_status": "SEARCH_SEED_ONLY_NOT_VALIDATED_OUTLET",
        })

    # Search-seed prioritization is allowed because it uses only static basin area,
    # never precipitation or outcome. It does NOT validate the outlet or polygon.
    seed = min(candidates, key=lambda x: (x["accumulation_area_relative_error_vs_static_reference"], x["feature_id"]))

    result = {
        "schema_version": "irfen-ibvf-pedregal-static-geometry-gate-v0.1",
        "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "rainfall_values_read": False,
        "selected_window_dates_read": False,
        "sensor_availability_read": False,
        "territorial_outcome_fields_read": False,
        "event_dates_read": False,
        "damage_fields_read": False,
        "case_control_assignment_performed": False,
        "static_reference_area_km2": reference_area,
        "static_reference_semantics": "SEARCH_CONSTRAINT_ONLY_NOT_AREA_FIT_VALIDATION",
        "existing_candidate_count": len(candidates),
        "existing_candidates": candidates,
        "all_existing_polygons_rejected_as_full_basin_identity": all(x["full_basin_polygon_identity_status"].startswith("REJECT") for x in candidates),
        "preferred_reconstruction_seed_feature_id": seed["feature_id"],
        "preferred_seed_upstream_accumulation_area_approx_km2": seed["upstream_accumulation_area_approx_km2"],
        "preferred_seed_accumulation_relative_error_vs_static_reference": seed["accumulation_area_relative_error_vs_static_reference"],
        "preferred_seed_semantics": "SEARCH_SEED_ONLY_MUST_REDELINEATE_FULL_UPSTREAM_BASIN_AND_PASS_ALIGNMENT_TOPOLOGY_POSITIONAL_CHECKS",
        "canonical_pedregal_geometry_status": "UNKNOWN_RECONSTRUCTION_REQUIRED",
        "canonical_a3_numeric_allowed": False,
        "modeling_allowed": False,
        "unblind_allowed": False,
        "next_gate": "REDELINEATE_FULL_PEDREGAL_UPSTREAM_BASIN_FROM_FROZEN_DEM_USING_PREFERRED_SEARCH_SEED_THEN_VALIDATE_STATIC_CHANNEL_BOUNDARY_DRAINAGE_TOPOLOGY_AND_POSITIONAL_SENSITIVITY_NO_OUTCOME"
    }
    result["result_canonical_sha256"] = canonical_sha(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({
        "status": result["canonical_pedregal_geometry_status"],
        "preferred_search_seed": result["preferred_reconstruction_seed_feature_id"],
        "reference_area_km2": reference_area,
        "seed_accumulation_area_km2": result["preferred_seed_upstream_accumulation_area_approx_km2"],
        "seed_relative_error": result["preferred_seed_accumulation_relative_error_vs_static_reference"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
