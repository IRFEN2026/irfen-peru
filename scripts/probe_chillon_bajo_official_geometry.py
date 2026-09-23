#!/usr/bin/env python3
"""Freeze official ANA Chillon basin geometry as Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. The emitted polygon is only the official ANA
hydrologic unit 137556. It does not resolve lower-river reaches, tributary
ravines, event footprints, exposure, hydraulic capacity, controls, thresholds
or activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "lima_norte_chillon_bajo"
QUERY_NAME = "Cuenca Chillón"
EXPECTED_CODE = "137556"
SOURCE_ID = "ANA-IDEP-UH-CHILLON-137556-20260923"
BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SOURCE_DIR = ROOT / "site/data/phase2/sources/chillon_bajo_hydrologic_context"
SOURCE = SOURCE_DIR / "ana_cuenca_chillon_137556.geojson"
SOURCE_INVENTORY = SOURCE_DIR / "source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_chillon_bajo_chillon_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_chillon_bajo_geometry_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_chillon_bajo.json"
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
    features = data.get("features") or []
    if data.get("type") != "FeatureCollection" or len(features) != 1:
        raise ValueError("expected exactly one official Chillon feature")
    feature = features[0]
    props = feature.get("properties") or {}
    if str(props.get("CODIGO")) != EXPECTED_CODE:
        raise ValueError(f"unexpected ANA code: {props.get('CODIGO')}")
    if props.get("NOMBRE") != QUERY_NAME:
        raise ValueError(f"unexpected ANA name: {props.get('NOMBRE')}")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Chillon geometry is not polygonal")
    if float(props.get("AREA_KM2") or 0) <= 0:
        raise ValueError("official hydrologic-unit area missing or invalid")
    return feature


def fetch_source() -> tuple[dict, str]:
    request = Request(query_url(), headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    validate_source(data)
    return data, sha_bytes(raw)


def source_record_from_inventory() -> dict:
    inv = load(SOURCE_INVENTORY)
    for key, expected in GUARDS.items():
        if inv.get(key) != expected:
            raise ValueError(f"unsafe source inventory guard: {key}")
    sources = inv.get("sources") or []
    if len(sources) != 1 or sources[0].get("source_id") != SOURCE_ID:
        raise ValueError("unexpected Chillon source inventory")
    return sources[0]


def expected_inventory_document(doc: dict) -> dict:
    updated = json.loads(json.dumps(doc))
    rows = [row for row in updated.get("candidates") or [] if row.get("candidate_id") == CANDIDATE_ID]
    if len(rows) != 1:
        raise ValueError("Chillon Bajo candidate missing from Phase-2 inventory")
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
        raise ValueError("Chillon Bajo contract identity mismatch")
    if updated.get("deployment_status") != "RESEARCH_ONLY" or updated.get("production_use") is not False:
        raise ValueError("unsafe Chillon Bajo contract state")
    if updated.get("decision_thresholds") is not None or updated.get("hydraulic_factors") is not None:
        raise ValueError("Chillon Bajo decision fields unexpectedly populated")
    if updated.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK":
        raise ValueError("Chillon Bajo missing-data guard changed")
    if (updated.get("validation") or {}).get("activation_gate") != "BLOCKED":
        raise ValueError("Chillon Bajo activation gate changed")
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
        "Official ANA Cuenca Chillón unit 137556 is normalized only as PARTIAL whole-basin context; lower-river reaches and tributary ravines remain unresolved and must be represented separately when reproducible geometry exists."
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
            "coverage": "Official ANA Cuenca Chillón hydrologic-unit polygon only; lower-river reaches and tributary ravines remain unresolved components.",
            "map_disclaimer": "Official whole-basin context RESEARCH_ONLY; not a lower-river flood extent, event footprint, hydraulic-capacity model, risk level or alert layer.",
        },
        "features": [{
            "type": "Feature",
            "id": "lima_norte_chillon_bajo_basin_context_137556",
            "properties": {
                "candidate_id": CANDIDATE_ID,
                "unit_id": "lima_norte_chillon_bajo_basin_context_137556",
                "name": "Cuenca Chillón · contexto hidrológico ANA",
                "feature_role": "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT",
                "hydrologic_role": "OFFICIAL_BASIN_BOUNDARY_NOT_LOWER_RIVER_OR_EVENT_FOOTPRINT",
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
                "lower_river_reaches_geometry_resolved": False,
                "tributary_ravines_geometry_resolved": False,
                "event_footprint_resolved": False,
                "counts_as_complete_candidate_geometry": False,
                "confidence": "HIGH_OFFICIAL_BASIN_GEOMETRY",
                "warning": "Whole-basin context only; do not infer lower-river flood extent, tributary routing, hydraulic capacity, thresholds, risk or alert state.",
            },
            "geometry": feature["geometry"],
        }],
    }
    validation = {
        "version": "phase2-chillon-bajo-geometry-validation-v1",
        **GUARDS,
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidate_id": CANDIDATE_ID,
        "source_snapshot_path": source_record["local_path"],
        "source_snapshot_sha256": source_record["canonical_sha256"],
        "normalized_geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "normalized_geometry_sha256": sha_bytes(canonical(normalized)),
        "official_unit": {
            "code": str(props["CODIGO"]),
            "name": props["NOMBRE"],
            "area_km2": float(props["AREA_KM2"]),
        },
        "component_resolution": {
            "chillon_basin_polygon": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "lower_river_reaches": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "tributary_ravines": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "event_footprint": "NOT_ASSERTED",
            "hydraulic_capacity": "UNKNOWN",
            "negative_controls": "NOT_ASSERTED",
        },
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
        "activation_gate": "BLOCKED",
    }
    return normalized, validation


def sync(check_only: bool) -> None:
    record = source_record_from_inventory()
    source_path = ROOT / record["local_path"]
    source = load(source_path)
    if sha_bytes(canonical(source)) != record["canonical_sha256"]:
        raise ValueError("frozen ANA Chillon canonical SHA-256 mismatch")
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
    source, raw_sha = fetch_source()
    feature = validate_source(source)
    write(SOURCE, source)
    props = feature["properties"]
    inventory = {
        "version": "phase2-chillon-bajo-source-inventory-v1",
        **GUARDS,
        "sources": [{
            "candidate_id": CANDIDATE_ID,
            "source_id": SOURCE_ID,
            "institution": "Autoridad Nacional del Agua / IDEP",
            "url": query_url(),
            "role": "official_whole_basin_geometry_research_context",
            "local_path": SOURCE.relative_to(ROOT).as_posix(),
            "canonical_sha256": sha_bytes(canonical(source)),
            "raw_response_sha256_at_freeze": raw_sha,
            "official_unit_code": str(props["CODIGO"]),
            "official_unit_name": props["NOMBRE"],
            "official_area_km2": float(props["AREA_KM2"]),
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        }],
        "forbidden": [
            "treat whole-basin polygon as lower-river or event/inundation footprint",
            "invent tributary-ravine or individual river-reach geometry",
            "connect independent hydrologic components artificially",
            "infer hydraulic capacity, discharge or operational thresholds",
            "infer negative controls from documentary silence",
            "derive risk levels or alerts",
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
            raise ValueError("frozen ANA Chillon source inventory missing; use --refresh-source once")
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
