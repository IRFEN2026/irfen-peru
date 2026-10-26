#!/usr/bin/env python3
"""Archive exact ANA Santa-name hydrography response, research context only.

Name-search matches do not establish Santa identity or ANA 2011 equivalence.
Run --self-test offline; live acquisition requires public ANA access.
"""
import argparse
import zipfile
from collections import Counter
from tempfile import TemporaryDirectory
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
    # A valid JSON scalar/array is not an ArcGIS GeoJSON response. Preserve
    # UNKNOWN rather than raising an unclassified AttributeError in live CI.
    if not isinstance(obj, dict):
        raise ValueError("GeoJSON root is not an object")
    if obj.get("error") or obj.get("exceededTransferLimit"):
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


# Immutable GitHub Actions artifact checksum (run 40236836542, artifact 12615331858).
# The artifact expires 2026-11-24; this verifier does not make it permanent.
# These bytes are third-party mirrors, never original ANA hydrography or 2011 axis.
ARTIFACT_ZIP_SHA256_20261025 = "6560c170dcf2919706df8db946745fddce5f2a277310bdef8d0fbe10cabda1c2"
ARTIFACT_MEMBERS_20261025 = {
    "ana_official/receipt.json",
    "arcgis_copy_2025/santa_ana_hydrography_raw.geojson",
    "arcgis_copy_2025/santa_ana_hydrography_manifest.json",
    "arcgis_copy_2026/santa_ana_hydrography_raw.geojson",
    "arcgis_copy_2026/santa_ana_hydrography_manifest.json",
}



def recompute_mirror_pair_qa(features_2025, features_2026):
    """Recompute descriptive mirror deltas from archived bytes, not from the ledger.

    This is NOT a geometry-equivalence or length-unit gate. The 1e-8 diagnostic
    is inherited verbatim from the frozen 2026-10-25 ledger; it authorizes no
    coordinate snapping, area tolerance, map layer or 2011-axis equivalence.
    """
    from statistics import median

    def keyed(features):
        by_key = {}
        for feature in features:
            p = feature["properties"]
            key = (p.get("CODIGO_CA"), p.get("NOMBRE_CA"))
            if not all(isinstance(value, str) and value for value in key):
                raise ValueError("mirror code/name missing")
            by_key.setdefault(key, []).append(feature)
        return by_key

    a, b = keyed(features_2025), keyed(features_2026)
    counts_a = Counter({key: len(rows) for key, rows in a.items()})
    counts_b = Counter({key: len(rows) for key, rows in b.items()})
    if counts_a != counts_b:
        raise ValueError("mirror code/name multiset differs")
    unique = [key for key in a if len(a[key]) == len(b[key]) == 1]
    deltas, ratios = [], []
    equal_vertices = equal_coordinates = below_existing_diagnostic = 0
    for key in unique:
        fa, fb = a[key][0], b[key][0]
        pa, pb = positions(fa["geometry"]), positions(fb["geometry"])
        if len(pa) != len(pb):
            continue  # reported mismatch, never silently aligned or interpolated
        equal_vertices += 1
        delta = max(abs(v - w) for va, vb in zip(pa, pb) for v, w in zip(va, vb))
        deltas.append((key, delta, fa, fb))
        equal_coordinates += delta == 0
        below_existing_diagnostic += delta < 1e-8
        la, lb = fa["properties"].get("LONG_KM"), fb["properties"].get("LONG_KM")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or
               not math.isfinite(x) or x <= 0 for x in (la, lb)):
            raise ValueError("mirror LONG_KM not comparable; units unadjudicated")
        ratios.append(la / lb)
    if len(deltas) != len(unique) or len(deltas) < 2:
        raise ValueError("cannot reproduce mirror vertex/length comparison")
    deltas.sort(key=lambda row: row[1], reverse=True)
    largest_key, largest_delta, largest_a, largest_b = deltas[0]
    other_basin = all(
        feature["properties"].get("NOMBRE_UH") != "Cuenca Santa"
        for feature in (largest_a, largest_b))
    return {
        "features_each": len(features_2025),
        "unique_code_name_keys": len(a),
        "unambiguous_one_to_one_keys": len(unique),
        "ambiguous_duplicate_keys": [
            {"codigo_ca": key[0], "nombre_ca": key[1], "count_each": len(a[key])}
            for key in a if len(a[key]) > 1],
        "nombre_ca_rio_santa_features_each": sum(
            row["properties"].get("NOMBRE_CA") == "Río Santa" for row in features_2025),
        "nombre_uh_cuenca_santa_features_each": sum(
            row["properties"].get("NOMBRE_UH") == "Cuenca Santa" for row in features_2025),
        "rio_santa_codes": sorted({
            row["properties"].get("CODIGO_CA") for row in features_2025
            if row["properties"].get("NOMBRE_CA") == "Río Santa"}),
        "unambiguous_pairs_with_same_vertex_count": equal_vertices,
        "unambiguous_pairs_exact_coordinate_equality": equal_coordinates,
        "unambiguous_pairs_with_max_absolute_coordinate_delta_below_1e_minus_8_degrees":
            below_existing_diagnostic,
        "large_coordinate_disagreement": {
            "codigo_ca": largest_key[0], "nombre_ca": largest_key[1],
            "max_absolute_coordinate_delta_degrees": largest_delta,
            "other_basin_not_santa_axis": other_basin},
        "other_31_pairs_max_absolute_coordinate_delta_degrees": deltas[1][1],
        "raw_LONG_KM_ratio_2025_over_2026_unique_pairs": {
            "minimum": min(ratios), "median": median(ratios), "maximum": max(ratios)},
    }


