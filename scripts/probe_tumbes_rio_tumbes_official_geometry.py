#!/usr/bin/env python3
"""Freeze official ANA Rio Tumbes basin context and dated 2023 inundation footprints.

RESEARCH_ONLY / TEST_ONLY. Basin geometry and observed-event footprints remain separate.
No threshold, capacity, negative control, risk, activation or alert is derived here.
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

SPECS = {
    "basin": {
        "layer_id": 2,
        "source_id": "ANA-TUMBES-2023-MAPSERVER-BASIN",
        "name_contains": "Cuenca Tumbes",
        "snapshot": SOURCE_ROOT / "ana_cuenca_tumbes.geojson",
        "output": BASIN_GEOMETRY,
        "validation": BASIN_VALIDATION,
        "role": "OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT",
        "event_date": None,
    },
    "event_20230428": {
        "layer_id": 66,
        "source_id": "ANA-TUMBES-2023-INUNDATION-20230428",
        "name_contains": "Areas Inundadas Rio Tumbes 28 Abril 2023",
        "snapshot": SOURCE_ROOT / "ana_rio_tumbes_inundation_20230428.geojson",
        "output": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230428.geojson",
        "validation": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230428_validation.json",
        "role": "OBSERVED_EVENT_FOOTPRINT_ONLY",
        "event_date": "2023-04-28",
    },
    "event_20230504": {
        "layer_id": 67,
        "source_id": "ANA-TUMBES-2023-INUNDATION-20230504",
        "name_contains": "Areas Inundadas Rio Tumbes 04 Mayo 2023",
        "snapshot": SOURCE_ROOT / "ana_rio_tumbes_inundation_20230504.geojson",
        "output": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230504.geojson",
        "validation": EVENT_ROOT / "tumbes_rio_tumbes_observed_inundation_20230504_validation.json",
        "role": "OBSERVED_EVENT_FOOTPRINT_ONLY",
        "event_date": "2023-05-04",
    },
}


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def metadata_url(layer_id: int) -> str:
    return f"{SERVICE}/{layer_id}?f=pjson"


def query_url(layer_id: int) -> str:
    return f"{SERVICE}/{layer_id}/query?" + urlencode({
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    })


def fetch_json(url: str) -> tuple[dict, bytes]:
    request = Request(url, headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
    with urlopen(request, timeout=75) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")), raw


def validate_metadata(metadata: dict, spec: dict) -> str:
    if metadata.get("id") != spec["layer_id"]:
        raise ValueError(f"unexpected ANA layer id: {spec['source_id']}")
    name = str(metadata.get("name") or "")
    if normalized_text(spec["name_contains"]) not in normalized_text(name):
        raise ValueError(f"unexpected ANA layer name for {spec['source_id']}: {name}")
    if "query" not in str(metadata.get("capabilities") or "").lower():
        raise ValueError(f"ANA layer is not queryable: {spec['source_id']}")
    return name


def validate_source(source: dict, spec: dict) -> list[dict]:
    if source.get("type") != "FeatureCollection":
        raise ValueError(f"source is not FeatureCollection: {spec['source_id']}")
    features = source.get("features") or []
    if not features:
        raise ValueError(f"empty official layer: {spec['source_id']}")
    if spec["event_date"] is None and len(features) != 1:
        raise ValueError(f"Cuenca Tumbes expected exactly one feature, got {len(features)}")
    for feature in features:
        if (feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"non-polygon feature in {spec['source_id']}")
    return features


def make_normalized(source: dict, spec: dict, source_hash: str, layer_name: str) -> dict:
    features = validate_source(source, spec)
    out = []
    for index, feature in enumerate(features, start=1):
        is_event = spec["event_date"] is not None
        props = {
            "discovery_id": DISCOVERY_ID,
            "unit_id": f"{DISCOVERY_ID}_{spec['layer_id']}_{index}",
            "name": "Rio Tumbes basin context" if not is_event else f"Rio Tumbes observed inundation {spec['event_date']}",
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
            "counts_as_event_footprint": is_event,
            "counts_as_basin_geometry": not is_event,
            "provider_values_are_irfen_thresholds": False,
            "confidence": "HIGH_OFFICIAL_ANA_REPRODUCIBLE_GEOMETRY",
        }
        out.append({"type": "Feature", "id": props["unit_id"], "properties": props, "geometry": feature["geometry"]})
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
                if not is_event
                else "RESEARCH_ONLY observed event footprint; not basin geometry, future hazard, threshold, risk or alert."
            ),
        },
        "features": out,
    }


def make_validation(spec: dict, source_hash: str, normalized: dict, layer_name: str, metadata_hash: str) -> dict:
    is_event = spec["event_date"] is not None
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
        "normalized_path": spec["output"].relative_to(ROOT).as_posix(),
        "normalized_sha256": sha(canonical(normalized)),
        "feature_count": len(normalized["features"]),
        "geometry_role": spec["role"],
        "event_date": spec["event_date"],
        "counts_as_operational_geometry": False,
        "counts_as_event_footprint": is_event,
        "counts_as_basin_geometry": not is_event,
        "provider_values_are_irfen_thresholds": False,
        "artificial_connector_used": False,
    }


def assert_guards(document: dict, label: str) -> None:
    for key, expected in GUARDS.items():
        if document.get(key) != expected:
            raise ValueError(f"unsafe guard {label}: {key}")


def build_from_frozen(check_only: bool) -> dict[str, dict]:
    inventory = load(SOURCE_INVENTORY)
    assert_guards(inventory, "source inventory")
    rows = {row["key"]: row for row in inventory.get("layers") or []}
    if set(rows) != set(SPECS):
        raise ValueError("frozen source inventory does not contain exactly the three preregistered layers")
    records = {}
    for key, spec in SPECS.items():
        row = rows[key]
        snapshot = ROOT / row["snapshot_path"]
        if not snapshot.is_file():
            raise ValueError(f"missing frozen source snapshot: {key}")
        source = load(snapshot)
        source_hash = sha(canonical(source))
        if source_hash != row["canonical_sha256"]:
            raise ValueError(f"frozen source hash mismatch: {key}")
        validate_source(source, spec)
        normalized = make_normalized(source, spec, source_hash, row["layer_name"])
        validation = make_validation(spec, source_hash, normalized, row["layer_name"], row["metadata_sha256"])
        for path, value in ((spec["output"], normalized), (spec["validation"], validation)):
            if check_only:
                if not path.is_file() or path.read_bytes() != canonical(value):
                    raise ValueError(f"stale deterministic artifact: {path.relative_to(ROOT)}")
            else:
                write(path, value)
        records[key] = {
            "source_id": spec["source_id"],
            "event_date": spec["event_date"],
            "normalized_path": spec["output"].relative_to(ROOT).as_posix(),
            "normalized_sha256": sha(canonical(normalized)),
            "validation_path": spec["validation"].relative_to(ROOT).as_posix(),
            "validation_sha256": sha(canonical(validation)),
        }
    return records


def sync_contract_and_package(records: dict[str, dict], check_only: bool) -> None:
    contract = load(CONTRACT)
    package = load(PACKAGE)
    assert_guards(contract, "contract")
    assert_guards(package, "package")
    basin = records["basin"]
    contract["contract_status"] = "DISCOVERY_RESEARCH_ONLY_BASIN_CONTEXT_REPRODUCIBLE"
    contract["assets"]["geometry"].update({
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
    package["contract_status"] = "DISCOVERY_BASIN_CONTEXT_REPRODUCIBLE_EVENT_GEOMETRY_SEPARATE"
    package["assets"]["geometry"].update({
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
    reviews = [{
        "review_type": "OFFICIAL_ANA_BASIN_GEOMETRY_REPLAY",
        "source_id": basin["source_id"],
        "path": basin["normalized_path"],
        "sha256": basin["normalized_sha256"],
        "counts_as_event_footprint": False,
    }]
    for key in ("event_20230428", "event_20230504"):
        record = records[key]
        reviews.append({
            "review_type": "OFFICIAL_ANA_OBSERVED_INUNDATION_REPLAY",
            "source_id": record["source_id"],
            "event_date": record["event_date"],
            "path": record["normalized_path"],
            "sha256": record["normalized_sha256"],
            "counts_as_basin_geometry": False,
        })
    package["validation"]["review_evidence"] = reviews
    for path, value in ((CONTRACT, contract), (PACKAGE, package)):
        if check_only:
            if path.read_bytes() != canonical(value):
                raise ValueError(f"stale derived document: {path.relative_to(ROOT)}")
        else:
            write(path, value)


def refresh_source() -> None:
    rows = []
    for key, spec in SPECS.items():
        metadata, metadata_raw = fetch_json(metadata_url(spec["layer_id"]))
        layer_name = validate_metadata(metadata, spec)
        source, source_raw = fetch_json(query_url(spec["layer_id"]))
        validate_source(source, spec)
        write(spec["snapshot"], source)
        rows.append({
            "key": key,
            "source_id": spec["source_id"],
            "layer_id": spec["layer_id"],
            "layer_name": layer_name,
            "metadata_url": metadata_url(spec["layer_id"]),
            "query_url": query_url(spec["layer_id"]),
            "snapshot_path": spec["snapshot"].relative_to(ROOT).as_posix(),
            "canonical_sha256": sha(canonical(source)),
            "raw_response_sha256_at_freeze": sha(source_raw),
            "metadata_sha256": sha(canonical(metadata)),
            "raw_metadata_sha256_at_freeze": sha(metadata_raw),
            "feature_count": len(source.get("features") or []),
            "geometry_role": spec["role"],
            "event_date": spec["event_date"],
        })
    write(SOURCE_INVENTORY, {
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
    })


def run(refresh: bool, check_only: bool) -> dict[str, dict]:
    if refresh:
        refresh_source()
    if not SOURCE_INVENTORY.is_file():
        raise ValueError("frozen Rio Tumbes source inventory missing")
    records = build_from_frozen(check_only)
    sync_contract_and_package(records, check_only)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source and args.check_only:
        raise ValueError("--refresh-source and --check-only are mutually exclusive")
    records = run(args.refresh_source, args.check_only)
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
