#!/usr/bin/env python3
"""Shared resolver for Phase-2 RESEARCH_ONLY hydrologic subunit sampling targets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CONTRACTS_PATH = SITE / "data/phase2/spatial_observation_contracts_v0_1.json"


class Phase2SubunitSamplingError(ValueError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_feature(document, selector):
    prop = selector.get("property")
    value = selector.get("value")
    features = document.get("features") if document.get("type") == "FeatureCollection" else [document]
    matches = [
        feature for feature in (features or [])
        if (feature.get("properties") or {}).get(prop) == value
    ]
    if len(matches) != 1:
        raise Phase2SubunitSamplingError(
            f"selector {prop}={value!r} matched {len(matches)} features"
        )
    return matches[0]


def load_research_subunit_targets():
    """Resolve only Claude-F subunits explicitly eligible for research sampling."""
    contracts = load_json(CONTRACTS_PATH)
    if contracts.get("deployment_status") != "RESEARCH_ONLY":
        raise Phase2SubunitSamplingError("spatial contracts must remain RESEARCH_ONLY")
    if contracts.get("production_use") is not False:
        raise Phase2SubunitSamplingError("spatial contracts production_use must remain false")
    if contracts.get("activation_gate") != "BLOCKED":
        raise Phase2SubunitSamplingError("spatial contracts activation_gate must remain BLOCKED")

    targets = []
    for candidate in contracts.get("candidate_records") or []:
        candidate_id = candidate.get("candidate_id")
        for contract in candidate.get("subunit_contracts") or []:
            if contract.get("contract_status") != "RESEARCH_SAMPLING_ELIGIBLE":
                continue
            if contract.get("deployment_status") != "RESEARCH_ONLY":
                raise Phase2SubunitSamplingError(f"{candidate_id}: subunit not RESEARCH_ONLY")
            if contract.get("production_use") is not False:
                raise Phase2SubunitSamplingError(f"{candidate_id}: production_use changed")
            if contract.get("production_ready") is not False:
                raise Phase2SubunitSamplingError(f"{candidate_id}: production_ready changed")
            if contract.get("operational_alerting_enabled") is not False:
                raise Phase2SubunitSamplingError(f"{candidate_id}: alerting changed")
            if contract.get("activation_gate") != "BLOCKED":
                raise Phase2SubunitSamplingError(f"{candidate_id}: activation gate changed")
            if contract.get("counts_as_candidate_wide_geometry") is not False:
                raise Phase2SubunitSamplingError(f"{candidate_id}: subunit cannot complete parent")
            if contract.get("counts_as_operational_geometry") is not False:
                raise Phase2SubunitSamplingError(f"{candidate_id}: subunit cannot be operational")

            geometry_ref = contract.get("geometry_ref") or {}
            path = ROOT / str(geometry_ref.get("path") or "")
            if not path.is_file():
                raise Phase2SubunitSamplingError(f"{candidate_id}: geometry file missing: {path}")
            document = load_json(path)
            feature = _select_feature(document, geometry_ref.get("feature_selector") or {})
            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            expected_hash = geometry_ref.get("geometry_sha256")
            hash_scope = geometry_ref.get("hash_scope")
            if not expected_hash:
                raise Phase2SubunitSamplingError(
                    f"{candidate_id}/{contract.get('subunit_id')}: missing geometry hash"
                )
            if hash_scope == "FEATURE_GEOMETRY_SHA256":
                actual_hash = props.get("geometry_sha256")
            elif hash_scope == "GEOJSON_FILE_SHA256":
                actual_hash = _sha256_file(path)
            else:
                raise Phase2SubunitSamplingError(
                    f"{candidate_id}/{contract.get('subunit_id')}: unsupported hash_scope {hash_scope!r}"
                )
            if actual_hash != expected_hash:
                raise Phase2SubunitSamplingError(
                    f"{candidate_id}/{contract.get('subunit_id')}: geometry hash mismatch"
                )
            if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                raise Phase2SubunitSamplingError(
                    f"{candidate_id}/{contract.get('subunit_id')}: non-area geometry"
                )
            geom = shape(geometry).buffer(0)
            if geom.is_empty or geom.area <= 0:
                raise Phase2SubunitSamplingError(
                    f"{candidate_id}/{contract.get('subunit_id')}: empty geometry"
                )

            subunit_id = contract["subunit_id"]
            targets.append({
                "id": f"phase2_subunit:{candidate_id}:{subunit_id}",
                "name": f"Phase-2 RESEARCH_ONLY: {subunit_id}",
                "candidate_id": candidate_id,
                "subunit_id": subunit_id,
                "geometry": geom,
                "geometry_path": geometry_ref.get("path"),
                "geometry_sha256": expected_hash,
                "declared_area_km2": geometry_ref.get("declared_area_km2"),
                "sampling_contract": contract.get("sampling_contract") or {},
                "contract_scope": contract.get("contract_scope"),
                "hash_scope": hash_scope,
                "phase2_subunit": {
                    "candidate_id": candidate_id,
                    "subunit_id": subunit_id,
                    "deployment_status": "RESEARCH_ONLY",
                    "counts_as_candidate_wide_geometry": False,
                    "counts_as_operational_geometry": False,
                },
            })

    targets.sort(key=lambda row: row["id"])
    return targets


def target_ids():
    return {target["id"] for target in load_research_subunit_targets()}