def replay_oct25_artifact_zip(archive_path):
    """Independently replay the exact time-limited capture ZIP; never promote a map."""
    path = Path(archive_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != ARTIFACT_ZIP_SHA256_20261025:
        raise ValueError("GitHub artifact ZIP SHA-256 mismatch")
    ledger_path = (Path(__file__).resolve().parents[1] /
                   "site/data/phase2/source_assessments/" /
                   "santa_20261025_mirror_hydrography_replay_v0_1.json")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger["source_capture"]["github_artifact_id"] != 12615331858:
        raise ValueError("artifact provenance mismatch")
    by_source = {item["source"]: item for item in ledger["sources"]}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(ARTIFACT_MEMBERS_20261025) or set(names) != ARTIFACT_MEMBERS_20261025:
            raise ValueError("unexpected, missing or duplicate archive member")
        receipt = json.loads(archive.read("ana_official/receipt.json"))
        official = by_source["ana_official"]
        if (receipt.get("source") != "ana_official" or
                receipt.get("source_custody") != "ANA_OFFICIAL_SERVICE" or
                receipt.get("capture_status") != "UNKNOWN_SOURCE_ACCESS_UNAVAILABLE_OR_INVALID" or
                receipt.get("raw_response_sha256") is not None or
                receipt.get("candidate_count") is not None or
                official.get("absence_claim") is not False):
            raise ValueError("official ANA unavailability misrepresented")
        for key, expected in GUARDS.items():
            if receipt.get(key) != expected:
                raise ValueError("official ANA receipt guard changed: " + key)
        identity_multisets = {}
        raw_features = {}
        for source_key in ("arcgis_copy_2025", "arcgis_copy_2026"):
            source = by_source[source_key]
            raw = archive.read(source_key + "/santa_ana_hydrography_raw.geojson")
            manifest_bytes = archive.read(source_key + "/santa_ana_hydrography_manifest.json")
            manifest = json.loads(manifest_bytes)
            if (len(raw) != source["raw_response_bytes"] or
                    hashlib.sha256(raw).hexdigest() != source["raw_response_sha256"] or
                    hashlib.sha256(manifest_bytes).hexdigest() != source["manifest_sha256"]):
                raise ValueError("mirror bytes or SHA-256 mismatch: " + source_key)
            if (manifest.get("source") != source_key or
                    manifest.get("source_url") != source_url(source_key) or
                    manifest.get("source_custody") != "THIRD_PARTY_HOSTED_ANA_ATTRIBUTED_COPY_UNVERIFIED" or
                    manifest.get("candidate_count") != source["candidate_count"] or
                    manifest.get("raw_response_sha256") != source["raw_response_sha256"] or
                    manifest.get("raw_response_bytes") != len(raw) or
                    manifest.get("http_provenance_verified") is not True):
                raise ValueError("mirror manifest provenance mismatch: " + source_key)
            for key, expected in GUARDS.items():
                if manifest.get(key) != expected:
                    raise ValueError("mirror guard changed: " + source_key + ":" + key)
            for key in ("official_ana_byte_equivalence_established", "identity_adjudicated",
                        "2011_axis_equivalence", "2011_datum_resolved", "geometry_map_published"):
                if manifest.get(key) is not False:
                    raise ValueError("unsupported mirror promotion: " + source_key + ":" + key)
            rows = inspect(raw, source_key)
            if rows != manifest.get("candidates") or len(rows) != source["candidate_count"]:
                raise ValueError("mirror feature parsing no longer reproducible: " + source_key)
            features = json.loads(raw)["features"]
            raw_features[source_key] = features
            identity_multisets[source_key] = Counter(
                (feature["properties"].get("CODIGO_CA"), feature["properties"].get("NOMBRE_CA"))
                for feature in features)
        if identity_multisets["arcgis_copy_2025"] != identity_multisets["arcgis_copy_2026"]:
            raise ValueError("mirror code/name multisets disagree")
        measured = recompute_mirror_pair_qa(
            raw_features["arcgis_copy_2025"], raw_features["arcgis_copy_2026"])
        recorded = ledger["replay_qa"]
        for field, observed in measured.items():
            expected = recorded.get(field)
            if field == "ambiguous_duplicate_keys":
                observed = sorted(observed, key=lambda x: (x["codigo_ca"], x["nombre_ca"]))
                expected = sorted(expected, key=lambda x: (x["codigo_ca"], x["nombre_ca"]))
            if observed != expected:
                raise ValueError("frozen mirror QA not reproducible: " + field)
        if (recorded.get("mirror_geometry_equivalence_established") is not False or
                recorded.get("mirror_length_attribute_equivalence_established") is not False or
                recorded.get("river_2011_axis_equivalence_established") is not False or
                recorded.get("length_units_adjudicated") is not False):
            raise ValueError("unjustified mirror equivalence promotion")
    return {"artifact_zip_sha256": ARTIFACT_ZIP_SHA256_20261025,
            "mirror_candidate_count_each": by_source["arcgis_copy_2025"]["candidate_count"],
            "official_ana": "UNKNOWN_SOURCE_ACCESS_UNAVAILABLE_OR_INVALID",
            "third_party_mirrors_not_equivalent_to_ana": True,
            "historical_santa_2011_datum_resolved": False,
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

    def test_nonobject_json_is_fail_closed_unknown(self):
        # Syntactically valid but structurally invalid source responses must
        # be classified as UNKNOWN, never as missing Santa features.
        for raw in (b"null", b"[]", b"123", b'"not-geojson"'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                inspect(raw)

    def test_oct25_mirror_replay_provenance_remains_fail_closed(self):
        # Regression contract for the documented 2026-10-25 GitHub artifact.
        # This tests the provenance ledger, NOT the unavailable original ANA
        # bytes or the time-limited mirror GeoJSON; no geometry is promoted.
        ledger_path = (Path(__file__).resolve().parents[1] /
                       "site/data/phase2/source_assessments/"
                       "santa_20261025_mirror_hydrography_replay_v0_1.json")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        capture = ledger["source_capture"]
        self.assertEqual(capture["github_run_id"], 40236836542)
        self.assertFalse(capture["archive_is_permanent"])
        self.assertEqual(capture["artifact_retention_days"], 30)
        sources = {row["source"]: row for row in ledger["sources"]}
        self.assertEqual(set(sources), set(SOURCES))
        official = sources["ana_official"]
        self.assertEqual(official["custody"], "ANA_OFFICIAL_SERVICE")
        self.assertEqual(official["capture_status"],
                         "UNKNOWN_SOURCE_ACCESS_UNAVAILABLE_OR_INVALID")
        self.assertIsNone(official["raw_sha256"])
        self.assertIsNone(official["candidate_count"])
        self.assertFalse(official["absence_claim"])
        for key in ("arcgis_copy_2025", "arcgis_copy_2026"):
            with self.subTest(source=key):
                row = sources[key]
                self.assertEqual(row["source_url"], SOURCES[key]["layer"])
                self.assertEqual(row["custody"],
                                 "THIRD_PARTY_HOSTED_ANA_ATTRIBUTED_COPY_UNVERIFIED")
                self.assertEqual(row["capture_status"], "CAPTURED_UNVERIFIED_MIRROR")
                self.assertEqual(row["candidate_count"], 36)
                self.assertEqual(len(row["raw_response_sha256"]), 64)
                self.assertEqual(len(row["manifest_sha256"]), 64)
        replay = ledger["replay_qa"]
        self.assertFalse(replay["mirror_geometry_equivalence_established"])
        self.assertFalse(replay["mirror_length_attribute_equivalence_established"])
        self.assertFalse(replay["river_2011_axis_equivalence_established"])
        self.assertFalse(replay["query_completeness_established"])
        self.assertFalse(replay["length_units_adjudicated"])
        for key, expected in GUARDS.items():
            self.assertEqual(ledger[key], expected, key)
        self.mirror_pair_recomputation_synthetic_check()
        for key in ("official_ana_byte_equivalence_established",
                    "historical_santa_2011_datum_resolved",
                    "geometry_map_published", "identity_adjudicated"):
            self.assertIs(ledger[key], False, key)

    def mirror_pair_recomputation_synthetic_check(self):
        # Synthetic fixtures only; no claimed ANA geometry, thresholds or units.
        def feature(code, length, last_lat):
            return {"type": "Feature",
                    "properties": {"CODIGO_CA": code, "NOMBRE_CA": "Río Santa",
                                   "NOMBRE_UH": "Cuenca Santa", "LONG_KM": length},
                    "geometry": {"type": "LineString",
                                 "coordinates": [[0, 0], [1, last_lat]]}}
        a = [feature("synthetic-A", 1000, 1), feature("synthetic-B", 2000, 1)]
        b = [feature("synthetic-A", 1, 1), feature("synthetic-B", 2, 1.1)]
        qa = recompute_mirror_pair_qa(a, b)
        self.assertEqual(qa["unambiguous_pairs_with_same_vertex_count"], 2)
        self.assertEqual(qa["unambiguous_pairs_exact_coordinate_equality"], 1)
        self.assertEqual(qa["raw_LONG_KM_ratio_2025_over_2026_unique_pairs"]["median"], 1000)
        self.assertFalse(qa["large_coordinate_disagreement"]["other_basin_not_santa_axis"])
        with self.assertRaisesRegex(ValueError, "multiset differs"):
            recompute_mirror_pair_qa(a, b[:1])

    def test_oct25_artifact_zip_digest_mismatch_is_fail_closed(self):
        # Synthetic invalid bytes: this test never claims source absence.
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.zip"
            path.write_bytes(b"not the captured artifact")
            with self.assertRaisesRegex(ValueError, "ZIP SHA-256 mismatch"):
                replay_oct25_artifact_zip(path)

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
    parser.add_argument("--verify-artifact-zip", metavar="PATH",
                        help="Replay the pinned 2026-10-25 research-only ZIP without network")
    parser.add_argument("--source", choices=sorted(SOURCES), default="ana_official",
                        help="Explicit source selection; mirrors are unverified copies, not ANA official service")
    parser.add_argument("--out-dir", default="data/phase2/source_archive/santa_ana_hydrography_probe")
    args = parser.parse_args()
    if args.verify_artifact_zip:
        print(json.dumps(replay_oct25_artifact_zip(args.verify_artifact_zip), sort_keys=True))
        return 0
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
