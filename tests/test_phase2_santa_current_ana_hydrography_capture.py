#!/usr/bin/env python3
"""Fail-closed source capture for CURRENT ANA Santa hydrography, never Santa 2011.

Source: ANA ONRH/Rios_Quebradas_AAVI/MapServer/0 (official metadata and
the original live query are documented in IRFEN PR #334). This script does
not transform or publish the 2011 native axis or infer hydraulic properties.

Run offline tests:
  python -m unittest discover -s tests -p 'test_phase2_santa_current_ana_hydrography_capture.py' -v
Run a single public-source attempt (never automatically overwrites a freeze):
  python tests/test_phase2_santa_current_ana_hydrography_capture.py --capture --out-dir /tmp/santa-ana-freeze
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
MAX_BYTES = 25_000_000
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
LABEL = "CURRENT_ANA_HYDROGRAPHY_CONTEXT_CANDIDATES_ONLY"


class CaptureRejected(ValueError):
    """Invalid/incomplete source response: never freeze or infer a negative."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def urls() -> tuple[str, str]:
    common = {"where": WHERE}
    count = LAYER + "/query?" + urlencode({**common, "returnCountOnly": "true", "f": "json"})
    features = LAYER + "/query?" + urlencode({
        **common, "outFields": FIELDS, "returnGeometry": "true",
        "outSR": "4326", "f": "geojson",
    })
    return count, features


