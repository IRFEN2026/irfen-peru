#!/usr/bin/env python3
"""Freeze raw ANA 2018 Santa-name hydrography *candidates*; no 2011 equivalence.

Offline tests: python -m unittest discover -s tests -p test_phase2_santa_ana_hydrography_freeze.py
Live replay (explicit): python tests/test_phase2_santa_ana_hydrography_freeze.py --capture --output /tmp/santa-ana
Zero results and network failures are UNKNOWN, never hydrologic negatives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/phase2_ana_national_hydrography_service_v0_1.json"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
SAFE = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
    "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
}


class CaptureError(RuntimeError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def query(layer, params):
    return layer.rstrip("/") + "/query?" + urlencode(params)


def discovery_url(layer):
    return query(layer, {"where": WHERE, "returnIdsOnly": "true", "f": "json"})


def exact_url(layer, oid):
    if type(oid) is not int or oid < 0:
        raise CaptureError("INVALID_OBJECTID")
    return query(layer, {
        "where": f"OBJECTID_1 = {oid}", "outFields": FIELDS,
        "returnGeometry": "true", "outSR": "4326",
        "returnZ": "false", "returnM": "false", "f": "geojson",
    })


def fetch_raw(url):
    request = Request(url, headers={
        "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
        "Accept": "application/json,application/geo+json",
    })
    try:
        with urlopen(request, timeout=90) as response:
            raw = response.read(12_000_001)
            provenance = {
                "requested_url": url, "final_url": response.geturl(),
                "http_status": getattr(response, "status", None),
                "content_type": response.headers.get("Content-Type"),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CaptureError("SOURCE_ACCESS_UNAVAILABLE:" + type(exc).__name__) from exc
    if not raw or len(raw) > 12_000_000:
        raise CaptureError("SOURCE_EMPTY_OR_TOO_LARGE")
    provenance.update({"raw_sha256": sha(raw), "raw_size_bytes": len(raw)})
    return raw, provenance


def parse(raw):
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CaptureError("SOURCE_INVALID_JSON") from exc
    if not isinstance(doc, dict) or doc.get("error") or doc.get("exceededTransferLimit"):
        raise CaptureError("SOURCE_ERROR_OR_TRANSFER_LIMIT")
    return doc


def ids_from(doc, maximum):
    if doc.get("objectIdFieldName") != "OBJECTID_1":
        raise CaptureError("OBJECTID_FIELD_DRIFT")
    ids = doc.get("objectIds")
    if ids is None:
        raise CaptureError("SOURCE_IDS_UNKNOWN_NOT_NEGATIVE")
    if not isinstance(ids, list) or len(ids) > maximum:
        raise CaptureError("INVALID_OR_UNBOUNDED_CANDIDATES")
    if any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids):
        raise CaptureError("INVALID_OR_DUPLICATE_OBJECTIDS")
    return sorted(ids)


def positions(value):
    if isinstance(value, list):
        if len(value) >= 2 and all(type(v) in (int, float) for v in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from positions(item)


def feature_row(doc, oid):
    features = doc.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise CaptureError("EXACT_FEATURE_COUNT_NOT_ONE")
    feature = features[0]
    props = feature.get("properties")
    geometry = feature.get("geometry")
    if feature.get("type") != "Feature" or not isinstance(props, dict) or props.get("OBJECTID_1") != oid:
        raise CaptureError("EXACT_OBJECTID_MISMATCH")
    if not isinstance(geometry, dict) or geometry.get("type") not in ("LineString", "MultiLineString"):
        raise CaptureError("NOT_OFFICIAL_POLYLINE")
    coords = list(positions(geometry.get("coordinates")))
    if len(coords) < 2 or not all(
        math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90
        for x, y in coords
    ):
        raise CaptureError("INVALID_EPSG4326_COORDINATES")
    return {
        "objectid_1": oid,
        "attributes": {field: props.get(field) for field in FIELDS.split(",")},
        "geometry_type": geometry["type"],
        "bbox_wgs84": [min(x for x, _ in coords), min(y for _, y in coords),
                        max(x for x, _ in coords), max(y for _, y in coords)],
        "status": "UNADJUDICATED_NAME_CANDIDATE_ONLY",
    }


def capture(output, maximum=50):
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    for key in ("deployment_status", "test_mode", "production_use",
                "production_ready", "operational_alerting_enabled", "activation_gate"):
        if config.get(key) != SAFE[key]:
            raise CaptureError("UNSAFE_SOURCE_CONFIG:" + key)
    source = config["source"]
    if source["geometry_type"] != "esriGeometryPolyline" or source["spatial_reference"] != 4326:
        raise CaptureError("SOURCE_METADATA_DRIFT")
    if output.exists():
        raise CaptureError("OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    raw_ids, ids_prov = fetch_raw(discovery_url(source["endpoint"]))
    ids = ids_from(parse(raw_ids), maximum)
    if not ids:
        raise CaptureError("ZERO_NAME_CANDIDATES_UNKNOWN_NOT_ABSENCE")
    rows, raw_features = [], []
    for oid in ids:
        raw, provenance = fetch_raw(exact_url(source["endpoint"], oid))
        row = feature_row(parse(raw), oid)
        row["raw_file"] = f"objectid_{oid}.geojson"
        row["provenance"] = provenance
        rows.append(row)
        raw_features.append((row["raw_file"], raw))
    manifest = {
        "schema_version": "0.1", "source": source,
        "discovery_where": WHERE, "discovery_raw_file": "discovery_ids.json",
        "discovery_provenance": ids_prov, "candidate_count": len(ids),
        "candidates": rows, **SAFE,
        "research_context": "CURRENT_ANA_HYDROGRAPHY_CONTEXT",
        "historical_2011_axis_equivalence": False,
        "historical_2011_datum_adjudicated": False,
        "hydrologic_identity_adjudicated": False,
        "map_publish_enabled": False,
        "interpretation": "Name matches only: not a 2011 model, floodplain, outlet, event, negative, or hydraulic parameter.",
    }
    output.mkdir(parents=True, exist_ok=False)
    for filename, raw, expected in [
        ("discovery_ids.json", raw_ids, ids_prov["raw_sha256"]),
        *[(row["raw_file"], raw, row["provenance"]["raw_sha256"])
          for row, (_, raw) in zip(rows, raw_features)],
    ]:
        path = output / filename
        path.write_bytes(raw)
        if sha(path.read_bytes()) != expected:
            raise CaptureError("ON_DISK_HASH_MISMATCH")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


class TestSantaANAFreezeOffline(unittest.TestCase):
    def test_exact_query(self):
        url = exact_url("https://example.org/MapServer/0", 42)
        self.assertIn("OBJECTID_1+%3D+42", url)
        self.assertIn("outSR=4326", url)
        with self.assertRaises(CaptureError):
            exact_url("https://example.org", True)

    def test_ids_are_not_negatives(self):
        self.assertEqual(ids_from({"objectIdFieldName": "OBJECTID_1", "objectIds": [7, 2]}, 5), [2, 7])
        for doc in (
            {"objectIdFieldName": "OBJECTID_1", "objectIds": None},
            {"objectIdFieldName": "WRONG", "objectIds": [2]},
            {"objectIdFieldName": "OBJECTID_1", "objectIds": [2, 2]},
        ):
            with self.assertRaises(CaptureError):
                ids_from(doc, 5)

    def test_line_candidate_only(self):
        doc = {"features": [{"type": "Feature", "properties": {"OBJECTID_1": 8},
                "geometry": {"type": "LineString",
                             "coordinates": [[-78.5, -9.2], [-78.4, -9.1]]}}]}
        self.assertEqual(feature_row(doc, 8)["status"], "UNADJUDICATED_NAME_CANDIDATE_ONLY")
        with self.assertRaises(CaptureError):
            feature_row(doc, 9)

    def test_source_errors_fail_closed(self):
        for raw in (b'{"error":{"code":500}}', b'{"exceededTransferLimit":true}', b'not json'):
            with self.assertRaises(CaptureError):
                parse(raw)

    def test_freeze_original_bytes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config.json"
            cfg.write_text(json.dumps({
                **{k: SAFE[k] for k in ("deployment_status", "test_mode",
                    "production_use", "production_ready",
                    "operational_alerting_enabled", "activation_gate")},
                "source": {"endpoint": "https://example.org/MapServer/0",
                           "geometry_type": "esriGeometryPolyline", "spatial_reference": 4326},
            }), encoding="utf-8")
            discovery = b'{"objectIdFieldName":"OBJECTID_1","objectIds":[8]}'
            feature = (b'{"features":[{"type":"Feature","properties":{"OBJECTID_1":8},'
                       b'"geometry":{"type":"LineString","coordinates":[[-78.5,-9.2],[-78.4,-9.1]]}}]}')
            def fake_fetch(url):
                raw = discovery if "returnIdsOnly" in url else feature
                return raw, {"requested_url": url, "raw_sha256": sha(raw),
                             "raw_size_bytes": len(raw)}
            with patch.dict(capture.__globals__, {"CONFIG": cfg, "fetch_raw": fake_fetch}):
                doc = capture(root / "archive")
            self.assertEqual((root / "archive" / "discovery_ids.json").read_bytes(), discovery)
            self.assertEqual((root / "archive" / "objectid_8.geojson").read_bytes(), feature)
            self.assertEqual(doc["candidates"][0]["provenance"]["raw_sha256"], sha(feature))
            self.assertFalse(doc["map_publish_enabled"])
            self.assertFalse(doc["historical_2011_datum_adjudicated"])
            self.assertEqual(doc["activation_gate"], "BLOCKED")
            self.assertEqual(doc["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(doc["decision_thresholds"])
            self.assertIsNone(doc["hydraulic_factors"])
            with self.assertRaises(CaptureError):
                with patch.dict(capture.__globals__, {"CONFIG": cfg, "fetch_raw": fake_fetch}):
                    capture(root / "archive")


if __name__ == "__main__":
    if "--capture" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--capture", action="store_true", required=True)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--max-candidates", type=int, default=50)
        args = parser.parse_args()
        if not 1 <= args.max_candidates <= 50:
            parser.error("max-candidates must be 1..50")
        try:
            result = capture(args.output, args.max_candidates)
        except CaptureError as exc:
            print("SANTA_ANA_SOURCE_STATUS=UNKNOWN/" + str(exc), file=sys.stderr)
            sys.exit(2)
        print("SANTA_ANA_MANIFEST_SHA256=" + sha((args.output / "manifest.json").read_bytes()))
        print("SANTA_ANA_UNADJUDICATED_CANDIDATES=" + str(result["candidate_count"]))
    else:
        unittest.main()
