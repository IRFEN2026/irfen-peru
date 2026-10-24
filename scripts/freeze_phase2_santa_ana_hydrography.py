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
# Alternative third-party-hosted copies of ANA-attributed 2018 hydrography.
# Similar attribution/schema is NOT evidence of identical bytes, version or lineage.
# Sources observed from public ArcGIS REST layer metadata on 2026-10-23.
SOURCES = {
    "ana_official": {
        "layer": LAYER, "oid_field": "OBJECTID_1",
        "custody": "ANA_OFFICIAL_SERVICE",
        "metadata_url": LAYER,
    },
    "arcgis_copy_2025": {
        "layer": "https://services.arcgis.com/evjBQsNzjm2hdraL/ArcGIS/rest/services/Rios/FeatureServer/0",
        "oid_field": "OBJECTID_1",
        "custody": "THIRD_PARTY_HOSTED_ANA_ATTRIBUTED_COPY_UNVERIFIED",
        "metadata_url": "https://services.arcgis.com/evjBQsNzjm2hdraL/ArcGIS/rest/services/Rios/FeatureServer/0",
    },
    "arcgis_copy_2026": {
        "layer": "https://services1.arcgis.com/RTK5Unh1Z71JKIiR/ArcGIS/rest/services/R%C3%ADos/FeatureServer/2",
        "oid_field": "FID",
        "custody": "THIRD_PARTY_HOSTED_ANA_ATTRIBUTED_COPY_UNVERIFIED",
        "metadata_url": "https://services1.arcgis.com/RTK5Unh1Z71JKIiR/ArcGIS/rest/services/R%C3%ADos/FeatureServer/2",
    },
}


def source_url(source_key):
    source = SOURCES[source_key]
    params = dict(PARAMS)
    params["outFields"] = FIELDS.replace("OBJECTID_1", source["oid_field"], 1)
    return source["layer"] + "/query?" + urlencode(params)


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


def capture_http_provenance(response, requested_url):
    """Reject non-200 or silently changed endpoints before freezing any bytes."""
    status = getattr(response, "status", None)
    final_url = response.geturl()
    if status != 200 or final_url != requested_url:
        raise ValueError("HTTP status or final URL differs from requested source")
    return {
        "requested_url": requested_url,
        "final_url": final_url,
        "http_status": status,
        "content_type": response.headers.get("Content-Type"),
        "http_date": response.headers.get("Date"),
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
    }


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


def inspect(raw, source_key="ana_official"):
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("error") or obj.get("exceededTransferLimit"):
        raise ValueError("ArcGIS error or truncated result")
    # RFC 7946 defaults to WGS84 lon/lat. An explicit conflicting legacy CRS
    # overrides that assumption and must not be archived as EPSG:4326.
    if "crs" in obj:
        crs = obj["crs"]
        allowed = {"EPSG:4326", "OGC:CRS84", "urn:ogc:def:crs:OGC::CRS84"}
        if not (isinstance(crs, dict) and crs.get("type") == "name"
                and isinstance(crs.get("properties"), dict)
                and crs["properties"].get("name") in allowed):
            raise ValueError("explicit GeoJSON CRS is not adjudicated WGS84 lon/lat")
    features = obj.get("features")
    if isinstance(features, list) and len(features) >= 2000:
        raise ValueError("candidate count reaches ArcGIS maxRecordCount; pagination not adjudicated")
    if obj.get("type") != "FeatureCollection" or not isinstance(features, list) or not features:
        raise ValueError("missing nonempty GeoJSON FeatureCollection")
    rows = []
    seen_objectids = set()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict):
            raise ValueError("malformed feature")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError("malformed geometry")
        points = positions(geometry)
        xs, ys = zip(*points)
        p = feature["properties"]
        # Recheck the server-side WHERE locally. A wrong/stale service response
        # must not be archived as a Santa-name match or as negative evidence.
        if not any(isinstance(p.get(field), str) and "santa" in p[field].casefold()
                   for field in ("NOMBRE_CA", "NOMBRE_UH")):
            raise ValueError("ANA candidate does not satisfy the declared Santa-name query")
        oid = p.get(SOURCES[source_key]["oid_field"])
        # Stable per-source object IDs are necessary to trace a captured candidate.
        # Missing, invalid or duplicate IDs mean UNKNOWN, never an adjudicated line.
        if isinstance(oid, bool) or not isinstance(oid, int) or oid < 0 or oid in seen_objectids:
            raise ValueError("missing, invalid or duplicate source object ID")
        seen_objectids.add(oid)
        rows.append({"objectid": oid, "codigo_ca": p.get("CODIGO_CA"),
                     "nombre_ca": p.get("NOMBRE_CA"), "tipo_ca": p.get("TIPO_CA"),
                     "nombre_uh": p.get("NOMBRE_UH"), "codigo_uh": p.get("CODIGO_UH"),
                     "long_km": p.get("LONG_KM"), "geometry_type": geometry["type"],
                     "bbox_wgs84": [min(xs), min(ys), max(xs), max(ys)]})
    return rows


