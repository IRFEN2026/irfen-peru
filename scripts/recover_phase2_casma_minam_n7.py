#!/usr/bin/env python3
"""Recover exact Casma N7 polygons from the public MINAM ArcGIS feature layer.

This is a provenance-first, fail-closed research replay. It accepts only exact
CODIGO matches that independently agree with the 2007 ANA-INRENA inventory on
identity and one-decimal area. It never digitizes the PDF, infers outlets,
creates event outcomes, routing parameters, hydraulic capacity, thresholds,
risk states or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"
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


class RecoveryError(RuntimeError):
    pass


class SourceUnavailable(RecoveryError):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def guard(doc: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if doc.get(key) != expected:
            raise RecoveryError(f"UNSAFE_{label}_{key}")


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def fetch(url: str, *, accept: str, max_bytes: int = 15_000_000) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
            "Accept": accept,
        },
    )
    try:
        with urlopen(req, timeout=120) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                raise SourceUnavailable(f"SOURCE_TOO_LARGE declared={declared}")
            data = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise SourceUnavailable(f"SOURCE_FETCH_FAILED {type(exc).__name__}") from exc
    if not data:
        raise SourceUnavailable("EMPTY_SOURCE")
    if len(data) > max_bytes:
        raise SourceUnavailable(f"SOURCE_TOO_LARGE actual>{max_bytes}")
    return data


def query_url(contract: dict, code: str) -> str:
    source = contract["source"]
    fields = ",".join(source["output_fields"])
    params = {
        "where": f"{source['exact_identity_field']} = '{code}'",
        "outFields": fields,
        "returnGeometry": "true",
        "outSR": str(source["query_output_wkid"]),
        "returnZ": "false",
        "returnM": "false",
        "f": "geojson",
    }
    return source["layer_url"].rstrip("/") + "/query?" + urlencode(params)


def iter_positions(value):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from iter_positions(item)


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    coords = list(iter_positions(geometry.get("coordinates")))
    if not coords:
        raise RecoveryError("EMPTY_GEOMETRY_COORDINATES")
    if any(not (math.isfinite(x) and math.isfinite(y)) for x, y in coords):
        raise RecoveryError("NONFINITE_GEOMETRY_COORDINATE")
    xs = [row[0] for row in coords]
    ys = [row[1] for row in coords]
    return min(xs), min(ys), max(xs), max(ys)


def service_area(props: dict) -> float:
    value = props.get("AREA_KM2")
    if value is None:
        value = props.get("AREA_FINAL")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise RecoveryError("MISSING_OR_INVALID_SERVICE_AREA")
    return float(value)


def service_name(props: dict) -> str:
    candidates = [props.get("NOMB_UH_N7"), props.get("Nombre_UH")]
    for value in candidates:
        if value is not None and str(value).strip():
            return str(value).strip()
    raise RecoveryError("MISSING_SERVICE_NAME")


def validate_feature(contract: dict, expected: dict, doc: dict) -> dict:
    features = doc.get("features")
    required_count = int(contract["validation"]["required_feature_count_per_code"])
    if not isinstance(features, list) or len(features) != required_count:
        raise RecoveryError(f"FEATURE_COUNT_MISMATCH code={expected['code']} count={0 if not isinstance(features,list) else len(features)}")
    feature = features[0]
    if feature.get("type") != "Feature":
        raise RecoveryError(f"NOT_GEOJSON_FEATURE code={expected['code']}")
    props = feature.get("properties") or {}
    actual_code = str(props.get("CODIGO") or "").strip()
    if actual_code != expected["code"]:
        raise RecoveryError(f"CODE_MISMATCH expected={expected['code']} actual={actual_code}")
    nivel = props.get("NIVEL")
    if contract["validation"]["require_level_7_when_level_field_present"] and nivel is not None and int(nivel) != 7:
        raise RecoveryError(f"LEVEL_MISMATCH code={expected['code']} NIVEL={nivel}")
    if str(props.get("NIVEL7") or "").strip() not in {"", expected["code"]}:
        raise RecoveryError(f"NIVEL7_MISMATCH code={expected['code']} value={props.get('NIVEL7')}")
    actual_name = service_name(props)
    if normalize_name(actual_name) != normalize_name(expected["name"]):
        raise RecoveryError(f"NAME_MISMATCH code={expected['code']} expected={expected['name']} actual={actual_name}")
    actual_area = service_area(props)
    if round(actual_area, 1) != round(float(expected["area_km2"]), 1):
        raise RecoveryError(
            f"AREA_MISMATCH code={expected['code']} expected={expected['area_km2']:.1f} actual={actual_area:.6f}"
        )
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise RecoveryError(f"MISSING_GEOMETRY code={expected['code']}")
    if geometry.get("type") not in set(contract["validation"]["allowed_geojson_geometry_types"]):
        raise RecoveryError(f"GEOMETRY_TYPE_MISMATCH code={expected['code']} type={geometry.get('type')}")
    bbox = geometry_bbox(geometry)
    bounds = contract["validation"]["casma_bbox_wgs84"]
    if not (
        bounds["min_lon"] <= bbox[0] <= bounds["max_lon"]
        and bounds["min_lon"] <= bbox[2] <= bounds["max_lon"]
        and bounds["min_lat"] <= bbox[1] <= bounds["max_lat"]
        and bounds["min_lat"] <= bbox[3] <= bounds["max_lat"]
    ):
        raise RecoveryError(f"CASMA_BBOX_MISMATCH code={expected['code']} bbox={bbox}")
    return {
        "feature": feature,
        "actual_name": actual_name,
        "actual_area_km2": actual_area,
        "bbox_wgs84": [round(v, 8) for v in bbox],
        "objectid": props.get("OBJECTID"),
    }


def validate_metadata(contract: dict, metadata: dict) -> None:
    source = contract["source"]
    if metadata.get("geometryType") != source["expected_geometry_type"]:
        raise RecoveryError(f"SERVICE_GEOMETRY_TYPE_DRIFT {metadata.get('geometryType')}")
    ssr = metadata.get("sourceSpatialReference") or {}
    if int(ssr.get("wkid") or -1) != int(source["expected_source_wkid"]):
        raise RecoveryError(f"SOURCE_WKID_DRIFT {ssr}")
    names = {row.get("name") for row in metadata.get("fields", []) if isinstance(row, dict)}
    required = set(source["output_fields"])
    missing = sorted(required - names)
    if missing:
        raise RecoveryError(f"SERVICE_FIELDS_MISSING {missing}")
    formats = str(metadata.get("supportedQueryFormats") or "").lower()
    if "geojson" not in formats:
        raise RecoveryError("SERVICE_GEOJSON_SUPPORT_MISSING")


def write_outputs(contract: dict, metadata_bytes: bytes, staged: list[dict]) -> dict:
    outputs = contract["outputs"]
    archive_root = ROOT / outputs["archive_root"]
    metadata_path = ROOT / outputs["metadata_archive_path"]
    geometry_path = ROOT / outputs["geometry_path"]
    manifest_path = ROOT / outputs["manifest_path"]
    archive_root.mkdir(parents=True, exist_ok=True)
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_path.write_bytes(metadata_bytes)
    metadata_sha = sha256_bytes(metadata_bytes)
    normalized_features = []
    rows = []
    for row in staged:
        raw_path = archive_root / f"{row['expected']['code']}.geojson"
        raw_path.write_bytes(row["raw_bytes"])
        raw_sha = sha256_bytes(row["raw_bytes"])
        feature = row["validated"]["feature"]
        props = feature.get("properties") or {}
        normalized_features.append({
            "type": "Feature",
            "properties": {
                **SAFE,
                "unit_id": f"ancash_casma_n7__{row['expected']['code']}",
                "parent_context": "ancash_casma_sechin_yautan",
                "n7_code": row["expected"]["code"],
                "name": row["validated"]["actual_name"],
                "area_km2_service": row["validated"]["actual_area_km2"],
                "area_km2_ana_inrena_2007": row["expected"]["area_km2"],
                "source_institution": contract["source"]["institution"],
                "source_layer_url": contract["source"]["layer_url"],
                "source_query_url": row["query_url"],
                "source_native_wkid": contract["source"]["expected_source_wkid"],
                "output_wkid": contract["source"]["query_output_wkid"],
                "raw_response_sha256": raw_sha,
                "source_objectid": row["validated"]["objectid"],
                "geometry_role": "OFFICIAL_N7_HYDROGRAPHIC_CONTEXT",
                "activation_evidence": False,
                "event_footprint": False,
                "outlet_or_confluence": False,
                "routing_parameter": False,
                "historical_hydraulic_capacity": False,
                "risk_or_alert_layer": False,
            },
            "geometry": feature["geometry"],
        })
        rows.append({
            "code": row["expected"]["code"],
            "expected_name": row["expected"]["name"],
            "service_name": row["validated"]["actual_name"],
            "expected_area_km2": row["expected"]["area_km2"],
            "service_area_km2": row["validated"]["actual_area_km2"],
            "bbox_wgs84": row["validated"]["bbox_wgs84"],
            "objectid": row["validated"]["objectid"],
            "query_url": row["query_url"],
            "raw_archive_path": raw_path.relative_to(ROOT).as_posix(),
            "raw_response_sha256": raw_sha,
            "identity_pass": True,
            "area_pass": True,
            "geometry_pass": True,
        })

    normalized_features.sort(key=lambda f: f["properties"]["n7_code"])
    geometry_doc = {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "dataset_id": "ancash_casma_n7_minam_official_v0_1",
            "parent_context": "ancash_casma_sechin_yautan",
            "source_institution": contract["source"]["institution"],
            "source_native_wkid": contract["source"]["expected_source_wkid"],
            "output_wkid": contract["source"]["query_output_wkid"],
            "geometry_role": "OFFICIAL_N7_HYDROGRAPHIC_CONTEXT",
            "map_eligible_as_research_context": True,
            "map_eligible_as_activation_geometry": False,
            "event_footprint": False,
            "routing_enabled": False,
            "risk_or_alert_layer": False,
        },
        "features": normalized_features,
    }
    geometry_path.write_text(canonical(geometry_doc), encoding="utf-8")
    geometry_sha = sha256_file(geometry_path)
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": "0.1",
        "status": "PASS_REPRODUCIBLE_MINAM_CASMA_N7_OFFICIAL_GEOMETRY",
        **SAFE,
        "dataset_id": "ancash_casma_n7_minam_official_v0_1",
        "retrieved_at_utc": retrieved_at,
        "source_layer_url": contract["source"]["layer_url"],
        "source_metadata_url": contract["source"]["metadata_url"],
        "source_native_wkid": contract["source"]["expected_source_wkid"],
        "query_output_wkid": contract["source"]["query_output_wkid"],
        "metadata_archive_path": metadata_path.relative_to(ROOT).as_posix(),
        "metadata_sha256": metadata_sha,
        "independent_qa_source": contract["independent_qa"],
        "feature_count": len(rows),
        "features": rows,
        "geometry_path": geometry_path.relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "exact_vector_recovered": True,
        "all_nine_identity_checks_passed": len(rows) == 9,
        "pdf_digitization_used": False,
        "dem_backfill_used": False,
        "outlet_or_confluence_inferred": False,
        "event_outcome_used_for_geometry": False,
        "negative_control_created": False,
        "threshold_created": False,
        "map_eligible_as_research_context": True,
        "map_eligible_as_activation_geometry": False,
        "map_layers_registry_modified_by_this_replay": False,
        "rule": "Geometry may be presented only as official N7 hydrographic research context after independent PR QA; it is not activation evidence, an event footprint, routing, capacity, risk or alert semantics.",
    }
    manifest_path.write_text(canonical(manifest), encoding="utf-8")
    return manifest


def verify_existing(contract: dict) -> dict:
    outputs = contract["outputs"]
    manifest_path = ROOT / outputs["manifest_path"]
    geometry_path = ROOT / outputs["geometry_path"]
    metadata_path = ROOT / outputs["metadata_archive_path"]
    manifest = load(manifest_path)
    guard(manifest, "MANIFEST")
    if manifest.get("status") != "PASS_REPRODUCIBLE_MINAM_CASMA_N7_OFFICIAL_GEOMETRY":
        raise RecoveryError(f"UNKNOWN_MANIFEST_STATUS {manifest.get('status')}")
    if manifest.get("feature_count") != 9 or manifest.get("all_nine_identity_checks_passed") is not True:
        raise RecoveryError("INCOMPLETE_RECOVERY_MANIFEST")
    if sha256_file(metadata_path) != manifest["metadata_sha256"]:
        raise RecoveryError("METADATA_HASH_DRIFT")
    if sha256_file(geometry_path) != manifest["geometry_sha256"]:
        raise RecoveryError("GEOMETRY_HASH_DRIFT")
    for row in manifest["features"]:
        path = ROOT / row["raw_archive_path"]
        if sha256_file(path) != row["raw_response_sha256"]:
            raise RecoveryError(f"RAW_RESPONSE_HASH_DRIFT {row['code']}")
    geometry = load(geometry_path)
    guard(geometry["properties"], "GEOMETRY")
    if len(geometry.get("features", [])) != 9:
        raise RecoveryError("GEOMETRY_FEATURE_COUNT_DRIFT")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    guard(contract, "CONTRACT")

    manifest_path = ROOT / contract["outputs"]["manifest_path"]
    if manifest_path.is_file() and not args.refresh:
        manifest = verify_existing(contract)
        print(canonical({"status": manifest["status"], "feature_count": manifest["feature_count"]}).strip())
        return
    if not args.refresh:
        raise RecoveryError("MISSING_MANIFEST_REFRESH_REQUIRED")

    metadata_bytes = fetch(contract["source"]["metadata_url"], accept="application/json,text/plain;q=0.9,*/*;q=0.1")
    try:
        metadata = json.loads(metadata_bytes)
    except json.JSONDecodeError as exc:
        raise RecoveryError("SERVICE_METADATA_NOT_JSON") from exc
    validate_metadata(contract, metadata)

    staged = []
    for expected in contract["units"]:
        url = query_url(contract, expected["code"])
        raw = fetch(url, accept="application/geo+json,application/json;q=0.9,*/*;q=0.1")
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RecoveryError(f"QUERY_NOT_JSON code={expected['code']}") from exc
        validated = validate_feature(contract, expected, doc)
        staged.append({"expected": expected, "query_url": url, "raw_bytes": raw, "validated": validated})

    if len(staged) != 9:
        raise RecoveryError(f"INCOMPLETE_STAGE count={len(staged)}")
    manifest = write_outputs(contract, metadata_bytes, staged)
    verify_existing(contract)
    print(canonical({
        "status": manifest["status"],
        "feature_count": manifest["feature_count"],
        "geometry_sha256": manifest["geometry_sha256"],
    }).strip())


if __name__ == "__main__":
    main()
