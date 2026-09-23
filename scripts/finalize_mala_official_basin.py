#!/usr/bin/env python3
"""Freeze ANA Cuenca Mala as PARTIAL Phase-2 research geometry.

RESEARCH_ONLY / TEST_ONLY. This only materializes official hydrologic-unit
context for Cuenca Mala (ANA IDEP unit 137552). It does not resolve tributary
ravines, event footprints, outlets, hydraulic capacity, thresholds, negative
controls, risk, activation or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "lima_sur_mala"
SOURCE_ID = "ANA-IDEP-UH-MALA-137552-20260923"
EXPECTED_CODE = "137552"
EXPECTED_NAME = "Cuenca Mala"
EXPECTED_AREA = 2319.7069
EXPECTED_SOURCE_SHA256 = "fd2bc3c148689c6a24eaa150a5bcb02c86a2b62117f32c2f06f558dc855eada4"
QUERY_URL = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query?where=NOMBRE%3D%27Cuenca+Mala%27&outFields=%2A&returnGeometry=true&outSR=4326&geometryPrecision=7&f=geojson"
SOURCE = ROOT / "site/data/phase2/sources/mala_hydrologic_context/ana_cuenca_mala_137552.geojson"
SOURCE_INVENTORY = ROOT / "site/data/phase2/sources/mala_hydrologic_context/source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_sur_mala_mala_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_sur_mala_geometry_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_mala.json"
PHASE2_CATALOG = ROOT / "site/data/phase2/catalog.json"
MAP_CATALOG = ROOT / "site/data/map_layers.json"

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


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def validate_source(data: dict) -> dict:
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) != 1:
        raise ValueError("expected exactly one official Cuenca Mala feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if str(props.get("CODIGO")) != EXPECTED_CODE or props.get("NOMBRE") != EXPECTED_NAME:
        raise ValueError(f"unexpected ANA Cuenca Mala identity: {props}")
    if abs(float(props.get("AREA_KM2") or 0) - EXPECTED_AREA) > 0.001:
        raise ValueError("official Cuenca Mala area changed from frozen bootstrap")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Cuenca Mala geometry is not polygonal")
    digest = sha_bytes(canonical(data))
    if digest != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"ANA Cuenca Mala canonical source hash changed: {digest}")
    return feature


def fetch_source() -> dict:
    request = Request(QUERY_URL, headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))
    validate_source(data)
    return data


def build_geometry(source: dict) -> dict:
    feature = validate_source(source)
    props = feature["properties"]
    return {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "candidate_id": CANDIDATE_ID,
            "geometry_status": "PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT",
            "source_id": SOURCE_ID,
            "source_snapshot_sha256": EXPECTED_SOURCE_SHA256,
            "coverage": "Official ANA Cuenca Mala unit 137552 only; tributary ravines and river reaches remain unresolved separate components.",
            "map_disclaimer": "Official basin context RESEARCH_ONLY; not an event footprint, inundation extent, hydraulic-capacity model, risk level or alert layer.",
        },
        "features": [{
            "type": "Feature",
            "id": "lima_sur_mala_basin_context_137552",
            "properties": {
                "candidate_id": CANDIDATE_ID,
                "unit_id": "lima_sur_mala_basin_context_137552",
                "name": "Cuenca Mala · contexto hidrológico ANA",
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
                "tributary_ravines_geometry_resolved": False,
                "river_reaches_geometry_resolved": False,
                "counts_as_complete_candidate_geometry": False,
                "confidence": "HIGH_OFFICIAL_BASIN_GEOMETRY",
                "warning": "Basin context only; do not infer tributary routing, event extent, hydraulic capacity, thresholds, risk, activation or alert state.",
            },
            "geometry": feature["geometry"],
        }],
    }


def expected_contract(current: dict) -> dict:
    doc = json.loads(json.dumps(current))
    if doc.get("candidate_id") != CANDIDATE_ID:
        raise ValueError("Mala contract identity mismatch")
    if doc.get("deployment_status") != "RESEARCH_ONLY" or doc.get("production_use") is not False:
        raise ValueError("unsafe Mala contract")
    if doc.get("decision_thresholds") is not None or doc.get("hydraulic_factors") is not None:
        raise ValueError("Mala decision fields unexpectedly populated")
    if doc.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK":
        raise ValueError("Mala missing-data guard changed")
    if (doc.get("validation") or {}).get("activation_gate") != "BLOCKED":
        raise ValueError("Mala activation gate changed")
    doc["test_mode"] = "TEST_ONLY"
    doc["production_ready"] = False
    doc["operational_alerting_enabled"] = False
    doc["assets"]["geometry"] = {
        "status": "PARTIAL",
        "path": GEOMETRY.relative_to(ROOT).as_posix(),
        "source_ids": [SOURCE_ID],
    }
    note = "Official ANA Cuenca Mala geometry is normalized only as PARTIAL research context; tributary ravines, river reaches, event footprints and cross-component routing remain unresolved."
    notes = list(doc.get("notes") or [])
    if note not in notes:
        notes.append(note)
    doc["notes"] = notes
    return doc


def validation_doc(geometry: dict) -> dict:
    return {
        "version": "phase2-mala-geometry-validation-v1",
        **GUARDS,
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidate_id": CANDIDATE_ID,
        "source_snapshot_path": SOURCE.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": EXPECTED_SOURCE_SHA256,
        "normalized_geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "normalized_geometry_sha256": sha_bytes(canonical(geometry)),
        "official_unit": {"code": EXPECTED_CODE, "name": EXPECTED_NAME, "area_km2": EXPECTED_AREA},
        "component_resolution": {
            "cuenca_mala_polygon": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "tributary_ravines": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "river_reaches": "UNRESOLVED_NO_GEOMETRY_DRAWN",
            "event_footprint": "NOT_ASSERTED",
            "hydraulic_capacity": "UNKNOWN",
        },
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
    }


def source_inventory_doc() -> dict:
    return {
        "version": "phase2-mala-source-inventory-v1",
        **GUARDS,
        "sources": [{
            "candidate_id": CANDIDATE_ID,
            "source_id": SOURCE_ID,
            "institution": "Autoridad Nacional del Agua / IDEP",
            "url": QUERY_URL,
            "role": "official_hydrologic_unit_geometry_research_context",
            "local_path": SOURCE.relative_to(ROOT).as_posix(),
            "canonical_sha256": EXPECTED_SOURCE_SHA256,
            "official_unit_code": EXPECTED_CODE,
            "official_unit_name": EXPECTED_NAME,
            "official_area_km2": EXPECTED_AREA,
            "acquired_at_utc": "2026-09-22T23:48:20Z",
            "bootstrap_workflow_run_id": 35799156003,
            "bootstrap_artifact_digest": "sha256:9b3c23425314634f0ada055a39e7167703b5807cc355d6a339bb47979012a1db",
        }],
        "forbidden": [
            "treat basin polygon as an event footprint",
            "invent tributary ravine, river-reach or outlet geometry",
            "infer hydraulic capacity or historical discharge from basin geometry",
            "infer operational thresholds or activation",
            "infer negative controls from documentary silence",
        ],
    }


def materialize() -> None:
    source = fetch_source()
    geometry = build_geometry(source)
    write(SOURCE, source)
    write(SOURCE_INVENTORY, source_inventory_doc())
    write(GEOMETRY, geometry)
    write(VALIDATION, validation_doc(geometry))
    write(CONTRACT, expected_contract(load(CONTRACT)))
    subprocess.run([sys.executable, str(ROOT / "scripts/build_phase2_catalog.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/build_map_layer_catalog.py")], cwd=ROOT, check=True)
    check()


def check() -> None:
    source = load(SOURCE)
    validate_source(source)
    inv = load(SOURCE_INVENTORY)
    for key, value in GUARDS.items():
        if inv.get(key) != value:
            raise ValueError(f"unsafe Mala source inventory guard: {key}")
    rows = inv.get("sources") or []
    if len(rows) != 1 or rows[0].get("canonical_sha256") != EXPECTED_SOURCE_SHA256:
        raise ValueError("Mala frozen source inventory mismatch")
    geometry = load(GEOMETRY)
    expected_geometry = build_geometry(source)
    if canonical(geometry) != canonical(expected_geometry):
        raise ValueError("Mala normalized geometry is not deterministic from frozen source")
    validation = load(VALIDATION)
    if validation != validation_doc(expected_geometry):
        raise ValueError("Mala validation record is stale")
    contract = load(CONTRACT)
    geom = contract.get("assets", {}).get("geometry", {})
    if geom != {"status":"PARTIAL","path":GEOMETRY.relative_to(ROOT).as_posix(),"source_ids":[SOURCE_ID]}:
        raise ValueError("Mala contract geometry asset is not frozen PARTIAL context")
    for key, value in (("deployment_status","RESEARCH_ONLY"),("test_mode","TEST_ONLY"),("production_use",False),("production_ready",False),("operational_alerting_enabled",False),("decision_thresholds",None),("hydraulic_factors",None),("missing_data_rule","UNKNOWN_NOT_LOW_RISK")):
        if contract.get(key) != value:
            raise ValueError(f"unsafe Mala contract guard: {key}")
    if contract.get("alerting_enabled") is not False or contract["validation"].get("activation_gate") != "BLOCKED":
        raise ValueError("Mala alert/activation guard changed")
    phase2 = {r["candidate_id"]: r for r in load(PHASE2_CATALOG)["zones"]}[CANDIDATE_ID]
    if phase2["asset_status"]["geometry"] != "PARTIAL" or phase2["activation_gate"] != "BLOCKED":
        raise ValueError("Phase-2 Mala catalog did not retain PARTIAL/BLOCKED")
    mapped = {r["candidate_id"]: r for r in load(MAP_CATALOG)["research_zones"]}[CANDIDATE_ID]
    if not mapped["geometry"]["map_eligible"] or mapped["geometry"]["path"] != GEOMETRY.relative_to(ROOT).as_posix():
        raise ValueError("Mala research geometry is not published in map catalog")
    if mapped["deployment_status"] != "RESEARCH_ONLY" or mapped["production_use"] is not False or mapped["alerting_enabled"] is not False:
        raise ValueError("unsafe Mala map layer")
    if mapped["validation"]["activation_gate"] != "BLOCKED":
        raise ValueError("Mala map layer activation gate changed")


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--materialize", action="store_true")
    mode.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    if args.materialize:
        materialize()
    else:
        check()
    print(json.dumps({"status":"PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY","candidate_id":CANDIDATE_ID,"official_unit_code":EXPECTED_CODE,"counts_as_complete_candidate_geometry":False,"activation_gate":"BLOCKED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
