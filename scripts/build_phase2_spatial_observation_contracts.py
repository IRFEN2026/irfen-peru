#!/usr/bin/env python3
"""Build Phase-2 Spatial Observation Contracts (Claude F).

RESEARCH_ONLY / TEST_ONLY.

The output separates:
- candidate-wide geometries that are genuinely suitable for area-based research sampling;
- reproducible hydrologic subunit polygons usable only for research sampling;
- present geometries that are not catchments/watersheds;
- candidates blocked by missing/non-reproducible geometry.

It never promotes a candidate, opens an activation gate, infers thresholds,
or reinterprets regulatory corridors/fajas as drainage basins.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_2.json"
CATALOG_PATH = ROOT / "site/data/phase2/catalog.json"
ZONE_CONTRACTS_DIR = ROOT / "site/data/validation/phase2_zone_contracts"
OUT_PATH = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
LAMBAYEQUE_PARENT_ID = "lambayeque_chongoyape_oyotun_zana"
LAMBAYEQUE_MIGRATION_VALIDATION = (
    ROOT / "site/data/phase2/geometries/lambayeque_hydrologic_migration_validation.json"
)

POLYGON_TYPES = {"Polygon", "MultiPolygon"}
RESEARCH_SUBUNIT_ROLE = "local_debris_flow_catchment_candidate"
CANDIDATE_WIDE_APPROVED_ROLES = {
    "official_hydrologic_unit_polygon",
    "validated_watershed_polygon",
    "approved_catchment_polygon",
}
NON_CATCHMENT_ROLES = {
    "official_river_faja_marginal",
    "official_updated_faja_left_bank_control",
    "official_right_margin_hitos_connected",
    "official_left_margin_hitos_connected",
    "derived_regulatory_corridor_polygon",
}


class SpatialContractError(ValueError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def load_contract(candidate_id):
    path = ZONE_CONTRACTS_DIR / f"{candidate_id}.json"
    if not path.is_file():
        raise SpatialContractError(f"missing zone contract: {candidate_id}")
    return load_json(path)


def load_geometry_file(relative_path):
    path = ROOT / relative_path
    if not path.is_file():
        return None
    return load_json(path)


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_id(feature):
    props = feature.get("properties") or {}
    return props.get("unit_id") or props.get("feature_id") or props.get("feature_role")


def classify_feature(feature):
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    role = props.get("hydrologic_role") or props.get("feature_role")
    geometry_type = geometry.get("type")

    if role == RESEARCH_SUBUNIT_ROLE:
        if geometry_type not in POLYGON_TYPES:
            return "BLOCKED_SUBUNIT_NON_POLYGON", "hydrologic subunit is not Polygon/MultiPolygon"
        if props.get("candidate_status") != "REVIEW_ONLY":
            return "BLOCKED_SUBUNIT_STATUS", "subunit is not explicitly REVIEW_ONLY"
        for key in (
            "production_use",
            "production_ready",
            "alerting_enabled",
            "loaded_into_operational_calculation",
            "carries_alert_values",
            "carries_risk_classification",
        ):
            if props.get(key) is not False:
                return "BLOCKED_OPERATIONAL_FLAG", f"{key} must be false"
        if not props.get("geometry_sha256"):
            return "BLOCKED_MISSING_GEOMETRY_HASH", "geometry_sha256 missing"
        area = (props.get("coverage") or {}).get("delineated_area_km2")
        if not isinstance(area, (int, float)) or area <= 0:
            return "BLOCKED_MISSING_POSITIVE_AREA", "delineated_area_km2 missing/non-positive"
        return "ELIGIBLE_RESEARCH_SUBUNIT", None

    if role in CANDIDATE_WIDE_APPROVED_ROLES and geometry_type in POLYGON_TYPES:
        return "ELIGIBLE_CANDIDATE_WIDE_ROLE", None

    if role in NON_CATCHMENT_ROLES:
        return "EXCLUDED_NON_CATCHMENT_GEOMETRY", "regulatory/river-margin geometry is not a catchment"

    if geometry_type in ("LineString", "MultiLineString"):
        return "EXCLUDED_NON_AREA_GEOMETRY", "line geometry cannot represent precipitation sampling area"

    if geometry_type in POLYGON_TYPES:
        return "EXCLUDED_UNAPPROVED_POLYGON_ROLE", "polygon role is not an approved drainage-basin role"

    return "EXCLUDED_UNKNOWN_GEOMETRY", "geometry type/role is not eligible"


def build_subunit_contract(candidate_id, geometry_path, feature):
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coverage = props.get("coverage") or {}
    outlet = props.get("outlet") or {}
    unit_id = props.get("unit_id")
    if not unit_id:
        raise SpatialContractError(f"{candidate_id}: eligible subunit lacks unit_id")

    return {
        "contract_id": f"phase2-spatial-observation:{candidate_id}:{unit_id}:v0.1",
        "candidate_id": candidate_id,
        "subunit_id": unit_id,
        "contract_scope": "HYDROLOGIC_SUBUNIT_RESEARCH_ONLY",
        "contract_status": "RESEARCH_SAMPLING_ELIGIBLE",
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "counts_as_candidate_wide_geometry": False,
        "counts_as_operational_geometry": False,
        "geometry_ref": {
            "path": geometry_path,
            "feature_selector": {"property": "unit_id", "value": unit_id},
            "geometry_type": geometry.get("type"),
            "geometry_sha256": props.get("geometry_sha256"),
            "hash_scope": "FEATURE_GEOMETRY_SHA256",
            "representation": props.get("representation"),
            "hydrologic_role": props.get("hydrologic_role"),
            "declared_area_km2": coverage.get("delineated_area_km2"),
            "area_semantics": coverage.get("area_semantics"),
            "confidence": props.get("confidence"),
            "candidate_status": props.get("candidate_status"),
        },
        "outlet_status": {
            "official_confirmation": outlet.get("official_confirmation"),
            "lon": outlet.get("lon"),
            "lat": outlet.get("lat"),
            "selection": outlet.get("selection"),
        },
        "sampling_contract": {
            "method": "AREA_WEIGHTED_GRID_CELL_INTERSECTION",
            "geometry_crs": "EPSG:4326",
            "spatial_transfer_allowed": False,
            "cross_candidate_transfer_allowed": False,
            "minimum_coverage_pct": None,
            "coverage_threshold_status": "UNRESOLVED_NO_ARBITRARY_THRESHOLD",
            "missing_grid_cells_policy": "PRESERVE_COVERAGE_AND_FAIL_CLOSED",
            "partial_coverage_interpretation": "INSUFFICIENT_EVIDENCE_UNLESS_SOURCE_SPECIFIC_METHOD_APPROVED",
            "supported_source_families": ["IMERG", "GOES_RRQPE", "GEOS_CF"],
            "source_use_policy": {
                "IMERG": "RESEARCH_ONLY_WHEN_TIMESTAMPED_GRID_VALUES_ARE_AVAILABLE",
                "GOES_RRQPE": "BLOCKED_UNTIL_CANDIDATE_LEVEL_PRECIPITATION_VALUES_ARE_PERSISTED",
                "GEOS_CF": "FORECAST_ONLY_NEVER_OBSERVATION",
            },
        },
        "scientific_limitations": [
            "Subunit geometry does not make the parent Phase-2 candidate geometry complete.",
            "Sampling contract does not validate activation, thresholds, runoff response, or hydraulic routing.",
            "Outlet/area official confirmation remains independent of research sampling eligibility.",
        ],
    }


def build_lambayeque_child_contracts():
    validation = load_json(LAMBAYEQUE_MIGRATION_VALIDATION)
    if validation.get("status") != "PASS_RESEARCH_ONLY":
        raise SpatialContractError("Lambayeque migration validation is not PASS_RESEARCH_ONLY")
    if validation.get("hydrologic_children_reported_separately") != 2:
        raise SpatialContractError("Lambayeque must retain exactly two separated hydrologic children")
    if validation.get("phase2_registered_candidates_before") != 18 or validation.get("phase2_registered_candidates_after") != 18:
        raise SpatialContractError("Lambayeque migration must not change the 18-candidate Phase-2 count")
    if validation.get("artificial_connector_used") is not False:
        raise SpatialContractError("Lambayeque child units must not use artificial connectors")
    separation = validation.get("separation") or {}
    if separation.get("interior_overlap") is not False:
        raise SpatialContractError("Lambayeque child units must not overlap in their interiors")

    contracts = []
    for unit in validation.get("units") or []:
        child_id = unit.get("candidate_id")
        path = unit.get("output_path")
        expected_sha = unit.get("output_sha256")
        if not child_id or not path or not expected_sha:
            raise SpatialContractError("Lambayeque child unit missing id/path/hash")
        file_path = ROOT / path
        if not file_path.is_file():
            raise SpatialContractError(f"{child_id}: geometry file missing")
        if sha256_file(file_path) != expected_sha:
            raise SpatialContractError(f"{child_id}: geometry file hash mismatch")

        document = load_json(file_path)
        features = document.get("features") or []
        if len(features) != 1:
            raise SpatialContractError(f"{child_id}: expected exactly one official hydrologic feature")
        feature = features[0]
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}

        required = {
            "candidate_id": child_id,
            "parent_candidate_id": LAMBAYEQUE_PARENT_ID,
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "review_status": "REVIEW_ONLY",
            "geometry_role": "official_hydrologic_unit_boundary_research_reference",
        }
        for key, value in required.items():
            if props.get(key) != value:
                raise SpatialContractError(f"{child_id}: {key} expected {value!r}")
        if geometry.get("type") not in POLYGON_TYPES:
            raise SpatialContractError(f"{child_id}: official geometry must be Polygon/MultiPolygon")
        if unit.get("geometry_valid") is not True:
            raise SpatialContractError(f"{child_id}: migration validator reports invalid geometry")

        contracts.append({
            "contract_id": f"phase2-spatial-observation:{LAMBAYEQUE_PARENT_ID}:{child_id}:v0.1",
            "candidate_id": LAMBAYEQUE_PARENT_ID,
            "subunit_id": child_id,
            "contract_scope": "OFFICIAL_HYDROLOGIC_CHILD_UNIT_RESEARCH_ONLY",
            "contract_status": "RESEARCH_SAMPLING_ELIGIBLE",
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "counts_as_candidate_wide_geometry": False,
            "counts_as_operational_geometry": False,
            "geometry_ref": {
                "path": path,
                "feature_selector": {"property": "candidate_id", "value": child_id},
                "geometry_type": geometry.get("type"),
                "geometry_sha256": expected_sha,
                "hash_scope": "GEOJSON_FILE_SHA256",
                "representation": "OFFICIAL_ANA_HYDROLOGIC_UNIT_BOUNDARY",
                "hydrologic_role": props.get("geometry_role"),
                "declared_area_km2": props.get("official_area_km2"),
                "area_semantics": (
                    "OFFICIAL_WHOLE_HYDROLOGIC_UNIT_RESEARCH_CONTEXT_NOT_EVENT_FOOTPRINT"
                ),
                "confidence": props.get("confidence"),
                "candidate_status": props.get("review_status"),
            },
            "outlet_status": {
                "official_confirmation": False,
                "lon": None,
                "lat": None,
                "selection": None,
            },
            "sampling_contract": {
                "method": "AREA_WEIGHTED_GRID_CELL_INTERSECTION",
                "geometry_crs": "EPSG:4326",
                "spatial_transfer_allowed": False,
                "cross_candidate_transfer_allowed": False,
                "minimum_coverage_pct": None,
                "coverage_threshold_status": "UNRESOLVED_NO_ARBITRARY_THRESHOLD",
                "missing_grid_cells_policy": "PRESERVE_COVERAGE_AND_FAIL_CLOSED",
                "partial_coverage_interpretation": "INSUFFICIENT_EVIDENCE_UNLESS_SOURCE_SPECIFIC_METHOD_APPROVED",
                "supported_source_families": ["IMERG", "GOES_RRQPE", "GEOS_CF"],
                "source_use_policy": {
                    "IMERG": "RESEARCH_ONLY_WHOLE_HYDROLOGIC_UNIT_CONTEXT",
                    "GOES_RRQPE": "BLOCKED_UNTIL_CANDIDATE_LEVEL_PRECIPITATION_VALUES_ARE_PERSISTED",
                    "GEOS_CF": "FORECAST_ONLY_NEVER_OBSERVATION",
                },
            },
            "scientific_limitations": [
                "Whole hydrologic-unit rainfall is basin-scale context and is not rainfall for any named local quebrada or event footprint.",
                "The historical parent remains a non-activable grouper and receives no composite geometry.",
                "Sampling does not validate activation, thresholds, runoff response, hydraulic routing, or local impacts.",
            ],
        })

    contracts.sort(key=lambda row: row["subunit_id"])
    expected_children = {
        "lambayeque_chancay_lambayeque_chongoyape",
        "lambayeque_zana_oyotun",
    }
    if {row["subunit_id"] for row in contracts} != expected_children:
        raise SpatialContractError("unexpected Lambayeque hydrologic child set")
    return contracts


def build_candidate_entry(candidate, zone):
    candidate_id = candidate["candidate_id"]
    asset_status = (zone.get("asset_status") or {}).get("geometry")
    readiness = ((zone.get("asset_readiness") or {}).get("geometry") or {})
    presence = readiness.get("data_presence")
    geometry_path = None
    if presence == "PRESENT":
        contract = load_contract(candidate_id)
        geometry_asset = (contract.get("assets") or {}).get("geometry") or {}
        geometry_path = geometry_asset.get("path")

    base = {
        "candidate_id": candidate_id,
        "system_name": candidate.get("system_name"),
        "geometry_asset_status": asset_status,
        "geometry_data_presence": presence,
        "geometry_path": geometry_path,
        "candidate_wide_sampling_ready": False,
        "candidate_wide_contract": None,
        "subunit_contracts": [],
        "excluded_geometry_features": [],
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "activation_gate": "BLOCKED",
    }

    if candidate_id == LAMBAYEQUE_PARENT_ID:
        base["spatial_contract_status"] = "SUBUNIT_RESEARCH_ONLY"
        base["blocker"] = (
            "The historical parent has no composite geometry and remains non-activable; "
            "its two official ANA hydrologic children may be sampled independently for research only."
        )
        base["subunit_contracts"] = build_lambayeque_child_contracts()
        return base

    if presence != "PRESENT" or not geometry_path:
        base["spatial_contract_status"] = "BLOCKED_MISSING_GEOMETRY"
        base["blocker"] = "No reproducible geometry file is present for the candidate geometry asset."
        return base

    geometry = load_geometry_file(geometry_path)
    if geometry is None:
        base["spatial_contract_status"] = "BLOCKED_MISSING_GEOMETRY"
        base["blocker"] = "Geometry path is declared but file is not present."
        return base

    features = geometry.get("features") if geometry.get("type") == "FeatureCollection" else [geometry]
    features = features or []
    candidate_wide_features = []
    subunit_features = []

    for feature in features:
        classification, reason = classify_feature(feature)
        fid = feature_id(feature)
        role = (feature.get("properties") or {}).get("hydrologic_role") or (
            feature.get("properties") or {}
        ).get("feature_role")
        gtype = (feature.get("geometry") or {}).get("type")

        if classification == "ELIGIBLE_RESEARCH_SUBUNIT":
            subunit_features.append(feature)
            continue
        if classification == "ELIGIBLE_CANDIDATE_WIDE_ROLE":
            candidate_wide_features.append(feature)
            continue

        base["excluded_geometry_features"].append(
            {
                "feature_id": fid,
                "role": role,
                "geometry_type": gtype,
                "classification": classification,
                "reason": reason,
            }
        )

    if asset_status == "READY" and candidate_wide_features:
        # Reserved for a later state. No current Phase-2 candidate reaches this branch.
        base["candidate_wide_sampling_ready"] = True
        base["spatial_contract_status"] = "CANDIDATE_WIDE_RESEARCH_READY"
        base["blocker"] = None
        base["candidate_wide_contract"] = {
            "status": "RESERVED_FOR_APPROVED_FULL_CATCHMENT_ROLE",
            "feature_count": len(candidate_wide_features),
        }
        return base

    if subunit_features:
        base["spatial_contract_status"] = "SUBUNIT_RESEARCH_ONLY"
        base["blocker"] = (
            "Candidate-wide geometry is not READY; only explicitly delimited research subunits "
            "may be sampled without promoting the parent candidate."
        )
        base["subunit_contracts"] = [
            build_subunit_contract(candidate_id, geometry_path, feature)
            for feature in subunit_features
        ]
        return base

    base["spatial_contract_status"] = "NON_CATCHMENT_GEOMETRY_ONLY"
    base["blocker"] = (
        "A reproducible geometry file exists, but it contains no approved full-catchment "
        "or eligible research-subunit drainage polygon."
    )
    return base


def build():
    inventory = load_json(INVENTORY_PATH)
    catalog = load_json(CATALOG_PATH)
    candidates = inventory.get("candidates") or []
    zones = {z["candidate_id"]: z for z in catalog.get("zones") or []}

    if len(candidates) != 18 or len(zones) != 18:
        raise SpatialContractError(
            f"Phase-2 candidate count mismatch: inventory={len(candidates)} catalog={len(zones)}"
        )

    records = []
    for candidate in candidates:
        cid = candidate["candidate_id"]
        if cid not in zones:
            raise SpatialContractError(f"candidate missing from catalog: {cid}")
        records.append(
            build_candidate_entry(candidate, zones[cid])
        )

    counts = {}
    for record in records:
        status = record["spatial_contract_status"]
        counts[status] = counts.get(status, 0) + 1

    subunit_contracts = [
        contract
        for record in records
        for contract in record.get("subunit_contracts") or []
    ]

    return {
        "version": "phase2-spatial-observation-contracts-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "decision_thresholds": None,
        "activation_gate": "BLOCKED",
        "relationship_to_phase2": {
            "registered_candidate_count": 18,
            "changes_candidate_count": False,
            "changes_activation_gates": False,
            "changes_promotion_gates": False,
            "changes_v08_scope": False,
        },
        "guardrails": {
            "regulatory_corridor_is_not_catchment": True,
            "river_margin_is_not_catchment": True,
            "line_geometry_is_not_area_sampling_geometry": True,
            "subunit_contract_does_not_complete_parent_candidate": True,
            "cross_candidate_spatial_transfer_forbidden": True,
            "sampling_contract_is_not_activation_validation": True,
            "missing_geometry_is_blocked_not_low_risk": True,
        },
        "candidate_records": records,
        "summary": {
            "candidate_count": len(records),
            "candidate_wide_ready_count": sum(
                record["candidate_wide_sampling_ready"] for record in records
            ),
            "subunit_research_only_candidate_count": counts.get("SUBUNIT_RESEARCH_ONLY", 0),
            "non_catchment_geometry_only_count": counts.get("NON_CATCHMENT_GEOMETRY_ONLY", 0),
            "blocked_missing_geometry_count": counts.get("BLOCKED_MISSING_GEOMETRY", 0),
            "research_subunit_contract_count": len(subunit_contracts),
            "operational_spatial_contract_count": 0,
        },
    }


def generate(write=True):
    result = build()
    if write:
        write_json(OUT_PATH, result)
    return result


def main():
    result = generate(write=True)
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
