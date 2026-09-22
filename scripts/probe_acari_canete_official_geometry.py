#!/usr/bin/env python3
"""Freeze official ANA basin-context geometry for Phase-2 Acarí and Cañete.

RESEARCH_ONLY / TEST_ONLY. The emitted polygons are official ANA hydrologic-unit
boundaries used as basin context only. They do not resolve quebrada San Agustín,
individual Cañete tributary ravines, event footprints, hydraulic capacity,
negative controls, thresholds or operational activation.
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
BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
SOURCE_DIR = ROOT / "site/data/phase2/sources/acari_canete_hydrologic_context"
SOURCE_INVENTORY = SOURCE_DIR / "source_inventory.json"
INVENTORIES = [ROOT / "config/phase2_candidate_inventory_v0_1.json", ROOT / "config/phase2_candidate_inventory_v0_2.json"]
CONTRACT_DIR = ROOT / "site/data/validation/phase2_zone_contracts"
GEOM_DIR = ROOT / "site/data/phase2/geometries"

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

UNITS = {
    "arequipa_acari_san_agustin": {
        "query_name": "Cuenca Acarí",
        "slug": "acari",
        "source_id": "ANA-IDEP-UH-ACARI-20260922",
        "geometry_file": "arequipa_acari_san_agustin_acari_basin_context.geojson",
        "validation_file": "arequipa_acari_san_agustin_geometry_validation.json",
        "coverage": "Official ANA Cuenca Acarí hydrologic unit only; quebrada San Agustín remains an unresolved separate component and is not independently polygonized.",
        "unresolved_component": "quebrada San Agustín",
    },
    "lima_sur_canete": {
        "query_name": "Cuenca Cañete",
        "slug": "canete",
        "source_id": "ANA-IDEP-UH-CANETE-20260922",
        "geometry_file": "lima_sur_canete_canete_basin_context.geojson",
        "validation_file": "lima_sur_canete_geometry_validation.json",
        "coverage": "Official ANA Cuenca Cañete hydrologic unit only; named tributary ravines and regulatory fajas remain separate components and are not converted into event footprints.",
        "unresolved_component": "named tributary ravines",
    },
}


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def query_url(name: str) -> str:
    return BASE + "?" + urlencode({
        "where": f"NOMBRE='{name}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    })


def fetch_unit(name: str) -> tuple[dict, str]:
    url = query_url(name)
    req = Request(url, headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(req, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    return data, sha_bytes(raw)


def validate_official_feature(data: dict, expected_name: str) -> dict:
    if data.get("type") != "FeatureCollection" or len(data.get("features") or []) != 1:
        raise ValueError(f"{expected_name}: expected exactly one ANA feature")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    if props.get("NOMBRE") != expected_name:
        raise ValueError(f"{expected_name}: unexpected ANA identity {props.get('NOMBRE')!r}")
    if not str(props.get("CODIGO") or "").strip():
        raise ValueError(f"{expected_name}: missing official hydrologic-unit code")
    if float(props.get("AREA_KM2") or 0) <= 0:
        raise ValueError(f"{expected_name}: invalid official area")
    if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{expected_name}: official geometry is not polygonal")
    return feature


def geometry_document(candidate_id: str, cfg: dict, source_sha: str, feature: dict) -> dict:
    props = feature["properties"]
    return {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "candidate_id": candidate_id,
            "geometry_status": "PARTIAL_OFFICIAL_HYDROLOGIC_UNIT_CONTEXT",
            "source_id": cfg["source_id"],
            "source_snapshot_sha256": source_sha,
            "coverage": cfg["coverage"],
            "map_disclaimer": "Official basin context RESEARCH_ONLY; not an event footprint, hazard extent, hydraulic-capacity model, risk level or alert layer.",
        },
        "features": [{
            "type": "Feature",
            "id": f"{candidate_id}_{cfg['slug']}_basin_context",
            "properties": {
                "candidate_id": candidate_id,
                "unit_id": f"{candidate_id}_{cfg['slug']}_basin_context",
                "name": f"{cfg['query_name']} · contexto hidrológico ANA",
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
                "source_id": cfg["source_id"],
                "source_crs": "EPSG:4326 requested from ANA IDEP ArcGIS service",
                "geometry_method": "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM",
                "district_boundary_used": False,
                "dem_used": False,
                "outlet_used": False,
                "outlet": None,
                "unresolved_component": cfg["unresolved_component"],
                "counts_as_complete_candidate_geometry": False,
                "confidence": "HIGH_OFFICIAL_BASIN_GEOMETRY",
                "warning": "Basin context only; do not infer event occurrence, tributary routing, hydraulic capacity, thresholds, risk or alert state.",
            },
            "geometry": feature["geometry"],
        }],
    }


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def update_inventory_document(doc: dict, source_records: dict[str, dict]) -> dict:
    updated = json.loads(json.dumps(doc))
    by_id = {row.get("candidate_id"): row for row in updated.get("candidates") or []}
    catalog = updated.setdefault("official_source_catalog", {})
    for candidate_id, cfg in UNITS.items():
        row = by_id.get(candidate_id)
        if not row:
            raise ValueError(f"missing Phase-2 inventory candidate {candidate_id}")
        sources = list(row.get("official_sources") or [])
        if cfg["source_id"] not in sources:
            sources.append(cfg["source_id"])
        row["official_sources"] = sources
        catalog[cfg["source_id"]] = source_records[candidate_id]["url"]
    return updated


def update_contract_document(candidate_id: str, contract: dict, geometry_rel: str, source_id: str) -> dict:
    updated = json.loads(json.dumps(contract))
    if updated.get("candidate_id") != candidate_id:
        raise ValueError(f"contract identity mismatch for {candidate_id}")
    if updated.get("deployment_status") != "RESEARCH_ONLY" or updated.get("production_use") is not False:
        raise ValueError(f"unsafe contract state for {candidate_id}")
    if updated.get("decision_thresholds") is not None or updated.get("hydraulic_factors") is not None:
        raise ValueError(f"decision fields unexpectedly populated for {candidate_id}")
    if updated.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK":
        raise ValueError(f"missing-data guard changed for {candidate_id}")
    if (updated.get("validation") or {}).get("activation_gate") != "BLOCKED":
        raise ValueError(f"activation gate changed for {candidate_id}")
    source_ids = list(updated.get("official_source_ids") or [])
    if source_id not in source_ids:
        source_ids.append(source_id)
    updated["official_source_ids"] = source_ids
    geom = updated.setdefault("assets", {}).setdefault("geometry", {})
    existing_source_ids = list(geom.get("source_ids") or [])
    if source_id not in existing_source_ids:
        existing_source_ids.append(source_id)
    geom.update({"status": "PARTIAL", "path": geometry_rel, "source_ids": existing_source_ids})
    note = (
        "Official ANA basin geometry is now normalized as a PARTIAL research-context asset. "
        "It does not resolve all named local components, event footprints, hydraulic capacity, negative controls, thresholds or operational activation."
    )
    notes = list(updated.get("notes") or [])
    if note not in notes:
        notes.append(note)
    updated["notes"] = notes
    return updated


def build_validation(candidate_id: str, cfg: dict, source_record: dict, geom_rel: str, geom_sha: str, feature: dict) -> dict:
    props = feature["properties"]
    return {
        "version": "phase2-acari-canete-geometry-validation-v1",
        **GUARDS,
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidate_id": candidate_id,
        "source_snapshot_path": source_record["local_path"],
        "source_snapshot_sha256": source_record["canonical_sha256"],
        "normalized_geometry_path": geom_rel,
        "normalized_geometry_sha256": geom_sha,
        "official_unit": {
            "code": str(props["CODIGO"]),
            "name": props["NOMBRE"],
            "area_km2": float(props["AREA_KM2"]),
        },
        "component_resolution": {
            "official_basin_polygon": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "unresolved_component": cfg["unresolved_component"],
            "unresolved_component_geometry": "NOT_ASSERTED",
            "event_footprint": "NOT_ASSERTED",
            "hydraulic_capacity": "UNKNOWN",
        },
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
        "district_boundary_used": False,
        "dem_used": False,
        "activation_gate": "BLOCKED",
    }


def build_all(source_records: dict[str, dict]) -> tuple[dict[Path, object], dict[Path, object]]:
    generated: dict[Path, object] = {}
    contracts: dict[Path, object] = {}
    for candidate_id, cfg in UNITS.items():
        source_path = ROOT / source_records[candidate_id]["local_path"]
        source = load_json(source_path)
        if sha_bytes(canonical(source)) != source_records[candidate_id]["canonical_sha256"]:
            raise ValueError(f"{candidate_id}: frozen source canonical SHA-256 mismatch")
        feature = validate_official_feature(source, cfg["query_name"])
        geom_doc = geometry_document(candidate_id, cfg, source_records[candidate_id]["canonical_sha256"], feature)
        geom_path = GEOM_DIR / cfg["geometry_file"]
        geom_rel = geom_path.relative_to(ROOT).as_posix()
        geom_sha = sha_bytes(canonical(geom_doc))
        validation_path = GEOM_DIR / cfg["validation_file"]
        generated[geom_path] = geom_doc
        generated[validation_path] = build_validation(candidate_id, cfg, source_records[candidate_id], geom_rel, geom_sha, feature)
        contract_path = CONTRACT_DIR / f"{candidate_id}.json"
        contracts[contract_path] = update_contract_document(candidate_id, load_json(contract_path), geom_rel, cfg["source_id"])
    return generated, contracts


def source_records_from_inventory() -> dict[str, dict]:
    inv = load_json(SOURCE_INVENTORY)
    if inv.get("deployment_status") != "RESEARCH_ONLY" or inv.get("activation_gate") != "BLOCKED":
        raise ValueError("unsafe source inventory")
    records = {row["candidate_id"]: row for row in inv.get("sources") or []}
    if set(records) != set(UNITS):
        raise ValueError("source inventory candidate set mismatch")
    return records


def refresh_sources() -> dict[str, dict]:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    records = {}
    acquired_at = datetime.now(timezone.utc).isoformat()
    for candidate_id, cfg in UNITS.items():
        data, raw_sha = fetch_unit(cfg["query_name"])
        feature = validate_official_feature(data, cfg["query_name"])
        source_path = SOURCE_DIR / f"ana_{cfg['slug']}_basin.geojson"
        write_json(source_path, data)
        props = feature["properties"]
        records[candidate_id] = {
            "candidate_id": candidate_id,
            "source_id": cfg["source_id"],
            "institution": "Autoridad Nacional del Agua / IDEP",
            "url": query_url(cfg["query_name"]),
            "role": "official_hydrologic_unit_geometry_research_context",
            "local_path": source_path.relative_to(ROOT).as_posix(),
            "canonical_sha256": sha_bytes(canonical(data)),
            "raw_response_sha256_at_freeze": raw_sha,
            "official_unit_code": str(props["CODIGO"]),
            "official_unit_name": props["NOMBRE"],
            "official_area_km2": float(props["AREA_KM2"]),
            "acquired_at_utc": acquired_at,
        }
    inventory = {
        "version": "phase2-acari-canete-source-inventory-v1",
        **GUARDS,
        "sources": [records[cid] for cid in UNITS],
        "forbidden": [
            "treat basin polygons as event footprints",
            "invent quebrada San Agustin geometry",
            "invent Canete tributary ravine geometry",
            "infer hydraulic capacity or operational thresholds",
            "infer negative controls from documentary silence",
        ],
    }
    write_json(SOURCE_INVENTORY, inventory)
    return records


def sync_documents(source_records: dict[str, dict], check_only: bool) -> None:
    generated, contracts = build_all(source_records)
    inventory_expected = {}
    for path in INVENTORIES:
        inventory_expected[path] = update_inventory_document(load_json(path), source_records)

    expected = {**generated, **contracts, **inventory_expected}
    if check_only:
        for path, value in expected.items():
            if not path.is_file() or path.read_bytes() != canonical(value):
                raise ValueError(f"stale or missing deterministic artifact: {path.relative_to(ROOT)}")
    else:
        for path, value in expected.items():
            write_json(path, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source and args.check_only:
        raise ValueError("--refresh-source and --check-only are mutually exclusive")
    if args.refresh_source:
        source_records = refresh_sources()
        sync_documents(source_records, check_only=False)
    else:
        if not SOURCE_INVENTORY.is_file():
            raise ValueError("frozen ANA source inventory missing; use --refresh-source once")
        source_records = source_records_from_inventory()
        sync_documents(source_records, check_only=args.check_only)
        if not args.check_only:
            sync_documents(source_records, check_only=False)
    print(json.dumps({
        "status": "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY",
        "candidates": sorted(UNITS),
        "counts_as_complete_candidate_geometry": False,
        "activation_gate": "BLOCKED",
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
