#!/usr/bin/env python3
"""Freeze exact ANA hydrographic-unit geometry for Pativilca and Fortaleza.

RESEARCH_ONLY / TEST_ONLY. This script only resolves official hydrologic identity and
basin-context geometry. It never creates an event footprint, hydraulic capacity,
negative control, activation gate, risk level, or operational threshold.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
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
    "lima_norte_pativilca": {
        "code": "13758",
        "name": "Cuenca Pativilca",
        "source_id": "ANA-UH-13758-PATIVILCA",
        "contract": "site/data/validation/phase2_discovery_contracts/lima_norte_pativilca.json",
        "package": "site/data/validation/phase2_discovery_packages/lima_norte_pativilca.json",
        "source": "site/data/phase2/sources/north_coast_discovery_geometry/ana_lima_norte_pativilca_13758.geojson",
        "geometry": "site/data/phase2/geometries/lima_norte_pativilca_basin_context.geojson",
        "validation": "site/data/phase2/geometries/lima_norte_pativilca_geometry_validation.json",
    },
    "lima_norte_fortaleza_paramonga": {
        "code": "137592",
        "name": "Cuenca Fortaleza",
        "source_id": "ANA-UH-137592-FORTALEZA",
        "contract": "site/data/validation/phase2_discovery_contracts/lima_norte_fortaleza_paramonga.json",
        "package": "site/data/validation/phase2_discovery_packages/lima_norte_fortaleza_paramonga.json",
        "source": "site/data/phase2/sources/north_coast_discovery_geometry/ana_lima_norte_fortaleza_137592.geojson",
        "geometry": "site/data/phase2/geometries/lima_norte_fortaleza_basin_context.geojson",
        "validation": "site/data/phase2/geometries/lima_norte_fortaleza_geometry_validation.json",
    },
}


class FreezeError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_guards(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise FreezeError(f"UNSAFE_{label}_{key}")


def query_spec(code: str) -> dict:
    return {
        "endpoint": ENDPOINT,
        "where": f"CODIGO='{code}'",
        "out_fields": "*",
        "out_sr": 4326,
        "geometry_precision": 7,
        "format": "geojson",
    }


def fetch_source(spec: dict) -> dict:
    params = {
        "where": spec["where"],
        "outFields": spec["out_fields"],
        "returnGeometry": "true",
        "outSR": str(spec["out_sr"]),
        "geometryPrecision": str(spec["geometry_precision"]),
        "f": spec["format"],
    }
    url = spec["endpoint"] + "?" + urlencode(params)
    with urlopen(Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"}), timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_source(source: dict, code: str, name: str) -> dict:
    if source.get("type") != "FeatureCollection":
        raise FreezeError("ANA_RESPONSE_NOT_FEATURE_COLLECTION")
    features = source.get("features") or []
    if len(features) != 1:
        raise FreezeError(f"ANA_EXACT_CODE_NOT_UNIQUE_{code}_{len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}
    got_code = str(props.get("CODIGO") or props.get("codigo") or "")
    got_name = props.get("NOMBRE") or props.get("nombre")
    if got_code != code:
        raise FreezeError(f"ANA_CODE_MISMATCH_{code}_{got_code}")
    if got_name != name:
        raise FreezeError(f"ANA_NAME_MISMATCH_{code}_{got_name!r}")
    geom = feature.get("geometry") or {}
    if geom.get("type") not in {"Polygon", "MultiPolygon"} or not geom.get("coordinates"):
        raise FreezeError(f"ANA_GEOMETRY_MISSING_{code}")
    return feature


def normalized(discovery_id: str, target: dict, feature: dict, source_sha: str) -> dict:
    props = {
        "unit_id": discovery_id,
        "name": target["name"],
        "official_unit_code": target["code"],
        "source_id": target["source_id"],
        "source_snapshot_sha256": source_sha,
        "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
        "context_only": True,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        **SAFE,
        "alerting_enabled": False,
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "context_only": True,
            "source_id": target["source_id"],
            "source_snapshot_sha256": source_sha,
            "counts_as_event_footprint": False,
        },
        "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
    }


def validate_contract_identity(obj: dict, discovery_id: str, target: dict, label: str) -> None:
    validate_guards(obj, label)
    if obj.get("discovery_id") != discovery_id:
        raise FreezeError(f"{label}_DISCOVERY_ID_MISMATCH")
    identity = obj.get("hydrologic_identity") or {}
    if str(identity.get("ana_unit_code") or "") != target["code"]:
        raise FreezeError(f"{label}_ANA_CODE_MISMATCH")
    if identity.get("ana_unit_name") != target["name"]:
        raise FreezeError(f"{label}_ANA_NAME_MISMATCH")
    geometry = (obj.get("assets") or {}).get("geometry") or {}
    if geometry.get("counts_as_operational_geometry") is not False:
        raise FreezeError(f"{label}_OPERATIONAL_GEOMETRY_FORBIDDEN")
    if geometry.get("counts_as_event_footprint") is not False:
        raise FreezeError(f"{label}_EVENT_FOOTPRINT_FORBIDDEN")
    if geometry.get("approximate_fallback_allowed") is not False:
        raise FreezeError(f"{label}_APPROXIMATE_GEOMETRY_FORBIDDEN")
    if geometry.get("source_query") != query_spec(target["code"]):
        raise FreezeError(f"{label}_SOURCE_QUERY_DRIFT")


def refresh_one(discovery_id: str, target: dict) -> dict:
    cp = ROOT / target["contract"]
    pp = ROOT / target["package"]
    sp = ROOT / target["source"]
    gp = ROOT / target["geometry"]
    vp = ROOT / target["validation"]
    contract = load(cp)
    package = load(pp)
    validate_contract_identity(contract, discovery_id, target, "CONTRACT")
    validate_contract_identity(package, discovery_id, target, "PACKAGE")
    source = fetch_source(query_spec(target["code"]))
    feature = validate_source(source, target["code"], target["name"])
    source_sha = dump(sp, source)
    geometry_sha = dump(gp, normalized(discovery_id, target, feature, source_sha))
    validation = {
        "schema_version": "0.1",
        "discovery_id": discovery_id,
        "status": "PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY",
        **SAFE,
        "source_id": target["source_id"],
        "ana_unit_code": target["code"],
        "ana_unit_name": target["name"],
        "source_path": target["source"],
        "source_sha256": source_sha,
        "geometry_path": target["geometry"],
        "geometry_sha256": geometry_sha,
        "outcomes_read_for_geometry": False,
        "rainfall_read_for_geometry": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
    }
    validation_sha = dump(vp, validation)
    for obj in (contract, package):
        asset = obj["assets"]["geometry"]
        asset["status"] = "PARTIAL_OFFICIAL_BASIN_CONTEXT"
        asset["representation"] = "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
        asset["sha256"] = geometry_sha
        asset["source_path"] = target["source"]
        asset["source_sha256"] = source_sha
        asset["validation_path"] = target["validation"]
        asset["validation_sha256"] = validation_sha
        obj["contract_status"] = "DISCOVERY_HYDROLOGIC_IDENTITY_AND_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY"
    dump(cp, contract)
    dump(pp, package)
    return validation


def verify_one(discovery_id: str, target: dict) -> dict:
    cp = ROOT / target["contract"]
    pp = ROOT / target["package"]
    sp = ROOT / target["source"]
    gp = ROOT / target["geometry"]
    vp = ROOT / target["validation"]
    for path in (cp, pp, sp, gp, vp):
        if not path.is_file():
            raise FreezeError(f"FROZEN_FILE_MISSING_{discovery_id}_{path.name}")
    contract = load(cp)
    package = load(pp)
    validate_contract_identity(contract, discovery_id, target, "CONTRACT")
    validate_contract_identity(package, discovery_id, target, "PACKAGE")
    source = load(sp)
    source_sha = digest(sp)
    feature = validate_source(source, target["code"], target["name"])
    expected_geometry = canonical_bytes(normalized(discovery_id, target, feature, source_sha))
    if gp.read_bytes() != expected_geometry:
        raise FreezeError(f"FROZEN_GEOMETRY_REPLAY_MISMATCH_{discovery_id}")
    geometry_sha = digest(gp)
    validation = load(vp)
    validate_guards(validation, "VALIDATION")
    expected_validation = {
        "status": "PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY",
        "source_id": target["source_id"],
        "ana_unit_code": target["code"],
        "ana_unit_name": target["name"],
        "source_path": target["source"],
        "source_sha256": source_sha,
        "geometry_path": target["geometry"],
        "geometry_sha256": geometry_sha,
        "outcomes_read_for_geometry": False,
        "rainfall_read_for_geometry": False,
        "hydraulic_capacity_read": False,
        "thresholds_used": False,
        "negative_controls_read": False,
        "approximate_geometry_used": False,
        "event_footprint_created": False,
    }
    for key, expected in expected_validation.items():
        if validation.get(key) != expected:
            raise FreezeError(f"VALIDATION_DRIFT_{discovery_id}_{key}")
    validation_sha = digest(vp)
    for label, obj in (("CONTRACT", contract), ("PACKAGE", package)):
        asset = obj["assets"]["geometry"]
        expected_asset = {
            "status": "PARTIAL_OFFICIAL_BASIN_CONTEXT",
            "representation": "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT",
            "sha256": geometry_sha,
            "source_path": target["source"],
            "source_sha256": source_sha,
            "validation_path": target["validation"],
            "validation_sha256": validation_sha,
            "counts_as_operational_geometry": False,
            "counts_as_event_footprint": False,
            "approximate_fallback_allowed": False,
        }
        for key, expected in expected_asset.items():
            if asset.get(key) != expected:
                raise FreezeError(f"{label}_ASSET_DRIFT_{discovery_id}_{key}")
    return {
        "discovery_id": discovery_id,
        "source_sha256": source_sha,
        "geometry_sha256": geometry_sha,
        "validation_sha256": validation_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--refresh-source", action="store_true")
    group.add_argument("--verify-frozen", action="store_true")
    args = parser.parse_args()
    if args.refresh_source:
        results = [refresh_one(k, v) for k, v in TARGETS.items()]
        print(json.dumps({"status": "PASS_REFRESHED_OFFICIAL_ANA_GEOMETRIES", "targets": [r["discovery_id"] for r in results]}, sort_keys=True))
    else:
        results = [verify_one(k, v) for k, v in TARGETS.items()]
        print(json.dumps({"status": "PASS_FROZEN_OFFICIAL_ANA_GEOMETRY_REPLAY", "targets": results}, sort_keys=True))


if __name__ == "__main__":
    main()
