#!/usr/bin/env python3
"""Verify the frozen official ANA Virú discovery geometry without mutating artifacts."""
from __future__ import annotations

from hashlib import sha256
import json

import probe_phase2_viru_official_geometry as p


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def fail(message):
    raise p.ProbeError(message)


def main() -> None:
    contract = p.load(p.CONTRACT)
    package = p.load(p.PACKAGE)
    code, name, _query = p.validate_inputs(contract, package)
    if not p.SOURCE.is_file() or not p.GEOMETRY.is_file() or not p.VALIDATION.is_file():
        fail("FROZEN_VIRU_ARTIFACT_MISSING")

    source = p.load(p.SOURCE)
    source_sha = digest(p.SOURCE)
    feature = p.validate_source(source, code, name)
    expected_geometry = p.canonical_bytes(p.normalized(feature, code, name, source_sha))
    if p.GEOMETRY.read_bytes() != expected_geometry:
        fail("FROZEN_VIRU_GEOMETRY_REPLAY_MISMATCH")
    geometry_sha = digest(p.GEOMETRY)

    validation = p.load(p.VALIDATION)
    p.validate_guards(validation, "VALIDATION")
    required = {
        "status": "PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY",
        "source_id": "ANA-UH-137714-VIRU",
        "ana_unit_code": code,
        "ana_unit_name": name,
        "source_path": p.SOURCE.relative_to(p.ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": p.GEOMETRY.relative_to(p.ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "outcomes_read": False,
        "rainfall_read": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
    }
    for key, expected in required.items():
        if validation.get(key) != expected:
            fail(f"FROZEN_VIRU_VALIDATION_MISMATCH_{key}")
    validation_sha = digest(p.VALIDATION)

    for label, obj in (("CONTRACT", contract), ("PACKAGE", package)):
        asset = obj["assets"]["geometry"]
        expected_asset = {
            "status": "PARTIAL_OFFICIAL_BASIN_CONTEXT",
            "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
            "sha256": geometry_sha,
            "validation_path": p.VALIDATION.relative_to(p.ROOT).as_posix(),
            "validation_sha256": validation_sha,
            "source_path": p.SOURCE.relative_to(p.ROOT).as_posix(),
            "source_sha256": source_sha,
            "counts_as_operational_geometry": False,
            "counts_as_event_footprint": False,
        }
        for key, expected in expected_asset.items():
            if asset.get(key) != expected:
                fail(f"FROZEN_VIRU_{label}_ASSET_MISMATCH_{key}")

    if contract.get("contract_status") != "DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY":
        fail("FROZEN_VIRU_CONTRACT_STATUS_DRIFT")
    if package.get("contract_status") != "DISCOVERY_HYDROLOGIC_IDENTITY_AND_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY":
        fail("FROZEN_VIRU_PACKAGE_STATUS_DRIFT")
    if package.get("geometry_contract_path") != p.CONTRACT.relative_to(p.ROOT).as_posix():
        fail("FROZEN_VIRU_PACKAGE_CONTRACT_LINK_DRIFT")

    print(json.dumps({
        "status": "PASS_FROZEN_VIRU_OFFICIAL_GEOMETRY_REPLAY",
        "source_sha256": source_sha,
        "geometry_sha256": geometry_sha,
        "validation_sha256": validation_sha,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
