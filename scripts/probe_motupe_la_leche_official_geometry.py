#!/usr/bin/env python3
"""Build reproducible RESEARCH_ONLY Motupe basin context for Phase 2.

The only polygon emitted is ANA hydrologic unit 137772 (Cuenca Motupe). Existing
official evidence identifies Río La Leche as watercourse 1377722 inside that
unit. No separate La Leche/Pítipo basin, outlet, event footprint, hydraulic
capacity or negative control is invented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/la_leche_pacora_pitipo_official_context_1998_2025.json"
SOURCE_DIR = ROOT / "site/data/phase2/sources/motupe_la_leche_hydrologic_context"
SOURCE = SOURCE_DIR / "ana_cuenca_motupe_137772.geojson"
SOURCE_INVENTORY = SOURCE_DIR / "source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lambayeque_motupe_la_leche_pitipo_motupe_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lambayeque_motupe_la_leche_pitipo_geometry_validation.json"
INVENTORIES = [
    ROOT / "config/phase2_candidate_inventory_v0_1.json",
    ROOT / "config/phase2_candidate_inventory_v0_2.json",
]
CANDIDATE_ID = "lambayeque_motupe_la_leche_pitipo"

BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
BASIN_URL = BASE + "?" + urlencode({
    "where": "NOMBRE='Cuenca Motupe'",
    "outFields": "*",
    "returnGeometry": "true",
    "outSR": "4326",
    "geometryPrecision": "7",
    "f": "geojson",
})
EXPECTED_SOURCE_SHA256 = "5b5b59e51cd84809e5f63336147e713a8277b61126e6d65ae1acd53481242b07"
EXPECTED_RAW_RESPONSE_SHA256 = "f4fc416ff85b3bfb6d3403298a37f3375e830c6f69df04ac2164bdaf2a99f048"
SOURCE_ID = "ANA-IDEP-UH-MOTUPE-137772-20260922"
GEOSNIRH_ID = "ANA-GEOSNIRH-MOTUPE-HYDROGRAPHIC-UNIT-137772"
GEOSNIRH_URL = "https://geosnirh.ana.gob.pe/server/rest/services/Mapas_ALA/Capas_ALA_Motupe_Olmos_LaLeche/MapServer"
OFFICIAL_SOURCE_IDS = [
    "CENEPRED-EVAR-PITIPO-SECTOR-1",
    "ANA-CENEPRED-CRITICAL-POINTS-2025",
    SOURCE_ID,
    GEOSNIRH_ID,
]
OFFICIAL_EVIDENCE_STAGE = "official_motupe_hydrologic_unit_geometry_and_la_leche_identity_context_available"
UNRESOLVED_GATES = [
    "preserve Rio Motupe and Rio La Leche as distinct named watercourses inside Cuenca Motupe until reproducible sub-basin or line geometry supports further separation",
    "resolve local ravine contributions without inventing a Pitipo hydrologic polygon",
    "normalize exposed caserios and infrastructure separately from the official basin boundary",
    "identify primary hydrological observations and event-paired controls",
]

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


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def normalized_text(value: object) -> str:
    return (str(value or "").strip().lower().replace("í", "i").replace("ó", "o")
            .replace("á", "a").replace("é", "e").replace("ú", "u"))


def fetch_source() -> dict:
    request = Request(BASIN_URL, headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    payload = canonical(data)
    sha = digest_bytes(payload)
    if sha != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"ANA source changed: {sha}; refusing to overwrite frozen snapshot")
    return data


def validate_source(data: dict) -> dict:
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) != 1:
        raise ValueError("expected exactly one official Cuenca Motupe feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if str(props.get("CODIGO")) != "137772" or normalized_text(props.get("NOMBRE")) != "cuenca motupe":
        raise ValueError(f"unexpected ANA unit identity: {props}")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("official Cuenca Motupe geometry is not polygonal")
    if abs(float(props.get("AREA_KM2")) - 3653.4699) > 1e-4:
        raise ValueError("official Cuenca Motupe area changed unexpectedly")
    return feature


def expected_inventory(value: dict) -> dict:
    updated = json.loads(json.dumps(value))
    rows = [row for row in updated.get("candidates") or [] if row.get("candidate_id") == CANDIDATE_ID]
    if len(rows) != 1:
        raise ValueError(f"expected one {CANDIDATE_ID} inventory row")
    row = rows[0]
    row["official_evidence_stage"] = OFFICIAL_EVIDENCE_STAGE
    row["official_sources"] = list(OFFICIAL_SOURCE_IDS)
    row["unresolved_gates"] = list(UNRESOLVED_GATES)
    catalog = updated.setdefault("official_source_catalog", {})
    catalog[SOURCE_ID] = BASIN_URL
    catalog[GEOSNIRH_ID] = GEOSNIRH_URL
    return updated


def sync_inventories(check_only: bool) -> None:
    for path in INVENTORIES:
        if not path.is_file():
            raise ValueError(f"missing inventory: {path.relative_to(ROOT)}")
        current = json.loads(path.read_text(encoding="utf-8"))
        expected = expected_inventory(current)
        if check_only:
            if current != expected:
                raise ValueError(f"stale Motupe inventory row: {path.relative_to(ROOT)}")
        else:
            path.write_bytes(canonical(expected))


def build_documents(source: dict) -> tuple[dict, dict, dict]:
    feature = validate_source(source)
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    identity = evidence["official_hydrologic_identity"]
    if identity["ana_hydrologic_unit_code"] != "137772" or identity["ana_hydrologic_unit_name"] != "Cuenca Motupe":
        raise ValueError("committed official basin identity changed unexpectedly")
    if identity["la_leche_watercourse_code"] != "1377722" or normalized_text(identity["la_leche_watercourse_name"]) != "rio la leche":
        raise ValueError("committed Rio La Leche identity changed unexpectedly")

    props = feature["properties"]
    normalized = {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "candidate_id": CANDIDATE_ID,
            "geometry_status": "PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT",
            "source_id": SOURCE_ID,
            "source_snapshot_sha256": EXPECTED_SOURCE_SHA256,
            "coverage": "Official ANA Cuenca Motupe unit 137772 only; Río La Leche, Río Motupe and local ravines remain separate named components and are not independently polygonized here.",
            "map_disclaimer": "Cuenca oficial de contexto RESEARCH_ONLY; no es huella de evento, mapa de peligro, capacidad hidráulica ni alerta.",
        },
        "features": [{
            "type": "Feature",
            "id": "lambayeque_motupe_basin_context_137772",
            "properties": {
                "candidate_id": CANDIDATE_ID,
                "unit_id": "lambayeque_motupe_basin_context_137772",
                "name": "Cuenca Motupe · contexto hidrológico ANA",
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
                "la_leche_watercourse_code": identity["la_leche_watercourse_code"],
                "la_leche_watercourse_name": identity["la_leche_watercourse_name"],
                "separate_la_leche_basin_polygon_asserted": False,
                "pitipo_hydrologic_polygon_asserted": False,
                "watercourse_line_geometry_materialized": False,
                "confidence": "HIGH_OFFICIAL_GEOMETRY_MEDIUM_UNDATED_SERVICE_CURRENTNESS",
                "warning": "Basin context only. Do not infer inundation, activation, hydraulic capacity or local ravine routing.",
            },
            "geometry": feature["geometry"],
        }],
    }
    inventory = {
        "version": "phase2-motupe-la-leche-source-inventory-v1",
        **GUARDS,
        "sources": [{
            "source_id": SOURCE_ID,
            "institution": "Autoridad Nacional del Agua / IDEP",
            "url": BASIN_URL,
            "role": "official_hydrologic_unit_geometry",
            "evidence_tier": "PRIMARY_OFFICIAL",
            "local_path": SOURCE.relative_to(ROOT).as_posix(),
            "canonical_sha256": EXPECTED_SOURCE_SHA256,
            "raw_response_sha256_at_freeze": EXPECTED_RAW_RESPONSE_SHA256,
            "official_unit_code": "137772",
            "official_unit_name": "Cuenca Motupe",
        }, {
            "source_id": "LA-LECHE-OFFICIAL-OUTCOME-HYDROLOGIC-CONTEXT-1998-2025",
            "institution": "multi-source official evidence package",
            "role": "official watercourse identity and bounded outcome context; not geometry source",
            "local_path": EVIDENCE.relative_to(ROOT).as_posix(),
            "sha256": digest(EVIDENCE),
        }],
        "forbidden": [
            "treat basin polygon as event footprint",
            "invent separate La Leche or Pitipo basin geometry",
            "derive hydraulic capacity or thresholds",
            "infer negative controls from absence of reports",
        ],
    }
    validation = {
        "version": "phase2-motupe-la-leche-geometry-validation-v1",
        **GUARDS,
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidate_id": CANDIDATE_ID,
        "source_snapshot_path": SOURCE.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": EXPECTED_SOURCE_SHA256,
        "normalized_geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
        "normalized_geometry_sha256": digest_bytes(canonical(normalized)),
        "source_inventory_path": SOURCE_INVENTORY.relative_to(ROOT).as_posix(),
        "identity_evidence_path": EVIDENCE.relative_to(ROOT).as_posix(),
        "official_unit": {"code": "137772", "name": "Cuenca Motupe", "area_km2": float(props["AREA_KM2"])},
        "component_resolution": {
            "cuenca_motupe_polygon": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "rio_la_leche_identity": "REPRODUCIBLE_OFFICIAL_IDENTITY_WITHOUT_LINE_GEOMETRY",
            "rio_motupe_line_geometry": "NOT_MATERIALIZED",
            "pitipo": "TERRITORIAL_REFERENCE_NOT_HYDROLOGIC_POLYGON",
            "local_ravines": "UNRESOLVED_NO_GEOMETRY_DRAWN",
        },
        "separation_rule": "Do not create separate basin polygons for Río La Leche, Pítipo or local ravines unless an independent reproducible hydrologic boundary is obtained.",
        "counts_as_complete_candidate_geometry": False,
        "activation_gate": "BLOCKED",
    }
    return normalized, inventory, validation


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source and args.check_only:
        raise ValueError("--refresh-source and --check-only are mutually exclusive")

    if args.refresh_source:
        source = fetch_source()
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        SOURCE.write_bytes(canonical(source))
    elif SOURCE.is_file():
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
    else:
        raise ValueError("frozen ANA source snapshot missing; run once with --refresh-source")

    if digest_bytes(canonical(source)) != EXPECTED_SOURCE_SHA256:
        raise ValueError("frozen ANA source snapshot SHA-256 mismatch")
    normalized, inventory, validation = build_documents(source)

    if args.check_only:
        sync_inventories(check_only=True)
        expected = {GEOMETRY: normalized, SOURCE_INVENTORY: inventory, VALIDATION: validation}
        for path, value in expected.items():
            if not path.is_file() or path.read_bytes() != canonical(value):
                raise ValueError(f"stale or missing generated artifact: {path.relative_to(ROOT)}")
    else:
        sync_inventories(check_only=False)
        write(GEOMETRY, normalized)
        write(SOURCE_INVENTORY, inventory)
        write(VALIDATION, validation)

    print(json.dumps({
        "status": validation["status"],
        "source_snapshot_sha256": EXPECTED_SOURCE_SHA256,
        "normalized_geometry_sha256": validation["normalized_geometry_sha256"],
        "counts_as_complete_candidate_geometry": False,
        "activation_gate": "BLOCKED",
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
