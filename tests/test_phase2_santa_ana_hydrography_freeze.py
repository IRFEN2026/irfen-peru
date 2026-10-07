"""Fail-closed source-byte capture for CURRENT ANA Santa hydrography only.

Run offline: python -m unittest tests.test_phase2_santa_ana_hydrography_freeze
Manual source capture: python tests/test_phase2_santa_ana_hydrography_freeze.py --capture /tmp/santa-ana-candidates
Unittest discovery never makes live requests. No 2011-axis/model/map equivalence.
"""
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
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
    "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
}
MAX_RESPONSE_BYTES = 8_000_000


class SourceUnavailable(Exception):
    """Temporary source failure, never a negative observation."""


class SourceInvalid(Exception):
    """Incomplete or inconsistent source response."""


def make_url(**params):
    return LAYER + "/query?" + urlencode(params)


def get_raw(url):
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
                                "Accept": "application/json,application/geo+json"})
    try:
        with urlopen(req, timeout=90) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SourceInvalid("RESPONSE_EXCEEDS_CAPTURE_BYTE_CAP")
            return raw
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailable("SOURCE_ACCESS_UNAVAILABLE:" + type(exc).__name__) from exc


def decode(raw):
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceInvalid("NON_JSON_SOURCE_RESPONSE") from exc
    if not isinstance(data, dict) or "error" in data:
        raise SourceInvalid("ARCGIS_ERROR_OR_INVALID_RESPONSE")
    if data.get("exceededTransferLimit"):
        raise SourceInvalid("EXCEEDED_TRANSFER_LIMIT")
    return data


def read_ids(raw):
    data = decode(raw)
    field, ids = data.get("objectIdFieldName"), data.get("objectIds")
    if field != "OBJECTID_1" or not isinstance(ids, list) or not ids:
        raise SourceInvalid("OBJECT_ID_DISCOVERY_MISSING_OR_UNEXPECTED")
    if any(type(x) is not int or x < 0 for x in ids) or len(set(ids)) != len(ids):
        raise SourceInvalid("OBJECT_ID_DUPLICATE_OR_INVALID")
    return sorted(ids)


def positions(coordinates):
    if not isinstance(coordinates, list) or not coordinates:
        raise SourceInvalid("EMPTY_COORDINATES")
    if len(coordinates) >= 2 and all(type(v) in (int, float) for v in coordinates[:2]):
        x, y = coordinates[:2]
        if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
            raise SourceInvalid("INVALID_EPSG4326_POSITION")
        yield (x, y)
    else:
        for child in coordinates:
            yield from positions(child)


def validate_feature(raw, expected_id):
    data = decode(raw)
    features = data.get("features")
    if data.get("type") != "FeatureCollection" or not isinstance(features, list) or len(features) != 1:
        raise SourceInvalid("NOT_EXACTLY_ONE_GEOJSON_FEATURE")
    feature = features[0]
    if feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict):
        raise SourceInvalid("INVALID_FEATURE_PROPERTIES")
    props = feature["properties"]
    if props.get("OBJECTID_1", feature.get("id")) != expected_id:
        raise SourceInvalid("OBJECT_ID_MISMATCH")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in ("LineString", "MultiLineString"):
        raise SourceInvalid("NOT_A_HYDROGRAPHY_LINE")
    pts = list(positions(geometry.get("coordinates")))
    if len(pts) < 2:
        raise SourceInvalid("TOO_FEW_POSITIONS")
    keys = ("CODIGO_CA", "NOMBRE_CA", "TIPO_CA", "NOMBRE_UH", "CODIGO_UH", "LONG_KM")
    for key in keys:
        if key not in props:
            raise SourceInvalid("MISSING_ATTRIBUTE:" + key)
    return {"objectid": expected_id, "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_count": len(raw), "geometry_type": geometry["type"],
            "bbox_epsg4326": [min(p[0] for p in pts), min(p[1] for p in pts),
                              max(p[0] for p in pts), max(p[1] for p in pts)],
            "attributes": {key: props[key] for key in keys}}