def freeze(raw, acquired_at, source_key="ana_official", http_provenance=None):
    rows = inspect(raw, source_key)
    source = SOURCES[source_key]
    return {"schema_version": "0.2", "source": source_key,
            "source_url": source_url(source_key), "source_metadata_url": source["metadata_url"],
            "source_custody": source["custody"],
            "official_ana_byte_equivalence_established": False,
            "source_metadata_observed_utc_date": "2026-10-23",
            "retrieved_at_utc": acquired_at,
            "http_provenance": http_provenance,
            "http_provenance_verified": http_provenance is not None,
            "source_redirect_policy": "REJECT_ALL_HTTP_REDIRECTS",
            "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_response_bytes": len(raw), "candidate_count": len(rows),
            "candidates": rows, "scientific_role": ("CURRENT_ANA_HYDROGRAPHY_CONTEXT_CANDIDATES_ONLY"
                                if source_key == "ana_official" else
                                "THIRD_PARTY_ANA_ATTRIBUTED_HYDROGRAPHY_UNVERIFIED_CANDIDATES_ONLY"),
            "identity_adjudicated": False, "2011_axis_equivalence": False,
            "2011_datum_resolved": False, "geometry_map_published": False,
            "completeness_claim": "NONE; name query is not exhaustive hydrographic identification",
            **GUARDS}


