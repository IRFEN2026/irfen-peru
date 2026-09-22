#!/usr/bin/env python3
"""Freeze official ANA Cuenca Omas geometry as Phase-2 research context.

RESEARCH_ONLY / TEST_ONLY. The emitted polygon is the official ANA hydrologic
unit 1375512 only. It does not resolve local Asia ravines, assign the 2024
huaico to a named watercourse, convert regulatory fajas to event footprints,
or infer hydraulic capacity, thresholds, negative controls or activation.
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
CANDIDATE_ID = "lima_sur_asia_omas"
QUERY_NAME = "Cuenca Omas"
EXPECTED_CODE = "1375512"
SOURCE_ID = "ANA-IDEP-UH-OMAS-1375512-20260922"
BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SOURCE_DIR = ROOT / "site/data/phase2/sources/asia_omas_hydrologic_context"
SOURCE = SOURCE_DIR / "ana_cuenca_omas_1375512.geojson"
SOURCE_INVENTORY = SOURCE_DIR / "source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_sur_asia_omas_omas_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_sur_asia_omas_geometry_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_asia_omas.json"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/asia_omas_official_spatial_exposure_context_2016_2024.json"
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


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def validate_source(data: dict) -> dict:
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) != 1:
        raise ValueError("expected exactly one official Cuenca Omas feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if str(props.get("CODIGO")) != EXPECTED_CODE or props.get("NOMBRE") != QUERY_NAME:
        raise ValueError(f"unexpected ANA identity: {props}")
    if float(props.get("AREA_KM2") or 0) <= 0:
        raise ValueError("official Cuenca Omas area missing or invalid")
    if abs(float(props["AREA_KM2"]) - 1111.12) > 1.0:
        raise ValueError("official Cuenca Omas area conflicts materially with frozen evidence context")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Cuenca Omas geometry is not polygonal")
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
    for key, value in GUARDS.items():
        if inv.get(key) != value:
            raise ValueError(f"unsafe source inventory guard {key}")
    sources = inv.get("sources") or []
    if len(sources) != 1 or sources[0].get("source_id") != SOURCE_ID:
        raise ValueError("unexpected Asia-Omas source inventory")
    return sources[0]


def expected_inventory_document(doc: dict) -> dict:
    updated = json.loads(json.dumps(doc))
    rows = [row for row in updated.get("candidates") or [] if row.get("candidate_id") == CANDIDATE_ID]
    if len(rows) != 1:
        raise ValueError("Asia-Omas candidate missing from Phase-2 inventory")
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
        raise ValueError("Asia-Omas contract identity mismatch")
    if updated.get("deployment_status") != "RESEARCH_ONLY" or updated.get("production_use") is not False:
        raise ValueError("unsafe Asia-Omas contract state")
    if updated.get("decision_thresholds") is not None or updated.get("hydraulic_factors") is not None:
        raise ValueError("Asia-Omas decision fields unexpectedly populated")
    if updated.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK":
        raise ValueError("Asia-Omas missing-data guard changed")
    if (updated.get("validation") or {}).get("activation_gate") != "BLOCKED":
        raise ValueError("Asia-Omas activation gate changed")
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
        "Official ANA Cuenca Omas geometry is normalized only as PARTIAL research context; local Asia ravines, coastal fans, event footprints and cross-component routing remain unresolved."
    )
    notes = list(updated.get("notes") or [])
    if note not in notes:
        notes.append(note)
    updated["notes"] = notes
    return updated


def build_documents(source: dict, source_record: dict) -> tuple[dict, dict]:
    feature = validate_source(source)
    evidence = load(EVIDENCE)
    unit = evidence["official_hydrologic_context"]["official_unit"]
    if unit["code"] != EXPECTED_CODE or unit["name"] != QUERY_NAME:
        raise ValueError("committed Asia-Omas hydrologic identity changed")
    sep = evidence["component_separation"]
    if not sep["official_omas_unit_confirmed"]:
        raise ValueError("official Omas unit is no longer confirmed")
    if sep["local_asia_ravines_individually_normalized"]:
        raise ValueError("local Asia ravines unexpectedly marked normalized")
    props = feature["properties"]
    normalized = {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "candidate_id": CANDIDATE_ID,
            "geometry_status": "PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT",
            "source_id": SOURCE_ID,
            "source_snapshot_sha256": source_record["canonical_sha256"],
            "coverage": "Official ANA Cuenca Omas unit 1375512 only; local Asia ravines and coastal fans remain separate unresolved components and are not independently polygonized here.",
            "map_disclaimer": "Official basin context RESEARCH_ONLY; not an event footprint, hazard extent, hydraulic-capacity model, risk level or alert layer.",
        },
        "features": [{
            "type": "Feature",
            "id": "lima_sur_omas_basin_context_1375512",
            "properties": {
                "candidate_id": CANDIDATE_ID,
                "unit_id": "lima_sur_omas_basin_context_1375512",
                "name": "Cuenca Omas · contexto hidrológico ANA",
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
                "local_asia_ravines_geometry_resolved": False,
                "coastal_fans_geometry_resolved": False,
                "event_2024_assigned_to_named_watercourse": False,
                "counts_as_complete_candidate_geometry": False,
                "confidence": "HIGH_OFFICIAL_BASIN_GEOMETRY",
                "warning": "Basin context only; do not infer the 2024 huaico watercourse, inundation, ravine routing, hydraulic capacity, thresholds, risk or alert state.",
            },
            "geometry": feature["geometry"],
        }],
    }
    validation = {
        "version": "phase2-asia-omas-geometry-validation-v1",
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
            "cuenca_omas_polygon": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "local_asia_ravines": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "coastal_fans": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "2024_huaico_named_watercourse": "UNRESOLVED_NOT_ASSIGNED",
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
    if sha_bytes(canonical(source)) != record["canonical_sha256"]:
        raise ValueError("frozen ANA Omas canonical SHA-256 mismatch")
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
        "version": "phase2-asia-omas-source-inventory-v1",
        **GUARDS,
        "sources": [{
            "candidate_id": CANDIDATE_ID,
            "source_id": SOURCE_ID,
            "institution": "Autoridad Nacional del Agua / IDEP",
            "url": query_url(),
            "role": "official_hydrologic_unit_geometry_research_context",
            "local_path": SOURCE.relative_to(ROOT).as_posix(),
            "canonical_sha256": sha_bytes(canonical(source)),
            "raw_response_sha256_at_freeze": raw_sha,
            "official_unit_code": str(props["CODIGO"]),
            "official_unit_name": props["NOMBRE"],
            "official_area_km2": float(props["AREA_KM2"]),
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        }],
        "forbidden": [
            "treat basin polygon or regulatory faja as an event footprint",
            "assign the 2024 Asia huaico to Omas, Rio Chico or any local ravine without component-resolved evidence",
            "invent local Asia ravine or coastal-fan geometry",
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
            raise ValueError("frozen ANA Omas source inventory missing; use --refresh-source once")
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
