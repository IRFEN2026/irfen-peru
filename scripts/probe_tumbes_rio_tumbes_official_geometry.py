#!/usr/bin/env python3
"""Freeze official ANA Rio Tumbes basin context and 2023 observed flood footprints.

RESEARCH_ONLY / TEST_ONLY. Basin geometry and dated observed-inundation footprints are
kept as different scientific objects. This script never derives thresholds, capacity,
negative controls, risk, activation or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_ID = "tumbes_rio_tumbes"
SERVICE = "https://geosnirh.ana.gob.pe/server/rest/services/Inundacion_Tumbes/Capas_Inundacion_Tumbes_04052023/MapServer"
SOURCE_ROOT = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_geometry"
SOURCE_INVENTORY = SOURCE_ROOT / "source_inventory.json"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/tumbes_rio_tumbes.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_rio_tumbes.json"
BASIN_GEOMETRY = ROOT / "site/data/phase2/geometries/tumbes_rio_tumbes_basin_context.geojson"
BASIN_VALIDATION = ROOT / "site/data/phase2/geometries/tumbes_rio_tumbes_geometry_validation.json"
EVENT_ROOT = ROOT / "site/data/phase2/event_footprints"

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

LAYER_SPECS = {
    "basin": {
        "layer_id": 2,
        "source_id": "ANA-TUMBES-2023-MAPSERVER-BASIN",
        "name_contains": "Cuenca Tumbes",
        "snapshot": SOURCE_ROOT / "ana_cuenca_tumbes.geojson",
        "normalized": BASIN_GEOMETRY,
        "validation": BASIN_VALIDATION,
        "role": "OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT",
        "event_date": None,
    },
    "event_20230428": {
        "layer_id": 66,
        "source_id": "ANA-TUMBES-2023-INUNDATION-20230428",
        "name_contains": "Areas Inundadas Rio Tumbes 28 Abril 2023",
        "snapshot": SOURCE_ROOT / "ana_rio_tumbes_inundation_20230428.geojson",
        "normalized": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230428.geojson",
        "validation": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230428_validation.json",
        "role": "OBSERVED_EVENT_FOOTPRINT_ONLY",
        "event_date": "2023-04-28",
    },
    "event_20230504": {
        "layer_id": 67,
        "source_id": "ANA-TUMBES-2023-INUNDATION-20230504",
        "name_contains": "Areas Inundadas Rio Tumbes 04 Mayo 2023",
        "snapshot": SOURCE_ROOT / "ana_rio_tumbes_inundation_20230504.geojson",
        "normalized": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230504.geojson",
        "validation": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230504_validation.json",
        "role": "OBSERVED_EVENT_FOOTPRINT_ONLY",
        "event_date": "2023-05-04",
    },
}


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def norm_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.lower().split())


def metadata_url(layer_id: int) -> str:
    return f"{SERVICE}/{layer_id}?f=pjson"


def query_url(layer_id: int) -> str:
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return f"{SERVICE}/{layer_id}/query?{urlencode(params)}"


def fetch_json(url: str) -> tuple[dict, bytes]:
    req = Request(url, headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(req, timeout=60) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")), raw


def validate_layer_metadata(metadata: dict, spec: dict) -> str:
    if metadata.get("id") != spec["layer_id"]:
        raise ValueError(f"unexpected ANA layer id for {spec['source_id']}: {metadata.get('id')}")
    name = str(metadata.get("name") or "")
    if norm_text(spec["name_contains"]) not in norm_text(name):
        raise ValueError(f"unexpected ANA layer name for {spec['source_id']}: {name}")
    if not metadata.get("capabilities") or "Query" not in str(metadata.get("capabilities")):
        raise ValueError(f"ANA layer is not queryable: {spec['source_id']}")
    return name


def validate_geojson(data: dict, spec: dict) -> list[dict]:
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"not a FeatureCollection: {spec['source_id']}")
    features = data.get("features") or []
    if not features:
        raise ValueError(f"empty official layer: {spec['source_id']}")
    if spec["role"] == "OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT" and len(features) != 1:
        raise ValueError(f"basin layer expected exactly one feature, got {len(features)}")
    for feature in features:
        gtype = (feature.get("geometry") or {}).get("type")
        if gtype not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"non-polygon official feature in {spec['source_id']}: {gtype}")
    return features


def normalized_feature_collection(source: dict, spec: dict, source_hash: str, layer_name: str) -> dict:
    features = validate_geojson(source, spec)
    normalized_features = []
    for index, feature in enumerate(features, start=1):
        properties = {
            "discovery_id": DISCOVERY_ID,
            "unit_id": f"{DISCOVERY_ID}_{spec['layer_id']}_{index}",
            "name": "Rio Tumbes basin context" if spec["event_date"] is None else f"Rio Tumbes observed inundation {spec['event_date']}",
            "feature_role": spec["role"],
            "source_id": spec["source_id"],
            "source_layer_id": spec["layer_id"],
            "source_layer_name": layer_name,
            "source_snapshot_sha256": source_hash,
            "event_date": spec["event_date"],
            "deployment_status": "RESEARCH_ONLY",
            "test_mode": "TEST_ONLY",
            "production_use": False,
            "production_ready": False,
            "alerting_enabled": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "decision_thresholds": None,
            "hydraulic_factors": None,
            "loaded_into_operational_calculation": False,
            "carries_alert_values": False,
            "carries_risk_classification": False,
            "counts_as_operational_geometry": False,
            "counts_as_event_footprint": spec["event_date"] is not None,
            "counts_as_basin_geometry": spec["event_date"] is None,
            "provider_values_are_irfen_thresholds": False,
            "confidence": "HIGH_OFFICIAL_ANA_REPRODUCIBLE_GEOMETRY",
            "warning": (
                "Official Rio Tumbes basin context only; not an event footprint, risk extent, hydraulic capacity or alert."
                if spec["event_date"] is None
                else "Observed dated inundation footprint only; not a basin boundary, future hazard envelope, threshold, risk class or alert."
            ),
        }
        normalized_features.append({
            "type": "Feature",
            "id": properties["unit_id"],
            "properties": properties,
            "geometry": feature["geometry"],
        })
    return {
        "type": "FeatureCollection",
        "properties": {
            **GUARDS,
            "discovery_id": DISCOVERY_ID,
            "source_id": spec["source_id"],
            "source_layer_id": spec["layer_id"],
            "source_layer_name": layer_name,
            "source_snapshot_sha256": source_hash,
            "geometry_role": spec["role"],
            "event_date": spec["event_date"],
            "map_disclaimer": (
                "RESEARCH_ONLY official basin context; not event footprint, risk, alert or hydraulic capacity."
                if spec["event_date"] is None
                else "RESEARCH_ONLY observed event footprint; not basin geometry, future hazard, threshold, risk or alert."
            ),
        },
        "features": normalized_features,
    }


def validation_record(spec: dict, source_hash: str, normalized: dict, layer_name: str, metadata_hash: str) -> dict:
    return {
        "schema_version": "0.1",
        **GUARDS,
        "status": "PASS_OFFICIAL_ANA_REPRODUCIBLE_GEOMETRY",
        "discovery_id": DISCOVERY_ID,
        "source_id": spec["source_id"],
        "source_layer_id": spec["layer_id"],
        "source_layer_name": layer_name,
        "source_snapshot_path": spec["snapshot"].relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": source_hash,
        "source_layer_metadata_sha256": metadata_hash,
        "normalized_path": spec["normalized"].relative_to(ROOT).as_posix(),
        "normalized_sha256": sha_bytes(canonical(normalized)),
        "feature_count": len(normalized["features"]),
        "geometry_role": spec["role"],
        "event_date": spec["event_date"],
        "counts_as_operational_geometry": False,
        "counts_as_event_footprint": spec["event_date"] is not None,
        "counts_as_basin_geometry": spec["event_date"] is None,
        "provider_values_are_irfen_thresholds": False,
        "artificial_connector_used": False,
    }


def assert_guards(document: dict, label: str) -> None:
    for key, expected in GUARDS.items():
        if document.get(key) != expected:
            raise ValueError(f"unsafe guard {label}: {key}={document.get(key)!r}")


def sync_contract_and_package(records: dict[str, dict], check_only: bool) -> None:
    contract = load(CONTRACT)
    package = load(PACKAGE)
    assert_guards(contract, "contract")
    assert_guards(package, "package")
    basin = records["basin"]
    geometry = contract.setdefault("assets", {}).setdefault("geometry", {})
    geometry.update({
        "status": "PARTIAL_REPRODUCIBLE_OFFICIAL_ANA_BASIN_CONTEXT",
        "path": basin["normalized_path"],
        "source_ids": [basin["source_id"]],
        "sha256": basin["normalized_sha256"],
        "validation_path": basin["validation_path"],
        "validation_sha256": basin["validation_sha256"],
        "representation": "OFFICIAL_ANA_HYDROLOGIC_BASIN_RESEARCH_CONTEXT",
        "counts_as_operational_geometry": False,
        "counts_as_event_footprint": False,
        "counts_as_complete_discovery_validation": False,
        "candidate_wide_sampling_ready": False,
    })
    contract["contract_status"] = "DISCOVERY_RESEARCH_ONLY_BASIN_CONTEXT_REPRODUCIBLE"

    pgeom = package.setdefault("assets", {}).setdefault("geometry", {})
    pgeom.update({
        "status": "PARTIAL_REPRODUCIBLE_OFFICIAL_ANA_BASIN_CONTEXT",
        "path": basin["normalized_path"],
        "source_ids": [basin["source_id"]],
        "sha256": basin["normalized_sha256"],
        "validation_path": basin["validation_path"],
        "validation_sha256": basin["validation_sha256"],
        "counts_as_operational_geometry": False,
        "counts_as_event_footprint": False,
        "approximate_points_allowed": False,
        "invented_polygons_allowed": False,
    })
    package["contract_status"] = "DISCOVERY_BASIN_CONTEXT_REPRODUCIBLE_EVENT_GEOMETRY_SEPARATE"
    reviews = [
        {
            "review_type": "OFFICIAL_ANA_BASIN_GEOMETRY_REPLAY",
            "source_id": basin["source_id"],
            "path": basin["normalized_path"],
            "sha256": basin["normalized_sha256"],
            "counts_as_event_footprint": False,
        },
        {
            "review_type": "OFFICIAL_ANA_OBSERVED_INUNDATION_REPLAY",
            "source_id": records[key]["source_id"],
            "event_date": records[key]["event_date"],
            "path": records[key]["normalized_path"],
            "sha256": records[key]["normalized_sha256"],
            "counts_as_basin_geometry": False,
        }
        for key in ("event_20230428", "event_20230504")
    ]
    package.setdefault("validation", {})["review_evidence"] = reviews

    expected = {CONTRACT: contract, PACKAGE: package}
    for path, value in expected.items():
        if check_only:
            if path.read_bytes() != canonical(value):
                raise ValueError(f"stale derived document: {path.relative_to(ROOT)}")
        else:
            write(path, value)


def records_from_inventory() -> dict[str, dict]:
    inventory = load(SOURCE_INVENTORY)
    assert_guards(inventory, "source inventory")
    rows = {row["key"]: row for row in inventory.get("layers") or []}
    if set(rows) != set(LAYER_SPECS):
        raise ValueError("unexpected source inventory layer keys")
    records = {}
    for key, spec in LAYER_SPECS.items():
        row = rows[key]
        snapshot = ROOT / row["snapshot_path"]
        if not snapshot.is_file() or sha_bytes(canonical(load(snapshot))) != row["canonical_sha256"]:
            raise ValueError(f"frozen source hash mismatch: {key}")
        source = load(snapshot)
        validate_geojson(source, spec)
        normalized = normalized_feature_collection(source, spec, row["canonical_sha256"], row["layer_name"])
        validation = validation_record(spec, row["canonical_sha256"], normalized, row["layer_name"], row["metadata_sha256"])
        records[key] = {
            "source_id": spec["source_id"],
            "event_date": spec["event_date"],
            "normalized_path": spec["normalized"].relative_to(ROOT).as_posix(),
            "normalized_sha256": sha_bytes(canonical(normalized)),
            "validation_path": spec["validation"].relative_to(ROOT).as_posix(),
            "validation_sha256": sha_bytes(canonical(validation)),
        }
    return records


def sync(check_only: bool) -> None:
    inventory = load(SOURCE_INVENTORY)
    assert_guards(inventory, "source inventory")
    rows = {row["key"]: row for row in inventory.get("layers") or []}
    records = {}
    for key, spec in LAYER_SPECS.items():
        row = rows.get(key)
        if not row:
            raise ValueError(f"missing frozen source record: {key}")
        snapshot = ROOT / row["snapshot_path"]
        source = load(snapshot)
        source_hash = sha_bytes(canonical(source))
        if source_hash != row["canonical_sha256"]:
            raise ValueError(f"frozen source hash mismatch: {key}")
        normalized = normalized_feature_collection(source, spec, source_hash, row["layer_name"])
        validation = validation_record(spec, source_hash, normalized, row["layer_name"], row["metadata_sha256"])
        expected = {spec["normalized"]: normalized, spec["validation"]: validation}
        for path, value in expected.items():
            if check_only:
                if not path.is_file() or path.read_bytes() != canonical(value):
                    raise ValueError(f"stale deterministic artifact: {path.relative_to(ROOT)}")
            else:
                write(path, value)
        records[key] = {
            "source_id": spec["source_id"],
            "event_date": spec["event_date"],
            "normalized_path": spec["normalized"].relative_to(ROOT).as_posix(),
            "normalized_sha256": sha_bytes(canonical(normalized)),
            "validation_path": spec["validation"].relative_to(ROOT).as_posix(),
            "validation_sha256": sha_bytes(canonical(validation)),
        }
    sync_contract_and_package(records, check_only)


def refresh_source() -> None:
    rows = []
    for key, spec in LAYER_SPECS.items():
        metadata, metadata_raw = fetch_json(metadata_url(spec["layer_id"]))
        layer_name = validate_layer_metadata(metadata, spec)
        source, source_raw = fetch_json(query_url(spec["layer_id"]))
        validate_geojson(source, spec)
        write(spec["snapshot"], source)
        rows.append({
            "key": key,
            "source_id": spec["source_id"],
            "layer_id": spec["layer_id"],
            "layer_name": layer_name,
            "metadata_url": metadata_url(spec["layer_id"]),
            "query_url": query_url(spec["layer_id"]),
            "snapshot_path": spec["snapshot"].relative_to(ROOT).as_posix(),
            "canonical_sha256": sha_bytes(canonical(source)),
            "raw_response_sha256_at_freeze": sha_bytes(source_raw),
            "metadata_sha256": sha_bytes(canonical(metadata)),
            "raw_metadata_sha256_at_freeze": sha_bytes(metadata_raw),
            "feature_count": len(source.get("features") or []),
            "geometry_role": spec["role"],
            "event_date": spec["event_date"],
        })
    inventory = {
        "schema_version": "0.1",
        **GUARDS,
        "discovery_id": DISCOVERY_ID,
        "service": SERVICE,
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "layers": rows,
        "separation_guards": {
            "basin_geometry_is_event_footprint": False,
            "observed_event_footprints_are_basin_geometry": False,
            "provider_values_are_irfen_thresholds": False,
            "artificial_connector_used": False,
        },
    }
    write(SOURCE_INVENTORY, inventory)
    sync(False)


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
            raise ValueError("frozen Rio Tumbes source inventory missing; run --refresh-source once")
        sync(args.check_only)
    records = records_from_inventory()
    print(json.dumps({
        "status": "PASS_TUMBES_RIO_TUMBES_OFFICIAL_REPLAY",
        "discovery_id": DISCOVERY_ID,
        "basin_geometry_sha256": records["basin"]["normalized_sha256"],
        "event_footprints": 2,
        "activation_gate": "BLOCKED",
        "production_use": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
