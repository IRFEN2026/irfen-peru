#!/usr/bin/env python3
"""Freeze exact official ANA Río Tumbes source bytes without promoting geometry.

RESEARCH_ONLY / TEST_ONLY. This script preserves raw metadata and GeoJSON bytes
for the preregistered ANA layers 2, 66 and 67, plus deterministic canonical
GeoJSON and SHA-256 provenance. It does not update map assets, thresholds,
capacity, activation, alerts, negatives or operational state.

All three layers are fetched and validated in memory before any repository file
is written, so a partial upstream response cannot create a partial source lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_geometry_freeze_plan_v0_3.json"
OUT_ROOT = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_geometry"
INVENTORY = OUT_ROOT / "source_inventory_v0_3.json"

SERVICE = "https://geosnirh.ana.gob.pe/server/rest/services/Inundacion_Tumbes/Capas_Inundacion_Tumbes_04052023/MapServer"

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

SPECS = {
    "basin": {
        "layer_id": 2,
        "expected_name_contains": "Cuenca Tumbes",
        "role": "OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT",
        "event_date": None,
    },
    "event_20230428": {
        "layer_id": 66,
        "expected_name_contains": "28 Abril 2023",
        "role": "OBSERVED_EVENT_FOOTPRINT_ONLY",
        "event_date": "2023-04-28",
    },
    "event_20230504": {
        "layer_id": 67,
        "expected_name_contains": "04 Mayo 2023",
        "role": "OBSERVED_EVENT_FOOTPRINT_ONLY",
        "event_date": "2023-05-04",
    },
}


class SourceUnavailable(RuntimeError):
    pass


class SourceContractError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


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


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY-SOURCE-FREEZE/0.3"})
    last: Exception | None = None
    for delay in (0, 5, 20):
        if delay:
            time.sleep(delay)
        try:
            with urlopen(request, timeout=90) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last = exc
    raise SourceUnavailable(f"ANA_SOURCE_UNAVAILABLE: {last}")


def parse_json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceContractError(f"{label}_NOT_UTF8_JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SourceContractError(f"{label}_NOT_JSON_OBJECT")
    return value


def validate_plan(plan: dict) -> None:
    for key, expected in SAFE.items():
        if plan.get(key) != expected:
            raise SourceContractError(f"UNSAFE_PLAN_GUARD_{key}")
    rows = {row["key"]: row for row in plan.get("layers") or []}
    if set(rows) != set(SPECS):
        raise SourceContractError("PLAN_LAYER_KEYS_DO_NOT_MATCH_PREREGISTRATION")
    if plan.get("freeze_contract", {}).get("all_layers_must_validate_before_any_write") is not True:
        raise SourceContractError("PLAN_MUST_REQUIRE_ATOMIC_SOURCE_FREEZE")


def validate_metadata(metadata: dict, spec: dict) -> str:
    if metadata.get("id") != spec["layer_id"]:
        raise SourceContractError(f"UNEXPECTED_LAYER_ID_{metadata.get('id')}")
    name = str(metadata.get("name") or "")
    if norm(spec["expected_name_contains"]) not in norm(name):
        raise SourceContractError(f"UNEXPECTED_LAYER_NAME_{spec['layer_id']}_{name}")
    if "query" not in str(metadata.get("capabilities") or "").lower():
        raise SourceContractError(f"LAYER_NOT_QUERYABLE_{spec['layer_id']}")
    return name


def validate_geojson(fc: dict, spec: dict) -> tuple[int, list[str]]:
    if fc.get("type") != "FeatureCollection":
        raise SourceContractError(f"LAYER_{spec['layer_id']}_NOT_FEATURE_COLLECTION")
    features = fc.get("features") or []
    if not features:
        raise SourceContractError(f"LAYER_{spec['layer_id']}_EMPTY")
    if spec["event_date"] is None and len(features) != 1:
        raise SourceContractError(f"LAYER_2_EXPECTED_ONE_BASIN_FEATURE_GOT_{len(features)}")
    geometry_types = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type")
        if geometry_type not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
            raise SourceContractError(f"LAYER_{spec['layer_id']}_NONPOLYGON_OR_EMPTY_GEOMETRY")
        geometry_types.append(geometry_type)
    return len(features), sorted(set(geometry_types))


def build_freeze_records(payloads: dict[str, tuple[bytes, bytes]]) -> tuple[dict, dict[str, dict]]:
    """Validate all payloads and build deterministic inventory before disk writes."""
    records: dict[str, dict] = {}
    parsed: dict[str, dict] = {}
    for key, spec in SPECS.items():
        metadata_raw, geojson_raw = payloads[key]
        metadata = parse_json(metadata_raw, f"{key}_metadata")
        geojson = parse_json(geojson_raw, f"{key}_geojson")
        layer_name = validate_metadata(metadata, spec)
        feature_count, geometry_types = validate_geojson(geojson, spec)
        parsed[key] = {"metadata": metadata, "geojson": geojson}
        records[key] = {
            "key": key,
            "layer_id": spec["layer_id"],
            "layer_name": layer_name,
            "role": spec["role"],
            "event_date": spec["event_date"],
            "metadata_url": metadata_url(spec["layer_id"]),
            "query_url": query_url(spec["layer_id"]),
            "raw_metadata_sha256": sha256(metadata_raw),
            "canonical_metadata_sha256": sha256(canonical(metadata)),
            "raw_geojson_sha256": sha256(geojson_raw),
            "canonical_geojson_sha256": sha256(canonical(geojson)),
            "feature_count": feature_count,
            "geometry_types": geometry_types,
        }
    inventory = {
        "schema_version": "0.3",
        **SAFE,
        "discovery_id": "tumbes_rio_tumbes",
        "status": "PASS_OFFICIAL_ANA_EXACT_SOURCE_FREEZE",
        "service": SERVICE,
        "layers": [records[key] for key in SPECS],
        "scientific_guards": {
            "basin_geometry_is_event_footprint": False,
            "event_footprints_are_basin_geometry": False,
            "provider_alert_bands_are_irfen_thresholds": False,
            "observed_discharge_is_hydraulic_capacity": False,
            "transfer_to_zarumilla_or_zorritos_allowed": False,
            "event_footprint_implies_basin_activation": False,
            "absence_of_event_footprint_is_negative": False,
            "map_publication_authorized_by_this_freeze": False,
        },
    }
    return inventory, parsed


def fetch_all() -> dict[str, tuple[bytes, bytes]]:
    payloads: dict[str, tuple[bytes, bytes]] = {}
    for key, spec in SPECS.items():
        payloads[key] = (
            fetch_bytes(metadata_url(spec["layer_id"])),
            fetch_bytes(query_url(spec["layer_id"])),
        )
    return payloads


def write_atomic_freeze(payloads: dict[str, tuple[bytes, bytes]], inventory: dict, parsed: dict[str, dict]) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for key, spec in SPECS.items():
        metadata_raw, geojson_raw = payloads[key]
        prefix = f"layer_{spec['layer_id']}"
        (OUT_ROOT / f"{prefix}_metadata.raw.json").write_bytes(metadata_raw)
        (OUT_ROOT / f"{prefix}_query.raw.geojson").write_bytes(geojson_raw)
        (OUT_ROOT / f"{prefix}_metadata.canonical.json").write_bytes(canonical(parsed[key]["metadata"]))
        (OUT_ROOT / f"{prefix}_query.canonical.geojson").write_bytes(canonical(parsed[key]["geojson"]))
    inventory = dict(inventory)
    inventory["acquired_at_utc"] = datetime.now(timezone.utc).isoformat()
    INVENTORY.write_bytes(canonical(inventory))


def refresh_source() -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    validate_plan(plan)
    payloads = fetch_all()
    inventory, parsed = build_freeze_records(payloads)
    write_atomic_freeze(payloads, inventory, parsed)
    return inventory


def check_plan_only() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    validate_plan(plan)
    assert SPECS["basin"]["layer_id"] == 2
    assert SPECS["event_20230428"]["layer_id"] == 66
    assert SPECS["event_20230504"]["layer_id"] == 67


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-plan-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source == args.check_plan_only:
        raise SystemExit("choose exactly one of --refresh-source or --check-plan-only")
    if args.check_plan_only:
        check_plan_only()
        print(json.dumps({
            "status": "PASS_TUMBES_SOURCE_FREEZE_PLAN",
            "activation_gate": "BLOCKED",
            "production_use": False,
            "map_publication_authorized": False,
        }, sort_keys=True))
        return 0
    inventory = refresh_source()
    print(json.dumps({
        "status": inventory["status"],
        "layers": len(inventory["layers"]),
        "activation_gate": inventory["activation_gate"],
        "production_use": inventory["production_use"],
        "map_publication_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
