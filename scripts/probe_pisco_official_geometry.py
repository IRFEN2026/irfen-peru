#!/usr/bin/env python3
"""Freeze/replay official ANA Cuenca Pisco geometry as Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. Only the ANA hydrologic unit Cuenca Pisco (13752)
is materialized. San Andres local drainage, tributary ravines, event footprints,
outlets, hydraulic capacity, operational thresholds and negative controls remain
unresolved and are never inferred by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "ica_pisco_san_andres"
QUERY_NAME = "Cuenca Pisco"
EXPECTED_CODE = "13752"
EXPECTED_AREA_KM2 = 4208.7453
EXPECTED_CANONICAL_SOURCE_SHA256 = "693bcd668bcc5f692a04d516976908757172c6274962e9f4ca0a6c6d9e799e9b"
BOOTSTRAP_RAW_RESPONSE_SHA256 = "f630aaddd560de40dd3b6327560fbcc1437790677d1e47bc1e7835be29170c9c"
SOURCE_ID = "ANA-IDEP-UH-PISCO-13752-20260922"
BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SOURCE_DIR = ROOT / "site/data/phase2/sources/pisco_hydrologic_context"
SOURCE = SOURCE_DIR / "ana_cuenca_pisco_13752.geojson"
SOURCE_INVENTORY = SOURCE_DIR / "source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/ica_pisco_san_andres_pisco_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/ica_pisco_san_andres_geometry_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/ica_pisco_san_andres.json"
INVENTORIES = [ROOT / "config/phase2_candidate_inventory_v0_1.json", ROOT / "config/phase2_candidate_inventory_v0_2.json"]

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


def query_url() -> str:
    return BASE + "?" + urlencode({
        "where": f"NOMBRE='{QUERY_NAME}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    })


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def validate_source(data: dict) -> dict:
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) != 1:
        raise ValueError("expected exactly one official Cuenca Pisco feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if str(props.get("CODIGO")) != EXPECTED_CODE or props.get("NOMBRE") != QUERY_NAME:
        raise ValueError(f"unexpected ANA identity: {props}")
    if abs(float(props.get("AREA_KM2") or 0) - EXPECTED_AREA_KM2) > 0.0001:
        raise ValueError("official Cuenca Pisco area changed from frozen bootstrap evidence")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Cuenca Pisco geometry is not polygonal")
    return feature


def fetch_source() -> tuple[dict, str]:
    request = Request(query_url(), headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    validate_source(data)
    digest = sha_bytes(canonical(data))
    if digest != EXPECTED_CANONICAL_SOURCE_SHA256:
        raise ValueError(f"ANA Cuenca Pisco canonical source changed: {digest}")
    return data, sha_bytes(raw)


def source_record_from_inventory() -> dict:
    inv = load(SOURCE_INVENTORY)
    for key, value in GUARDS.items():
        if inv.get(key) != value:
            raise ValueError(f"unsafe Pisco source inventory guard {key}")
    sources = inv.get("sources") or []
    if len(sources) != 1 or sources[0].get("source_id") != SOURCE_ID:
        raise ValueError("unexpected Pisco source inventory")
    row = sources[0]
    if row.get("canonical_sha256") != EXPECTED_CANONICAL_SOURCE_SHA256:
        raise ValueError("Pisco source inventory canonical SHA mismatch")
    return row


def expected_inventory_document(doc: dict) -> dict:
    updated = json.loads(json.dumps(doc))
    rows = [row for row in updated.get("candidates") or [] if row.get("candidate_id") == CANDIDATE_ID]
    if len(rows) != 1:
        raise ValueError("Pisco candidate missing from Phase-2 inventory")
    row = rows[0]
    sources = list(row.get("official_sources") or [])
    if SOURCE_ID not in sources:
        sources.append(SOURCE_ID)
    row["official_sources"] = sources
    updated.setdefault("official_source_catalog", {})[SOURCE_ID] = query_url()
    return updated


def expected_contract_document(doc: dict, geometry_rel: str) -> dict:
    updated = json.loads(json.dumps(doc))
    if updated.get("candidate_id") != CANDIDATE_ID:
        raise ValueError("Pisco contract identity mismatch")
    if updated.get("deployment_status") != "RESEARCH_ONLY" or updated.get("production_use") is not False:
        raise ValueError("unsafe Pisco contract state")
    if updated.get("decision_thresholds") is not None or updated.get("hydraulic_factors") is not None:
        raise ValueError("Pisco decision fields unexpectedly populated")
    if updated.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK":
        raise ValueError("Pisco missing-data guard changed")
    if (updated.get("validation") or {}).get("activation_gate") != "BLOCKED":
        raise ValueError("Pisco activation gate changed")
    updated["test_mode"] = "TEST_ONLY"
    updated["production_ready"] = False
    updated["operational_alerting_enabled"] = False
    source_ids = list(updated.get("official_source_ids") or [])
    if SOURCE_ID not in source_ids:
        source_ids.append(SOURCE_ID)
    updated["official_source_ids"] = source_ids
    geom = updated.setdefault("assets", {}).setdefault("geometry", {})
    geom_sources = list(geom.get("source_ids") or [])
    if SOURCE_ID not in geom_sources:
        geom_sources.append(SOURCE_ID)
    geom.update({"status": "PARTIAL", "path": geometry_rel, "source_ids": geom_sources})
    note = (
        "Official ANA Cuenca Pisco geometry is normalized only as PARTIAL research context; San Andres local drainage, tributary ravines, event footprints and cross-component routing remain unresolved."
    )
    notes = list(updated.get("notes") or [])
    if note not in notes:
        notes.append(note)
    updated["notes"] = notes
    return updated


def build_documents(source: dict, source_record: dict) -> tuple[dict, dict]:
    feature = validate_source(source)
    props = feature["properties"]
    normalized = {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "candidate_id": CANDIDATE_ID,
            "geometry_status": "PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT",
            "source_id": SOURCE_ID,
            "source_snapshot_sha256": source_record["canonical_sha256"],
            "coverage": "Official ANA Cuenca Pisco unit 13752 only; San Andres local drainage and tributary ravines remain separate unresolved components and are not polygonized here.",
            "map_disclaimer": "Official basin context RESEARCH_ONLY; not an event footprint, inundation extent, hydraulic-capacity model, risk level or alert layer.",
        },
        "features": [{
            "type": "Feature",
            "id": "ica_pisco_basin_context_13752",
            "properties": {
                "candidate_id": CANDIDATE_ID,
                "unit_id": "ica_pisco_basin_context_13752",
                "name": "Cuenca Pisco · contexto hidrológico ANA",
                "feature_role": "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT",
                "hydrologic_role": "OFFICIAL_BASIN_BOUNDARY_NOT_EVENT_FOOTPRINT",
                "deployment_status": "RESEARCH_ONLY",
                "test_mode": "TEST_ONLY",
                "review_status": "REVIEW_ONLY",
                "activation_gate": "BLOCKED",
                "production_use": False,
                "production_ready": False,
                "alerting_enabled": False,
                "operational_alerting_enabled": False,
                "loaded_into_operational_calculation": False,
                "carries_alert_values": False,
                "carries_risk_classification": False,
                "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
                "decision_thresholds": None,
                "hydraulic_factors": None,
                "official_hydrologic_unit_code": str(props["CODIGO"]),
                "official_hydrologic_unit_name": props["NOMBRE"],
                "official_area_km2": float(props["AREA_KM2"]),
                "source_id": SOURCE_ID,
                "source_crs": "EPSG:4326 requested from ANA IDEP ArcGIS service",
                "geometry_method": "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM",
                "district_boundary_used": False,
                "dem_used": False,
                "outlet_used": False,
                "outlet": None,
                "san_andres_local_drainage_geometry_resolved": False,
                "tributary_ravines_geometry_resolved": False,
                "event_footprint_asserted": False,
                "counts_as_complete_candidate_geometry": False,
                "confidence": "HIGH_OFFICIAL_BASIN_GEOMETRY",
                "warning": "Basin context only; do not infer San Andres drainage routing, event extent, hydraulic capacity, thresholds, risk or alert state.",
            },
            "geometry": feature["geometry"],
        }],
    }
    validation = {
        "version": "phase2-pisco-geometry-validation-v1",
        **GUARDS,
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidate_id": CANDIDATE_ID,
        "source_snapshot_path": source_record["local_path"],
        "source_snapshot_sha256": source_record["canonical_sha256"],
        "normalized_geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "normalized_geometry_sha256": sha_bytes(canonical(normalized)),
        "official_unit": {"code": str(props["CODIGO"]), "name": props["NOMBRE"], "area_km2": float(props["AREA_KM2"])},
        "component_resolution": {
            "cuenca_pisco_polygon": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "san_andres_local_drainage": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "tributary_ravines": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "event_footprint": "NOT_ASSERTED",
            "hydraulic_capacity": "UNKNOWN",
        },
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
        "activation_gate": "BLOCKED",
    }
    return normalized, validation


def sync(check_only: bool) -> None:
    record = source_record_from_inventory()
    source = load(ROOT / record["local_path"])
    if sha_bytes(canonical(source)) != EXPECTED_CANONICAL_SOURCE_SHA256:
        raise ValueError("frozen ANA Pisco canonical SHA-256 mismatch")
    normalized, validation = build_documents(source, record)
    geom_rel = GEOMETRY.relative_to(ROOT).as_posix()
    expected: dict[Path, object] = {
        GEOMETRY: normalized,
        VALIDATION: validation,
        CONTRACT: expected_contract_document(load(CONTRACT), geom_rel),
    }
    for path in INVENTORIES:
        expected[path] = expected_inventory_document(load(path))
    if check_only:
        for path, value in expected.items():
            if not path.is_file() or path.read_bytes() != canonical(value):
                raise ValueError(f"stale or missing deterministic artifact: {path.relative_to(ROOT)}")
    else:
        for path, value in expected.items():
            write(path, value)


def refresh_source() -> None:
    source, refresh_raw_sha = fetch_source()
    feature = validate_source(source)
    write(SOURCE, source)
    props = feature["properties"]
    inventory = {
        "version": "phase2-pisco-source-inventory-v1",
        **GUARDS,
        "sources": [{
            "candidate_id": CANDIDATE_ID,
            "source_id": SOURCE_ID,
            "institution": "Autoridad Nacional del Agua / IDEP",
            "url": query_url(),
            "role": "official_hydrologic_unit_geometry_research_context",
            "local_path": SOURCE.relative_to(ROOT).as_posix(),
            "canonical_sha256": EXPECTED_CANONICAL_SOURCE_SHA256,
            "bootstrap_raw_response_sha256": BOOTSTRAP_RAW_RESPONSE_SHA256,
            "refresh_raw_response_sha256": refresh_raw_sha,
            "bootstrap_workflow_run_id": 35797426794,
            "bootstrap_artifact_id": 10724201745,
            "bootstrap_artifact_digest": "sha256:2bb7c2a7b5eca665bde256e9a09d90f84beff4d1d8a52e09724056b368544d1c",
            "official_unit_code": str(props["CODIGO"]),
            "official_unit_name": props["NOMBRE"],
            "official_area_km2": float(props["AREA_KM2"]),
            "frozen_at_utc": "2026-09-22T23:26:40Z",
        }],
        "forbidden": [
            "treat the basin polygon as an event or inundation footprint",
            "assign San Andres local drainage or tributary ravines to this basin polygon without component-resolved evidence",
            "invent ravine, outlet or connector geometry",
            "infer hydraulic capacity or operational thresholds",
            "infer negative controls from documentary silence",
        ],
    }
    write(SOURCE_INVENTORY, inventory)
    sync(check_only=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source and args.check_only:
        raise ValueError("--refresh-source and --check-only are mutually exclusive")
    if args.refresh_source:
        refresh_source()
    else:
        if not SOURCE_INVENTORY.is_file():
            raise ValueError("frozen ANA Pisco source inventory missing; use --refresh-source once")
        sync(check_only=args.check_only)
        if not args.check_only:
            sync(check_only=False)
    print(json.dumps({
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidate_id": CANDIDATE_ID,
        "official_unit_code": EXPECTED_CODE,
        "counts_as_complete_candidate_geometry": False,
        "activation_gate": "BLOCKED",
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
