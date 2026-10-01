#!/usr/bin/env python3
"""Capture current institutional Casma N7 polygons from the public MINAM layer.

This is a provenance-first, fail-closed research replay with three explicit
gates. Gate A captures one exact current institutional feature per CODIGO/NIVEL7
and freezes raw bytes plus SHA-256 without requiring historical name/area
equality. Gate B keeps 2007 ANA-INRENA lineage/equivalence separate and false
unless direct evidence establishes it. Gate C (topology/map) is not performed
here, so captured geometry remains non-publishable. The replay never digitizes
the PDF, infers outlets, creates event outcomes, routing parameters, hydraulic
capacity, thresholds, risk states or alerts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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


CAPTURE_FORMAT_VERSION = 3
PROVENANCE_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Content-Encoding",
    "Date",
    "Last-Modified",
    "ETag",
    "Server",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_response(url: str, *, accept: str, max_bytes: int = 15_000_000) -> tuple[bytes, dict]:
    """Return the undecoded response body plus HTTP provenance.

    The body is returned exactly as read from the socket; it is never parsed,
    re-serialized or re-encoded before being archived.
    """
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
            meta = {
                "requested_url": url,
                "final_url": response.geturl(),
                "http_status": getattr(response, "status", None),
                "headers": {
                    name: response.headers.get(name)
                    for name in PROVENANCE_HEADERS
                    if response.headers.get(name) is not None
                },
            }
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise SourceUnavailable(f"SOURCE_FETCH_FAILED {type(exc).__name__}") from exc
    if not data:
        raise SourceUnavailable("EMPTY_SOURCE")
    if len(data) > max_bytes:
        raise SourceUnavailable(f"SOURCE_TOO_LARGE actual>{max_bytes}")
    meta["retrieved_at_utc"] = utc_now()
    meta["body_size_bytes"] = len(data)
    meta["body_sha256"] = sha256_bytes(data)
    return data, meta


def fetch(url: str, *, accept: str, max_bytes: int = 15_000_000) -> bytes:
    return fetch_response(url, accept=accept, max_bytes=max_bytes)[0]


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


def native_query_url(contract: dict, code: str, source_wkid: int) -> str:
    """Same exact-code query in ArcGIS JSON, in the layer's storage CRS.

    For a MapServer layer, a query without outSR returns geometry in the
    spatial reference of the *map* (Esri REST "Query (Map Service/Layer)"),
    which for this service is 4326, i.e. a server-side projection. The layer
    resource's ``sourceSpatialReference`` reports the CRS the features are
    stored in, so the native request sets outSR to exactly that WKID, taken
    from the layer metadata captured in the same run and cross-checked against
    the contract. No datumTransformation is requested.
    """
    source = contract["source"]
    expected = int(source["expected_source_wkid"])
    if int(source_wkid) != expected:
        raise RecoveryError(f"NATIVE_OUTSR_NOT_DECLARED_SOURCE wkid={source_wkid} expected={expected}")
    params = {
        "where": f"{source['exact_identity_field']} = '{code}'",
        "outFields": ",".join(source["output_fields"]),
        "returnGeometry": "true",
        "outSR": str(expected),
        "returnZ": "false",
        "returnM": "false",
        "f": "json",
    }
    return source["layer_url"].rstrip("/") + "/query?" + urlencode(params)


def validate_native(contract: dict, expected: dict, doc: dict) -> dict:
    """Fail-closed identity check of the native (source-CRS) ArcGIS response.

    Establishes only that the native bytes describe the same exact-code
    feature; it asserts nothing about historical equivalence.
    """
    code = expected["code"]
    if not isinstance(doc, dict) or doc.get("error") is not None:
        raise RecoveryError(f"NATIVE_SERVICE_ERROR code={code}")
    if doc.get("exceededTransferLimit") is True:
        raise RecoveryError(f"NATIVE_TRANSFER_LIMIT_EXCEEDED code={code}")
    features = doc.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise RecoveryError(
            f"NATIVE_FEATURE_COUNT_MISMATCH code={code} "
            f"count={0 if not isinstance(features, list) else len(features)}"
        )
    sr = doc.get("spatialReference") or {}
    wkids = {sr.get("wkid"), sr.get("latestWkid")}
    if int(contract["source"]["expected_source_wkid"]) not in wkids:
        raise RecoveryError(f"NATIVE_WKID_DRIFT code={code} sr={sr}")
    attrs = features[0].get("attributes") or {}
    if str(attrs.get("CODIGO") or "").strip() != code:
        raise RecoveryError(f"NATIVE_CODE_MISMATCH code={code}")
    if str(attrs.get("NIVEL7") or "").strip() != code:
        raise RecoveryError(f"NATIVE_NIVEL7_MISMATCH code={code}")
    rings = (features[0].get("geometry") or {}).get("rings")
    if not isinstance(rings, list) or not rings or not all(isinstance(r, list) and r for r in rings):
        raise RecoveryError(f"NATIVE_EMPTY_GEOMETRY code={code}")
    return {"objectid": attrs.get("OBJECTID"), "spatial_reference": sr}


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
    """Gate A: validate and capture a current institutional N7 feature.

    Historical display-name/area comparisons are recorded as Gate B evidence
    but do not gate immutable capture. This function never establishes
    equivalence to the 2007 Uh_pfas100 geometry.
    """
    if isinstance(doc, dict) and doc.get("exceededTransferLimit") is True:
        raise RecoveryError(f"TRANSFER_LIMIT_EXCEEDED code={expected['code']}")
    features = doc.get("features")
    required_count = int(contract["validation"]["required_feature_count_per_code"])
    if not isinstance(features, list) or len(features) != required_count:
        raise RecoveryError(
            f"FEATURE_COUNT_MISMATCH code={expected['code']} "
            f"count={0 if not isinstance(features, list) else len(features)}"
        )
    feature = features[0]
    if feature.get("type") != "Feature":
        raise RecoveryError(f"NOT_GEOJSON_FEATURE code={expected['code']}")
    props = feature.get("properties") or {}

    actual_code = str(props.get("CODIGO") or "").strip()
    if actual_code != expected["code"]:
        raise RecoveryError(
            f"CODE_MISMATCH expected={expected['code']} actual={actual_code}"
        )

    nivel = props.get("NIVEL")
    if (
        contract["validation"]["require_level_7_when_level_field_present"]
        and nivel is not None
        and int(nivel) != 7
    ):
        raise RecoveryError(f"LEVEL_MISMATCH code={expected['code']} NIVEL={nivel}")

    actual_nivel7 = str(props.get("NIVEL7") or "").strip()
    if actual_nivel7 != expected["code"]:
        raise RecoveryError(
            f"NIVEL7_MISMATCH code={expected['code']} value={props.get('NIVEL7')}"
        )

    actual_name = service_name(props)
    actual_area = service_area(props)
    expected_name = str(expected["name"])
    expected_area = float(expected["area_km2"])

    exact_name_match = normalize_name(actual_name) == normalize_name(expected_name)

    def without_generic_rio(value: object) -> str:
        normalized = normalize_name(value)
        return normalized[4:] if normalized.startswith("rio ") else normalized

    bounded_name_match = (
        without_generic_rio(actual_name) == without_generic_rio(expected_name)
    )
    area_delta = actual_area - expected_area
    area_rel_pct = (area_delta / expected_area * 100.0) if expected_area else None
    historical_one_decimal_area_match = (
        round(actual_area, 1) == round(expected_area, 1)
    )

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise RecoveryError(f"MISSING_GEOMETRY code={expected['code']}")
    if geometry.get("type") not in set(
        contract["validation"]["allowed_geojson_geometry_types"]
    ):
        raise RecoveryError(
            f"GEOMETRY_TYPE_MISMATCH code={expected['code']} "
            f"type={geometry.get('type')}"
        )
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
        "gate_a_identity_pass": True,
        "historical_exact_name_match": exact_name_match,
        "historical_bounded_generic_rio_name_match": bounded_name_match,
        "historical_one_decimal_area_match": historical_one_decimal_area_match,
        "historical_area_delta_km2": round(area_delta, 6),
        "historical_area_delta_percent": (
            None if area_rel_pct is None else round(area_rel_pct, 6)
        ),
        "historical_geometry_equivalence_to_Uh_pfas100": False,
    }

def validate_metadata(contract: dict, metadata: dict) -> dict:
    """Validate the layer resource and return its declared spatial references.

    ``sourceSpatialReference`` (storage CRS of the source dataset) must equal
    the contract WKID, with a consistent latestWkid when present. The map
    ``spatialReference`` is recorded as provenance only; it is the CRS the
    service projects to when outSR is omitted and is never accepted as the
    native CRS.
    """
    source = contract["source"]
    if metadata.get("geometryType") != source["expected_geometry_type"]:
        raise RecoveryError(f"SERVICE_GEOMETRY_TYPE_DRIFT {metadata.get('geometryType')}")
    ssr = metadata.get("sourceSpatialReference") or {}
    expected = int(source["expected_source_wkid"])
    if int(ssr.get("wkid") or -1) != expected:
        raise RecoveryError(f"SOURCE_WKID_DRIFT {ssr}")
    if ssr.get("latestWkid") is not None and int(ssr["latestWkid"]) != expected:
        raise RecoveryError(f"SOURCE_LATEST_WKID_DRIFT {ssr}")
    names = {row.get("name") for row in metadata.get("fields", []) if isinstance(row, dict)}
    required = set(source["output_fields"])
    missing = sorted(required - names)
    if missing:
        raise RecoveryError(f"SERVICE_FIELDS_MISSING {missing}")
    formats = str(metadata.get("supportedQueryFormats") or "").lower()
    if "geojson" not in formats:
        raise RecoveryError("SERVICE_GEOJSON_SUPPORT_MISSING")
    return {
        "source_wkid": expected,
        "layer_source_spatial_reference": ssr,
        # A MapServer layer resource exposes the map SR through extent; a
        # top-level spatialReference may be absent (it is for MINAM layer 1).
        "layer_top_level_spatial_reference": metadata.get("spatialReference"),
        "layer_extent_spatial_reference": (metadata.get("extent") or {}).get("spatialReference"),
        "service_current_version": metadata.get("currentVersion"),
    }


def write_outputs(
    contract: dict,
    metadata_bytes: bytes,
    staged: list[dict],
    metadata_http: dict | None = None,
    service_crs: dict | None = None,
) -> dict:
    """Persist Gate A capture artifacts; do not authorize map publication.

    Raw response bodies are written with write_bytes exactly as received.
    Only the separate normalized FeatureCollection is re-serialized.
    """
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
    sums = {metadata_path.relative_to(archive_root).as_posix(): metadata_sha}
    normalized_features = []
    rows = []
    for row in staged:
        raw_path = archive_root / f"{row['expected']['code']}.geojson"
        raw_path.write_bytes(row["raw_bytes"])
        raw_sha = sha256_bytes(row["raw_bytes"])
        sums[raw_path.relative_to(archive_root).as_posix()] = raw_sha
        native_path = archive_root / f"{row['expected']['code']}.native.json"
        native_path.write_bytes(row["native_bytes"])
        native_sha = sha256_bytes(row["native_bytes"])
        sums[native_path.relative_to(archive_root).as_posix()] = native_sha
        feature = row["validated"]["feature"]
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
                "geometry_role": "CURRENT_INSTITUTIONAL_N7_RESEARCH_CAPTURE",
                "gate_a_source_capture": "PASS",
                "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
                "gate_c_topology_map": "PENDING",
                "historical_geometry_equivalence_to_Uh_pfas100": False,
                "map_publication_authorized": False,
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
            "expected_name_2007": row["expected"]["name"],
            "service_name": row["validated"]["actual_name"],
            "expected_area_km2_2007": row["expected"]["area_km2"],
            "service_area_km2": row["validated"]["actual_area_km2"],
            "historical_exact_name_match": row["validated"]["historical_exact_name_match"],
            "historical_bounded_generic_rio_name_match": row["validated"][
                "historical_bounded_generic_rio_name_match"
            ],
            "historical_one_decimal_area_match": row["validated"][
                "historical_one_decimal_area_match"
            ],
            "historical_area_delta_km2": row["validated"]["historical_area_delta_km2"],
            "historical_area_delta_percent": row["validated"][
                "historical_area_delta_percent"
            ],
            "historical_geometry_equivalence_to_Uh_pfas100": False,
            "bbox_wgs84": row["validated"]["bbox_wgs84"],
            "objectid": row["validated"]["objectid"],
            "query_url": row["query_url"],
            "raw_archive_path": raw_path.relative_to(ROOT).as_posix(),
            "raw_response_sha256": raw_sha,
            "raw_response_http": row.get("http"),
            "native_query_url": row["native_query_url"],
            "native_archive_path": native_path.relative_to(ROOT).as_posix(),
            "native_response_sha256": native_sha,
            "native_response_http": row.get("native_http"),
            "native_spatial_reference": row["native_validated"]["spatial_reference"],
            "native_objectid": row["native_validated"]["objectid"],
            "gate_a_identity_pass": True,
            "gate_a_raw_capture_pass": True,
            "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
            "gate_c_topology_map": "PENDING",
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
            "geometry_role": "CURRENT_INSTITUTIONAL_N7_RESEARCH_CAPTURE",
            "gate_a_source_capture": "PASS",
            "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
            "gate_c_topology_map": "PENDING",
            "historical_geometry_equivalence_to_Uh_pfas100": False,
            "map_publication_authorized": False,
            "map_eligible_as_research_context": False,
            "map_eligible_as_activation_geometry": False,
            "event_footprint": False,
            "routing_enabled": False,
            "risk_or_alert_layer": False,
        },
        "features": normalized_features,
    }
    geometry_path.write_text(canonical(geometry_doc), encoding="utf-8")
    geometry_sha = sha256_file(geometry_path)
    sums_path = archive_root / "SHA256SUMS"
    sums_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items())),
        encoding="utf-8",
    )
    retrieved_at = utc_now()
    manifest = {
        "schema_version": "0.1",
        "capture_format_version": CAPTURE_FORMAT_VERSION,
        "status": "PASS_GATE_A_CURRENT_INSTITUTIONAL_N7_CAPTURE",
        **SAFE,
        "dataset_id": "ancash_casma_n7_minam_official_v0_1",
        "retrieved_at_utc": retrieved_at,
        "source_layer_url": contract["source"]["layer_url"],
        "source_metadata_url": contract["source"]["metadata_url"],
        "source_native_wkid": contract["source"]["expected_source_wkid"],
        "query_output_wkid": contract["source"]["query_output_wkid"],
        "metadata_archive_path": metadata_path.relative_to(ROOT).as_posix(),
        "metadata_sha256": metadata_sha,
        "metadata_http": metadata_http,
        "sha256sums_path": sums_path.relative_to(ROOT).as_posix(),
        "sha256sums_sha256": sha256_file(sums_path),
        "crs_provenance": {
            "layer_source_spatial_reference": (service_crs or {}).get("layer_source_spatial_reference"),
            "layer_top_level_spatial_reference": (service_crs or {}).get("layer_top_level_spatial_reference"),
            "layer_extent_spatial_reference": (service_crs or {}).get("layer_extent_spatial_reference"),
            "service_current_version": (service_crs or {}).get("service_current_version"),
            "native_request_outSR": contract["source"]["expected_source_wkid"],
            "native_crs_basis": (
                "outSR set explicitly to the layer sourceSpatialReference, which Esri "
                "documents as the spatial reference features are stored in; a MapServer "
                "query without outSR returns the map spatial reference instead"
            ),
            "native_crs_role": "DECLARED_STORAGE_CRS_OF_SOURCE_DATASET",
            "geojson_crs_role": "SERVER_PROJECTION_TO_REQUESTED_OUTSR",
            "map_spatial_reference_accepted_as_native": False,
            "datum_transformation_requested": False,
        },
        "raw_bytes_policy": (
            "Response bodies archived byte-for-byte as received. The native ArcGIS "
            "JSON is requested with outSR equal to the layer's declared "
            "sourceSpatialReference (storage CRS); the GeoJSON is a server "
            "projection to the contract outSR. Only the normalized "
            "FeatureCollection is re-serialized."
        ),
        "independent_qa_source": contract["independent_qa"],
        "feature_count": len(rows),
        "features": rows,
        "geometry_path": geometry_path.relative_to(ROOT).as_posix(),
        "geometry_sha256": geometry_sha,
        "current_institutional_vector_recovered": True,
        "exact_current_code_capture_recovered": True,
        "exact_vector_recovered": False,
        "historical_geometry_equivalence_to_Uh_pfas100": False,
        "all_nine_identity_checks_passed": len(rows) == 9,
        "all_nine_raw_hashes_frozen": len(rows) == 9,
        "gate_a_source_capture": "PASS",
        "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
        "gate_c_topology_map": "PENDING",
        "pdf_digitization_used": False,
        "dem_backfill_used": False,
        "outlet_or_confluence_inferred": False,
        "event_outcome_used_for_geometry": False,
        "negative_control_created": False,
        "threshold_created": False,
        "map_publication_authorized": False,
        "map_eligible_as_research_context": False,
        "map_eligible_as_activation_geometry": False,
        "map_layers_registry_modified_by_this_replay": False,
        "rule": (
            "Gate A freezes current institutional N7 source bytes and exact identity only. "
            "Historical name/area drift is preserved as Gate B evidence and does not block "
            "capture. Gate B remains not established without direct Uh_pfas100 lineage, "
            "and Gate C topology QA is required before any map publication as "
            "CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT."
        ),
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
    if manifest.get("capture_format_version") != CAPTURE_FORMAT_VERSION:
        raise RecoveryError(
            f"UNSUPPORTED_CAPTURE_FORMAT {manifest.get('capture_format_version')}"
        )
    if manifest.get("status") != "PASS_GATE_A_CURRENT_INSTITUTIONAL_N7_CAPTURE":
        raise RecoveryError(f"UNKNOWN_MANIFEST_STATUS {manifest.get('status')}")
    if manifest.get("feature_count") != 9 or manifest.get("all_nine_identity_checks_passed") is not True:
        raise RecoveryError("INCOMPLETE_RECOVERY_MANIFEST")
    if manifest.get("all_nine_raw_hashes_frozen") is not True:
        raise RecoveryError("INCOMPLETE_RAW_HASH_CAPTURE")
    if manifest.get("gate_a_source_capture") != "PASS":
        raise RecoveryError("GATE_A_NOT_PASS")
    if manifest.get("gate_b_lineage_equivalence") != "NOT_ESTABLISHED":
        raise RecoveryError("GATE_B_UNEXPECTED_STATE")
    if manifest.get("gate_c_topology_map") != "PENDING":
        raise RecoveryError("GATE_C_UNEXPECTED_STATE")
    if manifest.get("historical_geometry_equivalence_to_Uh_pfas100") is not False:
        raise RecoveryError("HISTORICAL_EQUIVALENCE_MUST_REMAIN_FALSE")
    if manifest.get("map_publication_authorized") is not False:
        raise RecoveryError("MAP_PUBLICATION_MUST_REMAIN_BLOCKED")
    if manifest.get("map_eligible_as_research_context") is not False:
        raise RecoveryError("MAP_CONTEXT_ELIGIBILITY_MUST_REMAIN_FALSE")
    if sha256_file(metadata_path) != manifest["metadata_sha256"]:
        raise RecoveryError("METADATA_HASH_DRIFT")
    if sha256_file(geometry_path) != manifest["geometry_sha256"]:
        raise RecoveryError("GEOMETRY_HASH_DRIFT")
    for row in manifest["features"]:
        path = ROOT / row["raw_archive_path"]
        if sha256_file(path) != row["raw_response_sha256"]:
            raise RecoveryError(f"RAW_RESPONSE_HASH_DRIFT {row['code']}")
        native_path = ROOT / row["native_archive_path"]
        if sha256_file(native_path) != row["native_response_sha256"]:
            raise RecoveryError(f"NATIVE_RESPONSE_HASH_DRIFT {row['code']}")
        if row.get("historical_geometry_equivalence_to_Uh_pfas100") is not False:
            raise RecoveryError(f"ROW_HISTORICAL_EQUIVALENCE_DRIFT {row['code']}")
    verify_sha256sums(manifest)
    expected_wkid = int(contract["source"]["expected_source_wkid"])
    crs = manifest.get("crs_provenance") or {}
    if crs.get("native_request_outSR") != expected_wkid:
        raise RecoveryError("NATIVE_OUTSR_PROVENANCE_DRIFT")
    if crs.get("map_spatial_reference_accepted_as_native") is not False:
        raise RecoveryError("MAP_SR_ACCEPTED_AS_NATIVE")
    if int((crs.get("layer_source_spatial_reference") or {}).get("wkid") or -1) != expected_wkid:
        raise RecoveryError("LAYER_SOURCE_SR_PROVENANCE_DRIFT")
    for row in manifest["features"]:
        sr = row.get("native_spatial_reference") or {}
        if expected_wkid not in {sr.get("wkid"), sr.get("latestWkid")}:
            raise RecoveryError(f"ROW_NATIVE_WKID_DRIFT {row['code']} sr={sr}")
        if f"outSR={expected_wkid}" not in str(row.get("native_query_url")):
            raise RecoveryError(f"ROW_NATIVE_OUTSR_DRIFT {row['code']}")
    geometry = load(geometry_path)
    guard(geometry["properties"], "GEOMETRY")
    if len(geometry.get("features", [])) != 9:
        raise RecoveryError("GEOMETRY_FEATURE_COUNT_DRIFT")
    props = geometry["properties"]
    if props.get("map_publication_authorized") is not False:
        raise RecoveryError("GEOMETRY_MAP_PUBLICATION_DRIFT")
    if props.get("map_eligible_as_research_context") is not False:
        raise RecoveryError("GEOMETRY_MAP_ELIGIBILITY_DRIFT")
    return manifest

def verify_sha256sums(manifest: dict) -> None:
    """Cross-check the sha256sum-compatible ledger against the manifest."""
    sums_path = ROOT / manifest["sha256sums_path"]
    if sha256_file(sums_path) != manifest["sha256sums_sha256"]:
        raise RecoveryError("SHA256SUMS_HASH_DRIFT")
    archive_root = sums_path.parent
    listed = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        listed[name] = digest
    expected = {
        (ROOT / manifest["metadata_archive_path"]).relative_to(archive_root).as_posix(): manifest["metadata_sha256"],
    }
    for row in manifest["features"]:
        expected[(ROOT / row["raw_archive_path"]).relative_to(archive_root).as_posix()] = row["raw_response_sha256"]
        expected[(ROOT / row["native_archive_path"]).relative_to(archive_root).as_posix()] = row["native_response_sha256"]
    if listed != expected:
        raise RecoveryError("SHA256SUMS_MANIFEST_MISMATCH")
    for name, digest in listed.items():
        if sha256_file(archive_root / name) != digest:
            raise RecoveryError(f"SHA256SUMS_FILE_DRIFT {name}")


def refresh(contract: dict) -> dict:
    """Stage all nine exact-code captures in memory, then write atomically.

    Nothing is written unless metadata and all nine GeoJSON + native responses
    pass Gate A identity checks (partial archives are forbidden by contract).
    """
    metadata_bytes, metadata_http = fetch_response(
        contract["source"]["metadata_url"],
        accept="application/json,text/plain;q=0.9,*/*;q=0.1",
    )
    try:
        metadata = json.loads(metadata_bytes)
    except json.JSONDecodeError as exc:
        raise RecoveryError("SERVICE_METADATA_NOT_JSON") from exc
    service_crs = validate_metadata(contract, metadata)

    staged = []
    for expected in contract["units"]:
        code = expected["code"]
        url = query_url(contract, code)
        raw, http = fetch_response(url, accept="application/geo+json,application/json;q=0.9,*/*;q=0.1")
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RecoveryError(f"QUERY_NOT_JSON code={code}") from exc
        validated = validate_feature(contract, expected, doc)

        native_url = native_query_url(contract, code, service_crs["source_wkid"])
        native_raw, native_http = fetch_response(native_url, accept="application/json;q=0.9,*/*;q=0.1")
        try:
            native_doc = json.loads(native_raw)
        except json.JSONDecodeError as exc:
            raise RecoveryError(f"NATIVE_QUERY_NOT_JSON code={code}") from exc
        native_validated = validate_native(contract, expected, native_doc)
        if native_validated["objectid"] != validated["objectid"]:
            raise RecoveryError(
                f"NATIVE_GEOJSON_OBJECTID_MISMATCH code={code} "
                f"native={native_validated['objectid']} geojson={validated['objectid']}"
            )
        staged.append({
            "expected": expected,
            "query_url": url,
            "raw_bytes": raw,
            "http": http,
            "validated": validated,
            "native_query_url": native_url,
            "native_bytes": native_raw,
            "native_http": native_http,
            "native_validated": native_validated,
        })

    if len(staged) != 9:
        raise RecoveryError(f"INCOMPLETE_STAGE count={len(staged)}")
    manifest = write_outputs(contract, metadata_bytes, staged, metadata_http, service_crs)
    verify_existing(contract)
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

    manifest = refresh(contract)
    print(canonical({
        "status": manifest["status"],
        "feature_count": manifest["feature_count"],
        "geometry_sha256": manifest["geometry_sha256"],
    }).strip())


if __name__ == "__main__":
    main()
