#!/usr/bin/env python3
"""Verify frozen Supe discovery registration and official ANA geometry without writes."""
from __future__ import annotations

from hashlib import sha256
import json

import bootstrap_phase2_supe_discovery as b


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def fail(message):
    raise b.BootstrapError(message)


def main() -> None:
    inventory = b.load(b.INVENTORY)
    contract = b.load(b.CONTRACT)
    package = b.load(b.PACKAGE)
    b.validate_guards(inventory, "INVENTORY")
    b.validate_guards(contract, "CONTRACT")
    b.validate_guards(package, "PACKAGE")

    rel = inventory.get("relationship_to_phase2") or {}
    if rel.get("registered_candidate_count_unchanged") != 18:
        fail("PHASE2_REGISTERED_CANDIDATE_COUNT_DRIFT")
    if rel.get("changes_registered_candidate_count") is not False or rel.get("changes_operational_scope") is not False:
        fail("DISCOVERY_EXTENSION_CHANGED_OPERATIONAL_SCOPE")
    units = inventory.get("discovery_units") or []
    if rel.get("discovery_units_count") != len(units):
        fail("DISCOVERY_COUNT_DRIFT")
    rows = [row for row in units if row.get("discovery_id") == b.DISCOVERY_ID]
    if len(rows) != 1 or rows[0] != b.DISCOVERY_ROW:
        fail("SUPE_DISCOVERY_REGISTRATION_DRIFT")

    code, name, _query = b.validate_inputs(contract, package)
    for path in (b.SOURCE, b.GEOMETRY, b.VALIDATION):
        if not path.is_file():
            fail(f"FROZEN_SUPE_ARTIFACT_MISSING_{path.name}")

    source = b.load(b.SOURCE)
    source_sha = digest(b.SOURCE)
    feature = b.validate_source(source, code, name)
    expected_geometry = b.canonical_bytes(b.normalized(feature, code, name, source_sha))
    if b.GEOMETRY.read_bytes() != expected_geometry:
        fail("FROZEN_SUPE_GEOMETRY_REPLAY_MISMATCH")
    geometry_sha = digest(b.GEOMETRY)

    validation = b.load(b.VALIDATION)
    b.validate_guards(validation, "VALIDATION")
    required_validation = {
        "status": "PASS_OFFICIAL_ANA_SUPE_DISCOVERY_BASIN_GEOMETRY",
        "source_id": "ANA-UH-137572-SUPE",
        "ana_unit_code": code,
        "ana_unit_name": name,
        "source_path": b.SOURCE.relative_to(b.ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": b.GEOMETRY.relative_to(b.ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "outcomes_read_for_geometry": False,
        "rainfall_read_for_geometry": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
        "caleta_vidal_used_as_basin": False,
    }
    for key, expected in required_validation.items():
        if validation.get(key) != expected:
            fail(f"FROZEN_SUPE_VALIDATION_MISMATCH_{key}")
    validation_sha = digest(b.VALIDATION)

    for label, obj in (("CONTRACT", contract), ("PACKAGE", package)):
        asset = obj["assets"]["geometry"]
        expected_asset = {
            "status": "PARTIAL_OFFICIAL_BASIN_CONTEXT",
            "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
            "sha256": geometry_sha,
            "validation_path": b.VALIDATION.relative_to(b.ROOT).as_posix(),
            "validation_sha256": validation_sha,
            "source_path": b.SOURCE.relative_to(b.ROOT).as_posix(),
            "source_sha256": source_sha,
            "counts_as_operational_geometry": False,
            "counts_as_event_footprint": False,
        }
        for key, expected in expected_asset.items():
            if asset.get(key) != expected:
                fail(f"FROZEN_SUPE_{label}_ASSET_MISMATCH_{key}")

    if contract.get("contract_status") != "DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY":
        fail("FROZEN_SUPE_CONTRACT_STATUS_DRIFT")
    if package.get("contract_status") != "DISCOVERY_HYDROLOGIC_IDENTITY_AND_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY":
        fail("FROZEN_SUPE_PACKAGE_STATUS_DRIFT")
    if package.get("geometry_contract_path") != b.CONTRACT.relative_to(b.ROOT).as_posix():
        fail("FROZEN_SUPE_PACKAGE_CONTRACT_LINK_DRIFT")
    alignment = package.get("inventory_alignment") or {}
    if alignment.get("registration_status") != "REGISTERED_DISCOVERY_ONLY_NON_OPERATIONAL":
        fail("SUPE_INVENTORY_ALIGNMENT_NOT_REGISTERED")
    if alignment.get("operational_candidate_count_change_allowed") is not False:
        fail("SUPE_ALIGNMENT_ALLOWS_OPERATIONAL_COUNT_CHANGE")

    print(json.dumps({
        "status": "PASS_FROZEN_SUPE_DISCOVERY_REPLAY",
        "source_sha256": source_sha,
        "geometry_sha256": geometry_sha,
        "validation_sha256": validation_sha,
        "discovery_units_count": len(units),
        "registered_phase2_candidate_count": 18,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
