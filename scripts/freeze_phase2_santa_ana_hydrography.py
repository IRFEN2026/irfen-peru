#!/usr/bin/env python3
"""Archive exact ANA Santa-name hydrography response, research context only.

Name-search matches do not establish Santa identity or ANA 2011 equivalence.
Run --self-test offline; live acquisition requires public ANA access.
"""
import argparse
import hashlib
import json
import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
PARAMS = {"where": WHERE, "outFields": FIELDS, "returnGeometry": "true", "outSR": "4326", "f": "geojson"}
URL = LAYER + "/query?" + urlencode(PARAMS)
MAX_BYTES = 8_000_000
GUARDS = {"deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
          "production_use": False, "production_ready": False,
          "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
          "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "decision_thresholds": None,
          "hydraulic_factors": None, "map_publication_enabled": False}


class RejectRedirects(HTTPRedirectHandler):
    """Do not attribute redirected bytes to the declared ANA source."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def positions(geometry):
    typ = geometry.get("type")
    coords = geometry.get("coordinates")
    if typ == "LineString":
        lines = [coords]
    elif typ == "MultiLineString":
        lines = coords
    else:
        raise ValueError("non-polyline candidate")
    if not isinstance(lines, list) or not lines:
        raise ValueError("empty lines")
    result = []
    for line in lines:
        if not isinstance(line, list) or len(line) < 2:
            raise ValueError("short line")
        for pos in line:
            if not isinstance(pos, list) or len(pos) < 2:
                raise ValueError("invalid position")
            lon, lat = pos[:2]
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                   for x in (lon, lat)) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("invalid WGS84 position")
            result.append((lon, lat))
    return result


def inspect(raw):
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("error") or obj.get("exceededTransferLimit"):
        raise ValueError("ArcGIS error or truncated result")
    features = obj.get("features")
    if obj.get("type") != "FeatureCollection" or not isinstance(features, list) or not features:
        raise ValueError("missing nonempty GeoJSON FeatureCollection")
    rows = []
    for feature in features:
        if feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict):
            raise ValueError("malformed feature")
        points = positions(feature.get("geometry") or {})
        xs, ys = zip(*points)
        p = feature["properties"]
        # Recheck the server-side WHERE locally. A wrong/stale service response
        # must not be archived as a Santa-name match or as negative evidence.
        if not any(isinstance(p.get(field), str) and "santa" in p[field].casefold()
                   for field in ("NOMBRE_CA", "NOMBRE_UH")):
            raise ValueError("ANA candidate does not satisfy the declared Santa-name query")
        rows.append({"objectid": p.get("OBJECTID_1"), "codigo_ca": p.get("CODIGO_CA"),
                     "nombre_ca": p.get("NOMBRE_CA"), "tipo_ca": p.get("TIPO_CA"),
                     "nombre_uh": p.get("NOMBRE_UH"), "codigo_uh": p.get("CODIGO_UH"),
                     "long_km": p.get("LONG_KM"), "geometry_type": feature["geometry"]["type"],
                     "bbox_wgs84": [min(xs), min(ys), max(xs), max(ys)]})
    return rows


def freeze(raw, acquired_at):
    rows = inspect(raw)
    return {"schema_version": "0.1", "source": "ANA ONRH/Rios_Quebradas_AAVI MapServer/0",
            "source_url": URL, "retrieved_at_utc": acquired_at,
            "source_redirect_policy": "REJECT_ALL_HTTP_REDIRECTS",
            "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_response_bytes": len(raw), "candidate_count": len(rows),
            "candidates": rows, "scientific_role": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_CANDIDATES_ONLY",
            "identity_adjudicated": False, "2011_axis_equivalence": False,
            "2011_datum_resolved": False, "geometry_map_published": False,
            "completeness_claim": "NONE; name query is not exhaustive hydrographic identification",
            **GUARDS}


class OfflineTests(unittest.TestCase):
    def test_freeze_and_guards(self):
        # Synthetic software fixture, not Santa coordinates or evidence.
        raw = json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"NOMBRE_CA": "synthetic Santa"},
             "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
        ]}).encode()
        doc = freeze(raw, "TEST_ONLY")
        self.assertEqual(doc["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(doc["candidate_count"], 1)
        self.assertFalse(doc["production_use"])
        self.assertIsNone(doc["decision_thresholds"])
        self.assertFalse(doc["identity_adjudicated"])
        self.assertEqual(doc["source_redirect_policy"], "REJECT_ALL_HTTP_REDIRECTS")

    def test_rejects_nonmatching_or_unverifiable_name(self):
        # Synthetic software fixture: never an observation or geographic claim.
        for props in ({"NOMBRE_CA": "Río distinto"}, {"NOMBRE_UH": None},
                      {"NOMBRE_CA": 123}, {}):
            with self.subTest(props=props), self.assertRaises(ValueError):
                inspect(json.dumps({"type": "FeatureCollection", "features": [
                    {"type": "Feature", "properties": props,
                     "geometry": {"type": "LineString",
                                  "coordinates": [[0, 0], [1, 1]]}}
                ]}).encode())

    def test_redirect_is_rejected_offline(self):
        # Synthetic redirect, not an assertion about the ANA service.
        target = "https://example.invalid/not-the-ana-source"
        self.assertIsNone(RejectRedirects().redirect_request(
            Request(URL), None, 302, "Found", {"Location": target}, target))

    def test_rejects_unusable_responses(self):
        for obj in ({"error": {"code": 500}},
                    {"type": "FeatureCollection", "features": []},
                    {"type": "FeatureCollection", "exceededTransferLimit": True,
                     "features": [{"type": "Feature"}]}):
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                inspect(json.dumps(obj).encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--out-dir", default="data/phase2/source_archive/santa_ana_hydrography_probe")
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(OfflineTests)
        return 0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1
    request = Request(URL, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
                                    "Accept": "application/geo+json,application/json"})
    try:
        with build_opener(RejectRedirects()).open(request, timeout=90) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("response exceeds 8MB archive cap")
        manifest = freeze(raw, datetime.now(timezone.utc).isoformat())
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"UNKNOWN/SOURCE_ACCESS_UNAVAILABLE_OR_INVALID: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    root = Path(args.out_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "santa_ana_hydrography_raw.geojson").write_bytes(raw)
    (root / "santa_ana_hydrography_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SANTA_ANA_HYDROGRAPHY_SHA256=" + manifest["raw_response_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
