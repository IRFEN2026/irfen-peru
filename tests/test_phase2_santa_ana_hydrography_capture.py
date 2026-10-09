#!/usr/bin/env python3
"""Research-only ANA Santa current-hydrography raw capture.

This tool is deliberately independent of the ANA 2011 axis/model/floodplain.
It archives HTTP response bytes and SHA-256 when the public ArcGIS service
responds; a failed/partial request never implies absence of the Santa river.
No map publication, datum inference, event or operational activation.
Run: python tests/test_phase2_santa_ana_hydrography_capture.py --capture
Default invocation runs offline contract regression tests only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "data/phase2/source_archive/santa_ana_hydrography"
MAX_BYTES = 8_000_000
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
class CaptureError(ValueError):
    pass

class SourceUnavailable(CaptureError):
    pass

def query_url() -> str:
    return LAYER + "/query?" + urlencode({
        "where": WHERE, "outFields": FIELDS,
        "returnGeometry": "true", "outSR": "4326", "f": "geojson",
    })

def metadata_url() -> str:
    return LAYER + "?f=pjson"

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def fetch_raw(url: str) -> tuple[bytes, dict]:
    req = Request(url, headers={
        "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
        "Accept": "application/geo+json,application/json",
        "Accept-Encoding": "identity",
    })
    try:
        with urlopen(req, timeout=90) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_BYTES:
                raise SourceUnavailable("SOURCE_TOO_LARGE")
            raw = response.read(MAX_BYTES + 1)
            meta = {
                "final_url": response.geturl(),
                "http_status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise SourceUnavailable("SOURCE_ACCESS_UNAVAILABLE: " + type(exc).__name__) from exc
    if not raw or len(raw) > MAX_BYTES:
        raise SourceUnavailable("EMPTY_OR_OVERSIZE_RESPONSE")
    if meta["http_status"] != 200:
        raise SourceUnavailable("HTTP_NON_200")
    return raw, meta

def decode(raw: bytes) -> dict:
    try:
        doc = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CaptureError("SOURCE_NOT_VALID_JSON") from exc
    if not isinstance(doc, dict) or doc.get("error"):
        raise CaptureError("ARCGIS_SOURCE_ERROR")
    if doc.get("exceededTransferLimit") is True:
        raise CaptureError("PARTIAL_SOURCE_TRANSFER")
    return doc

def validate_metadata(doc: dict) -> None:
    if doc.get("geometryType") != "esriGeometryPolyline":
        raise CaptureError("UNEXPECTED_SOURCE_GEOMETRY_TYPE")
    names = {row.get("name") for row in doc.get("fields", []) if isinstance(row, dict)}
    if not set(FIELDS.split(",")).issubset(names):
        raise CaptureError("SOURCE_FIELDS_MISSING")
    if "geojson" not in str(doc.get("supportedQueryFormats", "")).lower():
        raise CaptureError("GEOJSON_QUERY_NOT_SUPPORTED")

def positions(coords):
    if isinstance(coords, (list, tuple)):
        if len(coords) >= 2 and all(type(x) in (int, float) for x in coords[:2]):
            yield float(coords[0]), float(coords[1])
        else:
            for item in coords:
                yield from positions(item)

def validate_candidates(doc: dict) -> list[dict]:
    features = doc.get("features")
    if doc.get("type") != "FeatureCollection" or not isinstance(features, list) or not features:
        raise CaptureError("NO_VERIFIED_FEATURE_COLLECTION")
    rows = []
    for feature in features:
        if feature.get("type") != "Feature":
            raise CaptureError("NON_FEATURE_RETURNED")
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in ("LineString", "MultiLineString"):
            raise CaptureError("UNEXPECTED_FEATURE_GEOMETRY")
        coords = list(positions(geometry.get("coordinates")))
        if not coords or any(not all(map(math.isfinite, xy)) for xy in coords):
            raise CaptureError("INVALID_OR_EMPTY_COORDINATES")
        if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in coords):
            raise CaptureError("NON_WGS84_COORDINATE_BOUNDS")
        props = feature.get("properties") or {}
        if not set(FIELDS.split(",")).issubset(props):
            raise CaptureError("CANDIDATE_ATTRIBUTES_MISSING")
        names = (str(props.get("NOMBRE_CA") or "") + " " + str(props.get("NOMBRE_UH") or "")).casefold()
        if "santa" not in names:
            raise CaptureError("CANDIDATE_NOT_MATCHING_QUERY")
        xs, ys = zip(*coords)
        rows.append({
            "objectid": props.get("OBJECTID_1"),
            "codigo_ca": props.get("CODIGO_CA"),
            "nombre_ca": props.get("NOMBRE_CA"),
            "tipo_ca": props.get("TIPO_CA"),
            "nombre_uh": props.get("NOMBRE_UH"),
            "codigo_uh": props.get("CODIGO_UH"),
            "long_km": props.get("LONG_KM"),
            "geometry_type": geometry["type"],
            "bbox_wgs84": [min(xs), min(ys), max(xs), max(ys)],
        })
    return rows

def write_immutable(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.read_bytes() != raw:
            raise CaptureError("IMMUTABLE_ARCHIVE_CONFLICT")
        return
    path.write_bytes(raw)

def capture(archive: Path) -> dict:
    meta_raw, meta_http = fetch_raw(metadata_url())
    validate_metadata(decode(meta_raw))
    query_raw, query_http = fetch_raw(query_url())
    candidates = validate_candidates(decode(query_raw))
    source_sha, metadata_sha = digest(query_raw), digest(meta_raw)
    manifest = {
        "schema_version": "0.1",
        "assessment_id": "santa_current_ana_hydrography_raw_capture_v0_1",
        **GUARDS,
        "scientific_role": "CURRENT_ANA_HYDROGRAPHY_CONTEXT",
        "map_publication_authorized": False,
        "historical_2011_axis_equivalence": False,
        "historical_2011_datum": "UNKNOWN",
        "historical_2011_model_or_floodplain_recovered": False,
        "source": {"institution": "ANA", "layer_url": LAYER,
                   "query_url": query_url(), "metadata_url": metadata_url(),
                   "raw_geojson_sha256": source_sha, "metadata_sha256": metadata_sha,
                   "raw_geojson_size_bytes": len(query_raw),
                   "metadata_size_bytes": len(meta_raw),
                   "query_http": query_http, "metadata_http": meta_http},
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "note": "Candidate lines are current ANA context, not the ANA 2011 axis, model or floodplain. No inferred datum.",
    }
    archive.mkdir(parents=True, exist_ok=True)
    write_immutable(archive / ("metadata_" + metadata_sha + ".pjson"), meta_raw)
    write_immutable(archive / ("query_" + source_sha + ".geojson"), query_raw)
    write_immutable(archive / ("manifest_" + source_sha + ".json"),
                    (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    return manifest

class TestSantaHydrographyFreeze(unittest.TestCase):
    def test_exact_query_and_context_only(self):
        args = parse_qs(urlparse(query_url()).query)
        self.assertEqual(args["where"], [WHERE])
        self.assertEqual(args["outSR"], ["4326"])
        self.assertEqual(args["returnGeometry"], ["true"])
        self.assertEqual(args["f"], ["geojson"])
        self.assertEqual(GUARDS["activation_gate"], "BLOCKED")
        self.assertIsNone(GUARDS["decision_thresholds"])
        self.assertIsNone(GUARDS["hydraulic_factors"])
        self.assertFalse(GUARDS["production_use"])
        self.assertFalse(GUARDS["operational_alerting_enabled"])

    def test_empty_or_error_never_counts_as_negative(self):
        for doc in ({"error": {"message": "offline"}}, {"features": []}):
            with self.assertRaises(CaptureError):
                validate_candidates(decode(json.dumps(doc).encode()))

    def test_partial_and_bad_geometry_rejected(self):
        with self.assertRaises(CaptureError):
            decode(b'{"exceededTransferLimit":true}')
        with self.assertRaises(CaptureError):
            validate_candidates({"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": []},
                 "properties": {}}]})

    def test_missing_metadata_fields_rejected(self):
        with self.assertRaises(CaptureError):
            validate_metadata({"geometryType": "esriGeometryPolyline",
                               "fields": [], "supportedQueryFormats": "geoJSON"})

if __name__ == "__main__":
    if "--capture" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--capture", action="store_true")
        parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
        args = parser.parse_args()
        try:
            result = capture(args.archive)
            print(json.dumps({"status": "CURRENT_CONTEXT_CAPTURED_RESEARCH_ONLY",
                              "raw_sha256": result["source"]["raw_geojson_sha256"],
                              "candidate_count": result["candidate_count"]}, sort_keys=True))
        except (CaptureError, SourceUnavailable) as exc:
            print("SOURCE_ACCESS_UNAVAILABLE_OR_QA_BLOCKED: " + str(exc), file=sys.stderr)
            sys.exit(2)
    else:
        unittest.main()
