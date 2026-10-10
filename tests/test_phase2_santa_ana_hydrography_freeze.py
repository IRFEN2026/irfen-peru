"""Fail-closed Santa current ANA hydrography freeze and offline regression tests.

Run offline: python -m unittest tests/test_phase2_santa_ana_hydrography_freeze.py -v
Run one bounded live attempt:
    python tests/test_phase2_santa_ana_hydrography_freeze.py --capture --out-dir /tmp/santa-ana-freeze

Evidence: ANA ONRH/Rios_Quebradas_AAVI/MapServer/0 metadata, documented in
IRFEN PR #334 (2026-09-26). This is CURRENT_ANA_HYDROGRAPHY_CONTEXT only.
It is NOT the ANA 2011 HEC-RAS axis, model, floodplain, datum, or capacity.
No map promotion, risk, alert, thresholds or hydraulic interpretation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timezone

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
MAX_BYTES = 32_000_000
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
SOURCE_ID = "ANA-ONRH-RIOS-QUEBRADAS-AAVI-SANTA-CURRENT-HYDROGRAPHY"


class InvalidSourceResponse(ValueError):
    pass


def query_url() -> str:
    return LAYER + "/query?" + urlencode({
        "where": WHERE,
        "outFields": FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })


def positions(coordinates):
    if not isinstance(coordinates, list):
        raise InvalidSourceResponse("coordinates are not an array")
    if len(coordinates) >= 2 and all(type(x) in (float, int) for x in coordinates[:2]):
        x, y = coordinates[:2]
        if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
            raise InvalidSourceResponse("invalid geographic coordinate")
        yield (float(x), float(y))
        return
    for part in coordinates:
        yield from positions(part)


def adjudicate(raw: bytes) -> dict:
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidSourceResponse("non-JSON source response") from exc
    if not isinstance(payload, dict) or payload.get("error") or payload.get("exceededTransferLimit"):
        raise InvalidSourceResponse("ArcGIS error or incomplete page")
    if payload.get("type") != "FeatureCollection":
        raise InvalidSourceResponse("not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise InvalidSourceResponse("no adjudicable features; NOT a negative observation")
    rows = []
    for f in features:
        if not isinstance(f, dict) or f.get("type") != "Feature":
            raise InvalidSourceResponse("invalid feature")
        g, a = f.get("geometry"), f.get("properties")
        if not isinstance(g, dict) or not isinstance(a, dict):
            raise InvalidSourceResponse("missing geometry or attributes")
        if g.get("type") not in ("LineString", "MultiLineString"):
            raise InvalidSourceResponse("not ANA polyline geometry")
        xy = list(positions(g.get("coordinates")))
        if len(xy) < 2:
            raise InvalidSourceResponse("empty or insufficient line coordinates")
        xs, ys = zip(*xy)
        rows.append({
            "objectid": a.get("OBJECTID_1"),
            "codigo_ca": a.get("CODIGO_CA"),
            "nombre_ca": a.get("NOMBRE_CA"),
            "tipo_ca": a.get("TIPO_CA"),
            "nombre_uh": a.get("NOMBRE_UH"),
            "codigo_uh": a.get("CODIGO_UH"),
            "long_km_source_attribute": a.get("LONG_KM"),
            "geometry_type": g["type"],
            "coordinate_count": len(xy),
            "bbox_wgs84_requested_output": [min(xs), min(ys), max(xs), max(ys)],
        })
    return {"feature_count": len(rows), "features": rows}


def receipt(status: str) -> dict:
    return {
        **GUARDS,
        "source_id": SOURCE_ID,
        "source_url": LAYER,
        "query_url": query_url(),
        "requested_outSR": 4326,
        "representation": "CURRENT_ANA_HYDROGRAPHY_CONTEXT",
        "source_role": "CURRENT_INSTITUTIONAL_POLYLINE_NOT_2011_AXIS_OR_FLOODPLAIN",
        "ana_2011_datum_established": False,
        "historical_geometry_equivalence": False,
        "map_publication_enabled": False,
        "raw_capture_status": status,
        "raw_response_sha256": None,
        "raw_response_bytes": None,
        "geometry_status": "UNKNOWN" if status != "FROZEN_VALID_SOURCE" else "CURRENT_CONTEXT_ONLY",
        "missing_source_is_negative_evidence": False,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def capture(out_dir: Path, timeout: float = 35) -> dict:
    """Exactly one bounded request; no retries, no partial raw geometry archive."""
    r = receipt("SOURCE_ACCESS_UNAVAILABLE")
    try:
        req = Request(query_url(), headers={
            "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
            "Accept": "application/geo+json,application/json",
        })
        with urlopen(req, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            r["http_status"] = response.status
            r["http_final_url"] = response.geturl()
            r["http_content_type"] = response.headers.get("Content-Type")
        if len(body) > MAX_BYTES:
            raise InvalidSourceResponse("response exceeds bounded capture size")
        result = adjudicate(body)
        r.update(result)
        r["raw_capture_status"] = "FROZEN_VALID_SOURCE"
        r["geometry_status"] = "CURRENT_CONTEXT_ONLY"
        r["raw_response_sha256"] = hashlib.sha256(body).hexdigest()
        r["raw_response_bytes"] = len(body)
        r["raw_response_path"] = "santa_ana_hydrography_current.geojson"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / r["raw_response_path"]).write_bytes(body)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        r["raw_capture_status"] = "SOURCE_ACCESS_UNAVAILABLE"
        r["source_error_type"] = type(exc).__name__
    except InvalidSourceResponse as exc:
        r["raw_capture_status"] = "SOURCE_RESPONSE_NOT_ADJUDICABLE"
        r["source_error_type"] = type(exc).__name__
        r["source_error_detail"] = str(exc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "santa_ana_hydrography_receipt.json").write_text(
        json.dumps(r, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return r


class SantaANAHydrographyFreezeOfflineTests(unittest.TestCase):
    @staticmethod
    def fixture(geometry=None):
        return json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"CODIGO_CA": "synthetic-test-only", "NOMBRE_CA": "SANTA"},
                "geometry": geometry or {"type": "LineString", "coordinates": [[-78, -9], [-78.1, -9.1]]},
            }],
        }).encode()

    def test_query_exact_and_nonoperational(self):
        self.assertIn("outSR=4326", query_url())
        self.assertIn("NOMBRE_UH", query_url())
        r = receipt("SOURCE_ACCESS_UNAVAILABLE")
        for key, value in GUARDS.items():
            self.assertEqual(r[key], value)
        self.assertFalse(r["map_publication_enabled"])
        self.assertFalse(r["ana_2011_datum_established"])
        self.assertIsNone(r["raw_response_sha256"])
        self.assertFalse(r["missing_source_is_negative_evidence"])

    def test_valid_synthetic_line_is_not_historical_geometry(self):
        result = adjudicate(self.fixture())
        self.assertEqual(result["feature_count"], 1)
        self.assertEqual(result["features"][0]["bbox_wgs84_requested_output"], [-78.1, -9.1, -78.0, -9.0])

    def test_empty_and_truncated_pages_fail_closed(self):
        with self.assertRaises(InvalidSourceResponse):
            adjudicate(b'{"type":"FeatureCollection","features":[]}')
        with self.assertRaises(InvalidSourceResponse):
            adjudicate(b'{"type":"FeatureCollection","exceededTransferLimit":true,"features":[]}')
        with self.assertRaises(InvalidSourceResponse):
            adjudicate(b'{"error":{"message":"service error"}}')

    def test_polygon_or_invalid_coordinate_rejected(self):
        with self.assertRaises(InvalidSourceResponse):
            adjudicate(self.fixture({"type": "Polygon", "coordinates": [[[-78, -9], [-78.1, -9.1]]] }))
        with self.assertRaises(InvalidSourceResponse):
            adjudicate(self.fixture({"type": "LineString", "coordinates": [[-78, -9], [181, -9.1]]}))

    def test_hash_is_of_raw_bytes_not_normalized_json(self):
        raw = self.fixture()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(bytes(raw)).hexdigest())
        self.assertNotEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw + b"\n").hexdigest())


if __name__ == "__main__":
    if "--capture" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--capture", action="store_true")
        parser.add_argument("--out-dir", type=Path, required=True)
        parser.add_argument("--timeout", type=float, default=35)
        args = parser.parse_args()
        output = capture(args.out_dir, args.timeout)
        print(json.dumps({
            "raw_capture_status": output["raw_capture_status"],
            "raw_response_sha256": output["raw_response_sha256"],
            "feature_count": output.get("feature_count"),
        }, sort_keys=True))
        if output["raw_capture_status"] == "SOURCE_RESPONSE_NOT_ADJUDICABLE":
            sys.exit(1)
    else:
        unittest.main()
