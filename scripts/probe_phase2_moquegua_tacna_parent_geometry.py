#!/usr/bin/env python3
"""Freeze exact official ANA parent-basin geometries for Moquegua/Tacna discovery.

Geometry/identity only. This probe intentionally does not read event outcomes,
rainfall, hydraulic capacity, thresholds, negative controls or operational state.
The normalized polygons remain RESEARCH_ONLY context and are not inserted into
the public map catalog by this script.
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
CFG = ROOT / "config/phase2_south_coast_moquegua_tacna_discovery_v0_1.json"
SOURCE_DIR = ROOT / "site/data/phase2/sources/south_moquegua_tacna_parent_geometry"
GEOM_DIR = ROOT / "site/data/phase2/geometries"

ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"

TARGETS = {
    "tacna_de_la_concordia": ("13152", "Cuenca De la Concordia"),
    "tacna_hospicio": ("13154", "Cuenca Hospicio"),
    "tacna_caplina": ("13156", "Cuenca Caplina"),
    "tacna_sama": ("13158", "Cuenca Sama"),
    "tacna_locumba": ("1316", "Cuenca Locumba"),
    "moquegua_ilo_moquegua": ("13172", "Cuenca Ilo - Moquegua"),
    "moquegua_honda": ("13178", "Cuenca Honda"),
    "moquegua_tambo": ("1318", "Cuenca Tambo"),
}

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


class ProbeError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return digest(raw)


def source_path(target: str, code: str) -> Path:
    return SOURCE_DIR / f"ana_{target}_{code}.geojson"


def geometry_path(target: str) -> Path:
    return GEOM_DIR / f"{target}_basin_context.geojson"


def validation_path(target: str) -> Path:
    return GEOM_DIR / f"{target}_geometry_validation.json"


def validate_config(cfg: dict) -> None:
    for key, expected in SAFE.items():
        if cfg.get(key) != expected:
            raise ProbeError(f"UNSAFE_CONFIG_{key}")
    rows = {row["discovery_id"]: row for row in cfg.get("official_basin_hierarchy", [])}
    if set(rows) != set(TARGETS):
        raise ProbeError("PARENT_BASIN_TARGET_SET_MISMATCH")
    for target, (code, name) in TARGETS.items():
        row = rows[target]
        if str(row.get("official_unit_code")) != code or row.get("name") != name:
            raise ProbeError(f"OFFICIAL_IDENTITY_MISMATCH_{target}")
        if row.get("entity_role") != "OFFICIAL_PARENT_BASIN_CONTEXT_NON_ACTIVATABLE":
            raise ProbeError(f"UNSAFE_PARENT_ROLE_{target}")
        if row.get("identity_status") != "OFFICIAL_ANA_UNIT_CONFIRMED":
            raise ProbeError(f"UNCONFIRMED_PARENT_IDENTITY_{target}")
        if row.get("map_publishable") is not False:
            raise ProbeError(f"PARENT_PREMATURELY_MAP_PUBLISHABLE_{target}")
        if row.get("activation_gate") != "BLOCKED":
            raise ProbeError(f"PARENT_ACTIVATION_GATE_NOT_BLOCKED_{target}")
        if row.get("decision_thresholds") is not None or row.get("hydraulic_factors") is not None:
            raise ProbeError(f"PARENT_THRESHOLDS_OR_HYDRAULICS_PRESENT_{target}")


def fetch(code: str) -> tuple[dict, str]:
    params = {
        "where": f"CODIGO='{code}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    url = ENDPOINT + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    with urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload, url


def validate_source(source: dict, code: str, expected_name: str) -> dict:
    if source.get("type") != "FeatureCollection":
        raise ProbeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
    features = source.get("features") or []
    if len(features) != 1:
        raise ProbeError(f"ANA_EXACT_CODE_NOT_UNIQUE count={len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    got_code = str(props.get("CODIGO") or props.get("codigo") or "")
    got_name = props.get("NOMBRE") or props.get("nombre")
    if got_code != code:
        raise ProbeError(f"ANA_CODE_MISMATCH expected={code} got={got_code}")
    if got_name != expected_name:
        raise ProbeError(f"ANA_NAME_MISMATCH expected={expected_name!r} got={got_name!r}")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
        raise ProbeError("ANA_GEOMETRY_MISSING_OR_NOT_POLYGON")
    return feature


def normalized(feature: dict, target: str, code: str, name: str) -> dict:
    source_id = f"ANA-IDEP-UH-{code}-20260926"
    area = (feature.get("properties") or {}).get("AREA_KM2")
    props = {
        "unit_id": target,
        "name": name,
        "official_unit_code": code,
        "official_area_km2": area,
        "source_id": source_id,
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        "map_publishable": False,
        "map_publication_status": "PENDING_INTEGRATOR_CATALOG_QA",
        **SAFE,
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "context_only": True,
            "source_id": source_id,
            "map_publishable": False,
            "map_publication_status": "PENDING_INTEGRATOR_CATALOG_QA",
        },
        "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
    }


def bootstrap_target(target: str) -> dict:
    code, name = TARGETS[target]
    source, request_url = fetch(code)
    feature = validate_source(source, code, name)
    sp = source_path(target, code)
    gp = geometry_path(target)
    vp = validation_path(target)
    source_sha = dump(sp, source)
    geom = normalized(feature, target, code, name)
    geometry_sha = dump(gp, geom)
    validation = {
        "schema_version": "0.1",
        "target": target,
        "status": "PASS_OFFICIAL_ANA_PARENT_BASIN_GEOMETRY",
        **SAFE,
        "official_unit_code": code,
        "official_unit_name": name,
        "source_id": f"ANA-IDEP-UH-{code}-20260926",
        "source_path": sp.relative_to(ROOT).as_posix(),
        "source_sha256": source_sha,
        "geometry_path": gp.relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "request_url": request_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_context_only": True,
        "map_catalog_updated": False,
        "map_publishable": False,
        "outcomes_read": False,
        "rainfall_read": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_used": False,
        "synthetic_union_used": False,
    }
    dump(vp, validation)
    return validation


def replay_target(target: str) -> dict:
    code, name = TARGETS[target]
    sp = source_path(target, code)
    gp = geometry_path(target)
    vp = validation_path(target)
    if not sp.is_file() or not gp.is_file() or not vp.is_file():
        raise ProbeError(f"FROZEN_ASSET_MISSING_{target}")
    source = load(sp)
    feature = validate_source(source, code, name)
    expected_geom = normalized(feature, target, code, name)
    stored_geom = load(gp)
    if canonical_bytes(stored_geom) != canonical_bytes(expected_geom):
        raise ProbeError(f"NORMALIZED_GEOMETRY_REPLAY_MISMATCH_{target}")
    validation = load(vp)
    for key, expected in SAFE.items():
        if validation.get(key) != expected:
            raise ProbeError(f"UNSAFE_VALIDATION_{target}_{key}")
    checks = {
        "official_unit_code": code,
        "official_unit_name": name,
        "source_path": sp.relative_to(ROOT).as_posix(),
        "geometry_path": gp.relative_to(ROOT).as_posix(),
        "source_sha256": digest(canonical_bytes(source)),
        "geometry_sha256": digest(canonical_bytes(stored_geom)),
        "parent_context_only": True,
        "map_catalog_updated": False,
        "map_publishable": False,
        "outcomes_read": False,
        "rainfall_read": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_used": False,
        "synthetic_union_used": False,
    }
    for key, expected in checks.items():
        if validation.get(key) != expected:
            raise ProbeError(f"VALIDATION_REPLAY_MISMATCH_{target}_{key}")
    return validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), action="append")
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source and args.check_only:
        raise ProbeError("REFRESH_AND_CHECK_ONLY_ARE_MUTUALLY_EXCLUSIVE")
    cfg = load(CFG)
    validate_config(cfg)
    targets = args.target or sorted(TARGETS)
    results = []
    for target in targets:
        if args.refresh_source:
            results.append(bootstrap_target(target))
        else:
            results.append(replay_target(target))
    print(json.dumps({
        "status": "PASS",
        "mode": "bootstrap" if args.refresh_source else "replay",
        "targets": [row["target"] for row in results],
        "map_catalog_updated": False,
        "production_use": False,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