def collect(fetch=get_raw):
    ids_url = make_url(where=WHERE, returnIdsOnly="true", f="json")
    ids_raw = fetch(ids_url)
    ids = read_ids(ids_raw)
    count_url = make_url(where=WHERE, returnCountOnly="true", f="json")
    count_raw = fetch(count_url)
    count = decode(count_raw).get("count")
    if type(count) is not int or count != len(ids):
        raise SourceInvalid("SOURCE_COUNT_AND_IDS_DISAGREE")
    records = []
    blobs = [("ids.json", ids_raw), ("count.json", count_raw)]
    for oid in ids:
        url = make_url(objectIds=str(oid), outFields=FIELDS, returnGeometry="true",
                       outSR="4326", f="geojson")
        raw = fetch(url)
        record = validate_feature(raw, oid)
        record["source_url"] = url
        records.append(record)
        blobs.append((str(oid) + ".geojson", raw))
    manifest = {
        "schema_version": "0.1", "source_layer": LAYER,
        "source_kind": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_ONLY",
        "historical_2011_axis_equivalence": False, "map_publication_authorized": False,
        "query_where": WHERE, "id_query_url": ids_url,
        "id_query_sha256": hashlib.sha256(ids_raw).hexdigest(),
        "count_query_url": count_url,
        "count_query_sha256": hashlib.sha256(count_raw).hexdigest(),
        "candidate_count": count, "records": records, "guards": GUARDS,
        "capture_limit": "Broad name-based candidates, not adjudicated Santa 2011 centerline.",
    }
    return manifest, blobs


def freeze(destination, fetch=get_raw):
    """Stage complete source responses before any persistent write."""
    manifest, blobs = collect(fetch)
    target = Path(destination)
    if target.exists():
        raise SourceInvalid("DESTINATION_EXISTS_NO_OVERWRITE")
    if not target.parent.is_dir():
        raise SourceInvalid("DESTINATION_PARENT_MISSING")
    with tempfile.TemporaryDirectory(prefix="santa-ana-stage-", dir=target.parent) as temp:
        stage = Path(temp)
        for name, raw in blobs:
            (stage / name).write_bytes(raw)
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")
        names = sorted(p.name for p in stage.iterdir())
        (stage / "SHA256SUMS").write_text("".join(
            hashlib.sha256((stage / name).read_bytes()).hexdigest() + "  " + name + "\n"
            for name in names), encoding="utf-8")
        os.rename(stage, target)
    return manifest


class OfflineContracts(unittest.TestCase):
    def test_guardrails(self):
        self.assertEqual(GUARDS["activation_gate"], "BLOCKED")
        self.assertEqual(GUARDS["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(GUARDS["decision_thresholds"])
        self.assertIsNone(GUARDS["hydraulic_factors"])
        self.assertFalse(any(GUARDS[x] for x in
                             ("production_use", "production_ready", "operational_alerting_enabled")))

    def test_id_inventory_is_exact(self):
        self.assertEqual(read_ids(b'{"objectIdFieldName":"OBJECTID_1","objectIds":[9,2]}'), [2, 9])
        for bad in (b'{"objectIdFieldName":"OBJECTID_1","objectIds":[2,2]}',
                    b'{"objectIdFieldName":"OBJECTID","objectIds":[2]}',
                    b'{"error":{"code":500}}'):
            with self.assertRaises(SourceInvalid):
                read_ids(bad)

    def test_incomplete_capture_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "frozen"
            def fetch(url):
                if "returnIdsOnly" in url:
                    return b'{"objectIdFieldName":"OBJECTID_1","objectIds":[5]}'
                return b'{"count":2}'
            with self.assertRaisesRegex(SourceInvalid, "COUNT_AND_IDS"):
                freeze(dest, fetch)
            self.assertFalse(dest.exists())

    def test_geojson_identity_and_geometry_fail_closed(self):
        base = {"type": "FeatureCollection", "features": [{"type": "Feature", "id": 5,
                "properties": {k: None for k in
                    ("CODIGO_CA", "NOMBRE_CA", "TIPO_CA", "NOMBRE_UH", "CODIGO_UH", "LONG_KM")},
                "geometry": {"type": "LineString",
                             "coordinates": [[-78, -9], [-78.1, -9.1]]}}]}
        raw = json.dumps(base).encode()
        self.assertEqual(validate_feature(raw, 5)["bbox_epsg4326"], [-78.1, -9.1, -78, -9])
        with self.assertRaisesRegex(SourceInvalid, "OBJECT_ID_MISMATCH"):
            validate_feature(raw, 6)
        base["features"][0]["geometry"]["type"] = "Polygon"
        with self.assertRaisesRegex(SourceInvalid, "NOT_A_HYDROGRAPHY_LINE"):
            validate_feature(json.dumps(base).encode(), 5)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--capture":
        try:
            result = freeze(sys.argv[2])
        except (SourceUnavailable, SourceInvalid) as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        print("CURRENT_ANA_HYDROGRAPHY_CONTEXT_ONLY candidates:", result["candidate_count"])
    else:
        unittest.main()