class OfflineTests(unittest.TestCase):
    def test_freeze_and_guards(self):
        # Synthetic software fixture, not Santa coordinates or evidence.
        raw = json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"NOMBRE_CA": "synthetic Santa", "OBJECTID_1": 1},
             "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
        ]}).encode()
        doc = freeze(raw, "TEST_ONLY")
        self.assertEqual(doc["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(doc["candidate_count"], 1)
        self.assertFalse(doc["production_use"])
        self.assertIsNone(doc["http_provenance"])
        self.assertFalse(doc["http_provenance_verified"])
        self.assertIsNone(doc["decision_thresholds"])
        self.assertEqual(doc["scientific_role"], "CURRENT_ANA_HYDROGRAPHY_CONTEXT_CANDIDATES_ONLY")
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

    def test_rejects_malformed_feature_and_geometry_fail_closed(self):
        # Synthetic fixtures only: malformed ANA responses are UNKNOWN, never evidence.
        malformed = [None, [], "not-a-feature",
                     {"type": "Feature", "properties": {"NOMBRE_CA": "synthetic Santa"},
                      "geometry": []},
                     {"type": "Feature", "properties": {"NOMBRE_CA": "synthetic Santa"},
                      "geometry": "LineString"},
                     {"type": "Feature", "properties": {"NOMBRE_CA": "synthetic Santa"},
                      "geometry": {"type": "MultiLineString", "coordinates": None}}]
        for candidate in malformed:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                inspect(json.dumps({"type": "FeatureCollection",
                                    "features": [candidate]}).encode())

    def test_http_source_provenance_is_exact_and_fail_closed(self):
        # Synthetic HTTP response: no claim that ANA or a mirror was reachable.
        from types import SimpleNamespace
        requested = source_url("ana_official")
        good = SimpleNamespace(status=200, geturl=lambda: requested,
                               headers={"Content-Type": "application/geo+json",
                                        "Date": "synthetic-test-date"})
        evidence = capture_http_provenance(good, requested)
        self.assertEqual(evidence["http_status"], 200)
        self.assertEqual(evidence["requested_url"], evidence["final_url"])
        self.assertEqual(evidence["content_type"], "application/geo+json")
        for status, final in ((206, requested), (200, "https://example.invalid/redirect")):
            bad = SimpleNamespace(status=status, geturl=lambda final=final: final,
                                  headers={})
            with self.subTest(status=status, final=final), self.assertRaises(ValueError):
                capture_http_provenance(bad, requested)

    def test_redirect_is_rejected_offline(self):
        # Synthetic redirect, not an assertion about the ANA service.
        target = "https://example.invalid/not-the-ana-source"
        self.assertIsNone(RejectRedirects().redirect_request(
            Request(URL), None, 302, "Found", {"Location": target}, target))

    def test_mirror_custody_and_source_specific_oid_fail_closed(self):
        raw = json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"NOMBRE_CA": "synthetic Santa", "FID": 42},
             "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
        ]}).encode()
        doc = freeze(raw, "TEST_ONLY", "arcgis_copy_2026")
        self.assertEqual(doc["candidates"][0]["objectid"], 42)
        self.assertIn("FID", doc["source_url"])
        self.assertEqual(doc["source_custody"], "THIRD_PARTY_HOSTED_ANA_ATTRIBUTED_COPY_UNVERIFIED")
        self.assertEqual(doc["scientific_role"],
                         "THIRD_PARTY_ANA_ATTRIBUTED_HYDROGRAPHY_UNVERIFIED_CANDIDATES_ONLY")
        self.assertFalse(doc["official_ana_byte_equivalence_established"])
        self.assertFalse(doc["identity_adjudicated"])
        self.assertFalse(doc["2011_axis_equivalence"])
        self.assertFalse(doc["geometry_map_published"])
        self.assertEqual(doc["activation_gate"], "BLOCKED")
        self.assertIsNone(doc["hydraulic_factors"])

    def test_source_object_ids_are_required_and_unique(self):
        # Synthetic software fixtures only, never Santa hydrographic evidence.
        def feature(oid):
            return {"type": "Feature",
                    "properties": {"NOMBRE_CA": "synthetic Santa", "OBJECTID_1": oid},
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
        for ids in ([None], [True], [-1], [1, 1], ["1"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                inspect(json.dumps({"type": "FeatureCollection",
                                    "features": [feature(oid) for oid in ids]}).encode())
        self.assertEqual(len(inspect(json.dumps({"type": "FeatureCollection",
                                                "features": [feature(1), feature(2)]}).encode())), 2)

    def test_explicit_geojson_crs_must_be_wgs84_lonlat(self):
        # Synthetic metadata fixtures only, not observed ANA geometry.
        obj = {"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {"NOMBRE_CA": "synthetic Santa", "OBJECTID_1": 1},
             "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
        ]}
        for crs in (None, {"type": "name", "properties": {"name": "EPSG:3857"}},
                    {"type": "name", "properties": {"name": "EPSG:32717"}},
                    {"type": "link", "properties": {"href": "unknown"}}):
            with self.subTest(crs=crs), self.assertRaises(ValueError):
                inspect(json.dumps({**obj, "crs": crs}).encode())
        for name in ("EPSG:4326", "OGC:CRS84", "urn:ogc:def:crs:OGC::CRS84"):
            with self.subTest(name=name):
                self.assertEqual(len(inspect(json.dumps({**obj, "crs": {
                    "type": "name", "properties": {"name": name}}}).encode())), 1)

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
    parser.add_argument("--source", choices=sorted(SOURCES), default="ana_official",
                        help="Explicit source selection; mirrors are unverified copies, not ANA official service")
    parser.add_argument("--out-dir", default="data/phase2/source_archive/santa_ana_hydrography_probe")
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(OfflineTests)
        return 0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1
    request = Request(source_url(args.source), headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
                                    "Accept": "application/geo+json,application/json"})
    try:
        with build_opener(RejectRedirects()).open(request, timeout=90) as response:
            provenance = capture_http_provenance(response, source_url(args.source))
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("response exceeds 8MB archive cap")
        manifest = freeze(raw, datetime.now(timezone.utc).isoformat(), args.source,
                          http_provenance=provenance)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"UNKNOWN/SOURCE_ACCESS_UNAVAILABLE_OR_INVALID: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    root = Path(args.out_dir) / args.source
    root.mkdir(parents=True, exist_ok=True)
    (root / "santa_ana_hydrography_raw.geojson").write_bytes(raw)
    (root / "santa_ana_hydrography_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SANTA_HYDROGRAPHY_CANDIDATE_SHA256=" + manifest["raw_response_sha256"])
    print("SOURCE_CUSTODY=" + manifest["source_custody"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
