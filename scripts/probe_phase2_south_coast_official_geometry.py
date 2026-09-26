#!/usr/bin/env python3
"""Freeze exact official ANA basin geometries for Moquegua/Tacna discovery units.

Geometry/identity only. This script never reads event outcomes, rainfall, hydraulic
capacity, thresholds, negative controls, or operational state. Exact ANA code/name
mismatches fail closed. Parent basin polygons remain context-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config/phase2_south_coast_moquegua_tacna_discovery_v0_1.json"
CONTRACT_DIR = ROOT / "site/data/validation/phase2_discovery_contracts"
SOURCE_ROOT = ROOT / "site/data/phase2/sources/south_coast_discovery_geometry"
GEOM_DIR = ROOT / "site/data/phase2/geometries"
ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"

SAFE = {
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

TARGETS = {
    "moquegua_ilo_moquegua_osmore": {
        "code": "13172",
        "name": "Cuenca Ilo - Moquegua",
        "source_id": "ANA-UH-13172-ILO-MOQUEGUA",
        "source": SOURCE_ROOT / "ana_moquegua_ilo_moquegua_13172.geojson",
        "geometry": GEOM_DIR / "moquegua_ilo_moquegua_basin_context.geojson",
    },
    "moquegua_tambo": {
        "code": "1318",
        "name": "Cuenca Tambo",
        "source_id": "ANA-UH-1318-TAMBO",
        "source": SOURCE_ROOT / "ana_moquegua_tambo_1318.geojson",
        "geometry": GEOM_DIR / "moquegua_tambo_basin_context.geojson",
    },
    "tacna_locumba_ilabaya_mirave": {
        "code": "1316",
        "name": "Cuenca Locumba",
        "source_id": "ANA-UH-1316-LOCUMBA",
        "source": SOURCE_ROOT / "ana_tacna_locumba_1316.geojson",
        "geometry": GEOM_DIR / "tacna_locumba_basin_context.geojson",
    },
    "tacna_sama": {
        "code": "13158",
        "name": "Cuenca Sama",
        "source_id": "ANA-UH-13158-SAMA",
        "source": SOURCE_ROOT / "ana_tacna_sama_13158.geojson",
        "geometry": GEOM_DIR / "tacna_sama_basin_context.geojson",
    },
    "tacna_caplina": {
        "code": "13156",
        "name": "Cuenca Caplina",
        "source_id": "ANA-UH-13156-CAPLINA",
        "source": SOURCE_ROOT / "ana_tacna_caplina_13156.geojson",
        "geometry": GEOM_DIR / "tacna_caplina_basin_context.geojson",
    },
}


class SouthCoastGeometryError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def validate_safe(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise SouthCoastGeometryError(f"UNSAFE_{label}_{key}")


def validate_inventory() -> dict[str, dict]:
    inventory = load(INVENTORY)
    validate_safe(inventory, "INVENTORY")
    if inventory.get("status") != "RESEARCH_ONLY_DISCOVERY_EXTENSION":
        raise SouthCoastGeometryError("INVENTORY_STATUS_DRIFT")
    relation = inventory.get("relationship_to_phase2") or {}
    if relation.get("changes_registered_candidate_count") is not False:
        raise SouthCoastGeometryError("REGISTERED_CANDIDATE_COUNT_CHANGE_FORBIDDEN")
    if relation.get("changes_operational_scope") is not False:
        raise SouthCoastGeometryError("OPERATIONAL_SCOPE_CHANGE_FORBIDDEN")
    if relation.get("map_publication_before_reproducible_geometry") is not False:
        raise SouthCoastGeometryError("MAP_PLACEHOLDER_GEOMETRY_ALLOWED")
    rows = inventory.get("discovery_units") or []
    by_id = {row.get("discovery_id"): row for row in rows}
    if set(by_id) != set(TARGETS) or len(rows) != len(TARGETS):
        raise SouthCoastGeometryError("SOUTH_COAST_TARGET_SET_DRIFT")
    for discovery_id, cfg in TARGETS.items():
        row = by_id[discovery_id]
        if str(row.get("ana_unit_code")) != cfg["code"] or row.get("ana_unit_name") != cfg["name"]:
            raise SouthCoastGeometryError(f"INVENTORY_IDENTITY_DRIFT_{discovery_id}")
    return by_id


def validate_contract(discovery_id: str, cfg: dict) -> dict:
    path = CONTRACT_DIR / f"{discovery_id}.json"
    if not path.is_file():
        raise SouthCoastGeometryError(f"MISSING_CONTRACT_{discovery_id}")
    contract = load(path)
    validate_safe(contract, f"CONTRACT_{discovery_id}")
    if contract.get("discovery_id") != discovery_id:
        raise SouthCoastGeometryError(f"CONTRACT_ID_DRIFT_{discovery_id}")
    identity = contract.get("hydrologic_identity") or {}
    if str(identity.get("ana_unit_code")) != cfg["code"] or identity.get("ana_unit_name") != cfg["name"]:
        raise SouthCoastGeometryError(f"CONTRACT_IDENTITY_DRIFT_{discovery_id}")
    if identity.get("territorial_reference_is_basin") is not False:
        raise SouthCoastGeometryError(f"TERRITORIAL_REFERENCE_AS_BASIN_{discovery_id}")
    query = contract.get("source_query") or {}
    if query.get("endpoint") != ENDPOINT or query.get("where") != f"CODIGO='{cfg['code']}'":
        raise SouthCoastGeometryError(f"UNSAFE_SOURCE_QUERY_{discovery_id}")
    asset = ((contract.get("assets") or {}).get("geometry") or {})
    if asset.get("path") != rel(cfg["geometry"]):
        raise SouthCoastGeometryError(f"GEOMETRY_PATH_DRIFT_{discovery_id}")
    if asset.get("counts_as_event_footprint") is not False:
        raise SouthCoastGeometryError(f"EVENT_FOOTPRINT_PROMOTION_{discovery_id}")
    if asset.get("counts_as_operational_geometry") is not False:
        raise SouthCoastGeometryError(f"OPERATIONAL_GEOMETRY_PROMOTION_{discovery_id}")
    map_policy = contract.get("map_policy") or {}
    if map_policy.get("approximate_geometry_forbidden") is not True:
        raise SouthCoastGeometryError(f"APPROXIMATE_GEOMETRY_ALLOWED_{discovery_id}")
    if map_policy.get("event_footprint_from_basin_geometry_forbidden") is not True:
        raise SouthCoastGeometryError(f"BASIN_AS_EVENT_FOOTPRINT_ALLOWED_{discovery_id}")
    for key in (
        "cross_basin_observation_transfer_forbidden",
        "threshold_transfer_forbidden",
        "negative_control_transfer_forbidden",
        "receiver_overflow_inference_from_local_activation_forbidden",
    ):
        if (contract.get("transfer_guards") or {}).get(key) is not True:
            raise SouthCoastGeometryError(f"TRANSFER_GUARD_DRIFT_{discovery_id}_{key}")
    return contract


def fetch_source(contract: dict) -> tuple[dict, str]:
    query = contract["source_query"]
    params = {
        "where": query["where"],
        "outFields": query.get("out_fields", "*"),
        "returnGeometry": "true",
        "outSR": str(query.get("out_sr", 4326)),
        "geometryPrecision": str(query.get("geometry_precision", 7)),
        "f": query.get("format", "geojson"),
    }
    url = query["endpoint"] + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    with urlopen(req, timeout=90) as response:
        source = json.loads(response.read().decode("utf-8"))
    return source, url


def validate_source(source: dict, code: str, name: str) -> dict:
    if source.get("type") != "FeatureCollection":
        raise SouthCoastGeometryError(f"ANA_RESPONSE_NOT_FEATURE_COLLECTION_{code}")
    features = source.get("features") or []
    if len(features) != 1:
        raise SouthCoastGeometryError(f"ANA_EXACT_CODE_NOT_UNIQUE_{code}_{len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    got_code = str(props.get("CODIGO") or props.get("codigo") or "")
    got_name = props.get("NOMBRE") or props.get("nombre")
    if got_code != code:
        raise SouthCoastGeometryError(f"ANA_CODE_MISMATCH_{code}_{got_code}")
    if got_name != name:
        raise SouthCoastGeometryError(f"ANA_NAME_MISMATCH_{code}_{got_name}")
    geom = feature.get("geometry") or {}
    if geom.get("type") not in {"Polygon", "MultiPolygon"} or not geom.get("coordinates"):
        raise SouthCoastGeometryError(f"ANA_GEOMETRY_INVALID_{code}")
    return feature


def normalized(discovery_id: str, cfg: dict, feature: dict) -> dict:
    feature_props = {
        "unit_id": discovery_id,
        "name": cfg["name"],
        "official_unit_code": cfg["code"],
        "source_id": cfg["source_id"],
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            "deployment_status": "RESEARCH_ONLY",
            "test_mode": "TEST_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "context_only": True,
            "source_id": cfg["source_id"],
        },
        "features": [
            {
                "type": "Feature",
                "properties": feature_props,
                "geometry": feature["geometry"],
            }
        ],
    }


def validation_path(cfg: dict) -> Path:
    return cfg["geometry"].with_name(cfg["geometry"].stem + "_validation.json")


def expected_validation(discovery_id: str, cfg: dict, source_sha: str, geometry_sha: str, request_url: str | None, fetched_at: str | None) -> dict:
    return {
        "schema_version": "0.1",
        "discovery_id": discovery_id,
        "status": "PASS_OFFICIAL_ANA_SOUTH_COAST_BASIN_GEOMETRY",
        **SAFE,
        "source_id": cfg["source_id"],
        "ana_unit_code": cfg["code"],
        "ana_unit_name": cfg["name"],
        "source_path": rel(cfg["source"]),
        "source_sha256": source_sha,
        "geometry_path": rel(cfg["geometry"]),
        "geometry_sha256": geometry_sha,
        "request_url": request_url,
        "fetched_at_utc": fetched_at,
        "outcomes_read_for_geometry": False,
        "rainfall_read_for_geometry": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
    }


def freeze_target(discovery_id: str, cfg: dict, contract: dict) -> dict:
    source, request_url = fetch_source(contract)
    feature = validate_source(source, cfg["code"], cfg["name"])
    source_sha = write_json(cfg["source"], source)
    geometry = normalized(discovery_id, cfg, feature)
    geometry_sha = write_json(cfg["geometry"], geometry)
    fetched_at = datetime.now(timezone.utc).isoformat()
    val = expected_validation(discovery_id, cfg, source_sha, geometry_sha, request_url, fetched_at)
    validation_sha = write_json(validation_path(cfg), val)

    asset = contract["assets"]["geometry"]
    asset.update({
        "status": "PARTIAL_OFFICIAL_BASIN_CONTEXT",
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "source_ids": [cfg["source_id"]],
        "source_path": rel(cfg["source"]),
        "source_sha256": source_sha,
        "sha256": geometry_sha,
        "validation_path": rel(validation_path(cfg)),
        "validation_sha256": validation_sha,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
    })
    contract["contract_status"] = "DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"
    write_json(CONTRACT_DIR / f"{discovery_id}.json", contract)
    return val


def check_target(discovery_id: str, cfg: dict, contract: dict) -> dict:
    if not cfg["source"].is_file():
        raise SouthCoastGeometryError(f"FROZEN_SOURCE_MISSING_{discovery_id}")
    if not cfg["geometry"].is_file():
        raise SouthCoastGeometryError(f"FROZEN_GEOMETRY_MISSING_{discovery_id}")
    vp = validation_path(cfg)
    if not vp.is_file():
        raise SouthCoastGeometryError(f"FROZEN_VALIDATION_MISSING_{discovery_id}")

    source = load(cfg["source"])
    feature = validate_source(source, cfg["code"], cfg["name"])
    source_sha = digest(cfg["source"])
    expected_geom = canonical_bytes(normalized(discovery_id, cfg, feature))
    if cfg["geometry"].read_bytes() != expected_geom:
        raise SouthCoastGeometryError(f"FROZEN_GEOMETRY_REPLAY_MISMATCH_{discovery_id}")
    geometry_sha = digest(cfg["geometry"])

    val = load(vp)
    validate_safe(val, f"VALIDATION_{discovery_id}")
    required = {
        "status": "PASS_OFFICIAL_ANA_SOUTH_COAST_BASIN_GEOMETRY",
        "source_id": cfg["source_id"],
        "ana_unit_code": cfg["code"],
        "ana_unit_name": cfg["name"],
        "source_path": rel(cfg["source"]),
        "source_sha256": source_sha,
        "geometry_path": rel(cfg["geometry"]),
        "geometry_sha256": geometry_sha,
        "outcomes_read_for_geometry": False,
        "rainfall_read_for_geometry": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
    }
    for key, expected in required.items():
        if val.get(key) != expected:
            raise SouthCoastGeometryError(f"FROZEN_VALIDATION_DRIFT_{discovery_id}_{key}")

    asset = contract["assets"]["geometry"]
    if contract.get("contract_status") != "DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY":
        raise SouthCoastGeometryError(f"CONTRACT_STATUS_NOT_FROZEN_{discovery_id}")
    required_asset = {
        "status": "PARTIAL_OFFICIAL_BASIN_CONTEXT",
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "source_ids": [cfg["source_id"]],
        "source_path": rel(cfg["source"]),
        "source_sha256": source_sha,
        "sha256": geometry_sha,
        "validation_path": rel(vp),
        "validation_sha256": digest(vp),
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
    }
    for key, expected in required_asset.items():
        if asset.get(key) != expected:
            raise SouthCoastGeometryError(f"FROZEN_CONTRACT_ASSET_DRIFT_{discovery_id}_{key}")
    return val


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", action="append", choices=sorted(TARGETS))
    parser.add_argument("--refresh-source", action="store_true")
    args = parser.parse_args()

    validate_inventory()
    targets = args.target or sorted(TARGETS)
    results = []
    for discovery_id in targets:
        cfg = TARGETS[discovery_id]
        contract = validate_contract(discovery_id, cfg)
        if args.refresh_source:
            results.append(freeze_target(discovery_id, cfg, contract))
        else:
            results.append(check_target(discovery_id, cfg, contract))
    print(json.dumps({
        "status": "PASS_SOUTH_COAST_GEOMETRY",
        "mode": "REFRESH_AND_FREEZE" if args.refresh_source else "REPLAY_CHECK_ONLY",
        "targets": [row["discovery_id"] for row in results],
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