def fetch_once(url: str, timeout: int = 35) -> tuple[bytes, dict]:
    request = Request(url, headers={
        "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
        "Accept": "application/json,application/geo+json",
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise CaptureRejected("SOURCE_RESPONSE_TOO_LARGE")
        metadata = {
            "requested_url": url,
            "final_url": response.geturl(),
            "http_status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "response_sha256": sha256(raw),
            "response_bytes": len(raw),
        }
        if response.status != 200:
            raise CaptureRejected("SOURCE_HTTP_NOT_200")
        return raw, metadata


def parse_json(raw: bytes) -> dict:
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise CaptureRejected("SOURCE_NOT_JSON") from exc
    if not isinstance(doc, dict) or "error" in doc:
        raise CaptureRejected("SOURCE_ESRI_ERROR_OR_NONOBJECT")
    if doc.get("exceededTransferLimit") is True:
        raise CaptureRejected("SOURCE_TRANSFER_LIMIT")
    return doc


def validate_count(raw: bytes) -> int:
    doc = parse_json(raw)
    n = doc.get("count")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise CaptureRejected("SOURCE_COUNT_UNAVAILABLE")
    if n == 0:
        raise CaptureRejected("SOURCE_NO_CANDIDATES_UNKNOWN_NOT_ABSENCE")
    return n


def positions(geometry: dict):
    typ = geometry.get("type")
    coords = geometry.get("coordinates")
    if typ == "LineString":
        lines = [coords]
    elif typ == "MultiLineString":
        lines = coords
    else:
        raise CaptureRejected("SOURCE_NOT_POLYLINE")
    if not isinstance(lines, list) or not lines:
        raise CaptureRejected("SOURCE_EMPTY_GEOMETRY")
    out = []
    for line in lines:
        if not isinstance(line, list) or len(line) < 2:
            raise CaptureRejected("SOURCE_BAD_LINE")
        for point in line:
            if not isinstance(point, list) or len(point) < 2:
                raise CaptureRejected("SOURCE_BAD_POSITION")
            x, y = point[:2]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   for v in (x, y)):
                raise CaptureRejected("SOURCE_NONFINITE_POSITION")
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                raise CaptureRejected("SOURCE_COORDINATES_OUTSIDE_EPSG4326")
            out.append((x, y))
    return out


def validate_features(raw: bytes, expected_count: int) -> list[dict]:
    doc = parse_json(raw)
    if doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
        raise CaptureRejected("SOURCE_NOT_GEOJSON_FEATURECOLLECTION")
    crs = doc.get("crs")
    if crs is not None and crs != {"type": "name", "properties": {"name": "EPSG:4326"}}:
        raise CaptureRejected("SOURCE_UNEXPECTED_CRS")
    features = doc["features"]
    if len(features) != expected_count:
        raise CaptureRejected("SOURCE_COUNT_MISMATCH_OR_TRUNCATION")
    result = []
    seen_ids = set()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise CaptureRejected("SOURCE_INVALID_FEATURE")
        props = feature.get("properties")
        geom = feature.get("geometry")
        if not isinstance(props, dict) or not isinstance(geom, dict):
            raise CaptureRejected("SOURCE_MISSING_ATTRIBUTES_OR_GEOMETRY")
        if not all(key in props for key in FIELDS.split(",")):
            raise CaptureRejected("SOURCE_REQUIRED_ATTRIBUTES_MISSING")
        if "SANTA" not in str(props.get("NOMBRE_CA") or "").upper() and \
           "SANTA" not in str(props.get("NOMBRE_UH") or "").upper():
            raise CaptureRejected("SOURCE_QUERY_PREDICATE_MISMATCH")
        oid = props["OBJECTID_1"]
        if oid is None or oid in seen_ids:
            raise CaptureRejected("SOURCE_DUPLICATE_OR_MISSING_OBJECTID")
        seen_ids.add(oid)
        xy = positions(geom)
        result.append({
            "objectid": oid,
            "attributes": {key: props[key] for key in FIELDS.split(",")},
            "bbox_epsg4326": [min(p[0] for p in xy), min(p[1] for p in xy),
                             max(p[0] for p in xy), max(p[1] for p in xy)],
            "geometry_type": geom["type"],
        })
    return sorted(result, key=lambda row: str(row["objectid"]))


def make_manifest(count_raw: bytes, geojson_raw: bytes, count_meta: dict, geojson_meta: dict) -> dict:
    n = validate_count(count_raw)
    rows = validate_features(geojson_raw, n)
    return {
        "schema_version": "0.1",
        **SAFE,
        "status": "CAPTURED_CURRENT_CONTEXT_ONLY_NOT_HISTORICAL_AXIS",
        "source": {"institution": "ANA", "service_layer": LAYER,
                   "count_query": count_meta, "geojson_query": geojson_meta,
                   "where": WHERE, "out_fields": FIELDS, "out_sr": 4326},
        "capture": {"count": n, "candidates": rows,
                    "raw_count_sha256": sha256(count_raw),
                    "raw_geojson_sha256": sha256(geojson_raw)},
        "scientific_role": LABEL,
        "historical_2011_axis_equivalence": False,
        "historical_2011_datum_adjudicated": False,
        "native_2011_axis_transformed": False,
        "floodplain_or_hydraulic_model_inferred": False,
        "map_publication_enabled": False,
        "operational_promotions": 0,
        "candidate_selection_is_hydrologic_identity": False,
    }


def capture(out_dir: Path) -> None:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise CaptureRejected("FROZEN_OUTPUT_EXISTS_NO_OVERWRITE")
    count_url, feature_url = urls()
    try:
        count_raw, count_meta = fetch_once(count_url)
        geojson_raw, geojson_meta = fetch_once(feature_url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(json.dumps({"status": "SOURCE_ACCESS_UNAVAILABLE",
                          "meaning": "UNKNOWN_NOT_LOW_RISK",
                          "error_type": type(exc).__name__}), file=sys.stderr)
        return
    manifest = make_manifest(count_raw, geojson_raw, count_meta, geojson_meta)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir) as stage:
        staged = Path(stage)
        (staged / "count.raw.json").write_bytes(count_raw)
        (staged / "candidates.raw.geojson").write_bytes(geojson_raw)
        (staged / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        for name in ("count.raw.json", "candidates.raw.geojson", "manifest.json"):
            os.replace(staged / name, out_dir / name)
    print(json.dumps({"status": manifest["status"], "count": manifest["capture"]["count"],
                      "sha256": manifest["capture"]["raw_geojson_sha256"]}))


class TestSantaCurrentANACapture(unittest.TestCase):
    """Synthetic-only tests; these coordinates are not real-world source geometry."""

    def fixture(self):
        feature = {"type": "Feature", "properties": {
            "OBJECTID_1": 123, "CODIGO_CA": "synthetic", "NOMBRE_CA": "Santa synthetic",
            "TIPO_CA": None, "NOMBRE_UH": "Santa synthetic",
            "CODIGO_UH": "synthetic", "LONG_KM": None,
        }, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
        return json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()

    def test_query_and_guards(self):
        a, b = urls()
        self.assertIn("returnCountOnly=true", a)
        self.assertIn("outSR=4326", b)
        self.assertIn("f=geojson", b)
        self.assertEqual(SAFE["activation_gate"], "BLOCKED")
        self.assertIsNone(SAFE["decision_thresholds"])
        self.assertIsNone(SAFE["hydraulic_factors"])

    def test_synthetic_capture_is_context_only(self):
        raw = self.fixture()
        manifest = make_manifest(b'{"count":1}', raw, {}, {})
        self.assertEqual(manifest["capture"]["raw_geojson_sha256"], sha256(raw))
        self.assertEqual(manifest["capture"]["count"], 1)
        self.assertFalse(manifest["map_publication_enabled"])
        self.assertFalse(manifest["historical_2011_axis_equivalence"])
        self.assertFalse(manifest["candidate_selection_is_hydrologic_identity"])
        self.assertEqual(manifest["activation_gate"], "BLOCKED")

    def test_fail_closed_on_count_mismatch(self):
        with self.assertRaisesRegex(CaptureRejected, "COUNT_MISMATCH"):
            validate_features(self.fixture(), 2)

    def test_fail_closed_on_empty_or_bad_source(self):
        for count in (b'{"count":0}', b'{"error":{"message":"failed"}}',
                      b'{"count":true}', b'{"count":-1}'):
            with self.subTest(count=count), self.assertRaises(CaptureRejected):
                validate_count(count)

    def test_fail_closed_on_crs_and_invalid_geometry(self):
        doc = json.loads(self.fixture())
        doc["crs"] = {"type": "name", "properties": {"name": "EPSG:32717"}}
        with self.assertRaisesRegex(CaptureRejected, "UNEXPECTED_CRS"):
            validate_features(json.dumps(doc).encode(), 1)
        del doc["crs"]
        doc["features"][0]["geometry"]["coordinates"] = [[0, 0], [float("nan"), 1]]
        with self.assertRaisesRegex(CaptureRejected, "NONFINITE"):
            validate_features(json.dumps(doc).encode(), 1)

    def test_fail_closed_on_transfer_limit(self):
        doc = json.loads(self.fixture())
        doc["exceededTransferLimit"] = True
        with self.assertRaisesRegex(CaptureRejected, "TRANSFER_LIMIT"):
            validate_features(json.dumps(doc).encode(), 1)


if __name__ == "__main__":
    if "--capture" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--capture", action="store_true")
        parser.add_argument("--out-dir", required=True, type=Path)
        args = parser.parse_args()
        try:
            capture(args.out_dir)
        except CaptureRejected as exc:
            print(json.dumps({"status": "SOURCE_QA_REJECTED",
                              "reason": str(exc), "meaning": "UNKNOWN_NOT_LOW_RISK"}),
                  file=sys.stderr)
            sys.exit(1)
    else:
        unittest.main()
