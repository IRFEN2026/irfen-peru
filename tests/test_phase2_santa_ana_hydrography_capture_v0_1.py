"""Fail-closed ANA Santa CURRENT hydrography capture + offline regression tests.

Manual capture (never run as a routine CI test):
python tests/test_phase2_santa_ana_hydrography_capture_v0_1.py --capture --output /tmp/santa-ana-20261007

This is NOT the 2011 HEC-RAS axis, inundation extent, or hydraulic model.
No geometries are generated: the raw HTTP responses are retained byte-for-byte.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%'"
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
MAX_RESPONSE_BYTES = 20_000_000  # Transport safety limit, NOT a scientific threshold.


class SourceUnavailable(Exception):
    pass


def query_url(**params):
    return LAYER + "/query?" + urlencode(params)


def raw_sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def get_raw(url):
    req = Request(url, headers={
        "User-Agent": "IRFEN-Santa-research-capture/0.1",
        "Accept": "application/json,application/geo+json",
    })
    try:
        with urlopen(req, timeout=45) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailable(type(exc).__name__) from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SourceUnavailable("RESPONSE_EXCEEDS_TRANSPORT_LIMIT")
    return raw


def json_object(raw):
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict) or "error" in obj:
        raise ValueError("source response is not a valid object / ArcGIS error")
    return obj


def positions(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("invalid GeoJSON coordinate nesting")
    if len(value) >= 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value[:2]):
        x, y = float(value[0]), float(value[1])
        if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
            raise ValueError("coordinate outside EPSG:4326 numeric domain")
        yield x, y
    else:
        for child in value:
            yield from positions(child)


def feature_summary(feature, objectid):
    if feature.get("type") != "Feature":
        raise ValueError("not a GeoJSON feature")
    props = feature.get("properties")
    if not isinstance(props, dict) or str(props.get("OBJECTID_1")) != str(objectid):
        raise ValueError("OBJECTID mismatch; do not adjudicate")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in ("LineString", "MultiLineString"):
        raise ValueError("not a current ANA polyline")
    coords = list(positions(geometry.get("coordinates")))
    if not coords:
        raise ValueError("empty polyline")
    xs, ys = zip(*coords)
    return {
        "objectid": objectid,
        "attributes": {key: props.get(key) for key in FIELDS.split(",")},
        "geometry_type": geometry["type"],
        "bbox_epsg4326": [min(xs), min(ys), max(xs), max(ys)],
        "coordinate_position_count": len(coords),
        "identity_adjudicated": False,
        "historical_2011_axis_equivalence": False,
        "map_publication_authorized": False,
    }


def capture(output, getter=get_raw):
    """Collect all raw responses before writing an immutable snapshot directory."""
    metadata_url = LAYER + "?f=pjson"
    ids_url = query_url(where=WHERE, returnIdsOnly="true", f="json")
    metadata_raw = getter(metadata_url)
    metadata = json_object(metadata_raw)
    if metadata.get("id") != 0 or metadata.get("geometryType") != "esriGeometryPolyline":
        raise ValueError("unexpected layer identity/type")
    if not any(f.get("name") == "OBJECTID_1" for f in metadata.get("fields", [])):
        raise ValueError("required source OBJECTID field missing")
    ids_raw = getter(ids_url)
    ids_doc = json_object(ids_raw)
    raw_ids = ids_doc.get("objectIds")
    if not isinstance(raw_ids, list):
        raise ValueError("missing objectIds; cannot interpret as zero candidates")
    if any(not isinstance(i, int) or isinstance(i, bool) for i in raw_ids):
        raise ValueError("invalid objectId")
    ids = sorted(set(raw_ids))
    files = {"layer_metadata.pjson": metadata_raw, "candidate_ids.json": ids_raw}
    rows = []
    for objectid in ids:
        url = query_url(
            where="1=1", objectIds=str(objectid), outFields=FIELDS,
            returnGeometry="true", outSR="4326", f="geojson",
        )
        raw = getter(url)
        doc = json_object(raw)
        features = doc.get("features")
        if doc.get("type") != "FeatureCollection" or not isinstance(features, list) or len(features) != 1:
            raise ValueError("one-feature-per-OBJECTID invariant failed")
        row = feature_summary(features[0], objectid)
        path = "objects/" + str(objectid) + ".geojson"
        row.update({"query_url": url, "raw_path": path, "raw_sha256": raw_sha256(raw)})
        rows.append(row)
        files[path] = raw
    manifest = {
        "schema_version": "0.1",
        **SAFE,
        "source_institution": "Autoridad Nacional del Agua (ANA)",
        "source_layer": LAYER,
        "source_layer_year_from_metadata": 2018,
        "representation": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_CANDIDATES_ONLY",
        "status": "CANDIDATES_ONLY_NOT_ADJUDICATED" if rows else "NO_CANDIDATE_RETURNED_NOT_NEGATIVE",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata_url": metadata_url,
        "metadata_raw_sha256": raw_sha256(metadata_raw),
        "candidate_ids_url": ids_url,
        "candidate_ids_raw_sha256": raw_sha256(ids_raw),
        "candidate_count": len(rows),
        "candidates": rows,
        "historical_2011_datum_established": False,
        "historical_2011_geometry_equivalence": False,
        "geometry_map_publishable": False,
        "notes": "Lexical candidates only. May include homonyms or multiple river segments; manual source and location adjudication required. Not an ANA 2011 model/axis/floodplain. No empty result is negative risk evidence.",
    }
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output = Path(output)
    if output.exists():
        raise FileExistsError("use a new empty destination; snapshots are immutable")
    output.mkdir(parents=True)
    for name, raw in files.items():
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as handle:
            handle.write(raw)
    return manifest


class TestSantaANASourceCapture(unittest.TestCase):
    def test_guardrails_are_fail_closed(self):
        self.assertEqual(SAFE["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(SAFE["test_mode"], "TEST_ONLY")
        self.assertFalse(SAFE["production_use"])
        self.assertFalse(SAFE["production_ready"])
        self.assertFalse(SAFE["operational_alerting_enabled"])
        self.assertEqual(SAFE["activation_gate"], "BLOCKED")
        self.assertEqual(SAFE["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(SAFE["decision_thresholds"])
        self.assertIsNone(SAFE["hydraulic_factors"])

    def test_query_is_lexical_and_does_not_assume_identity(self):
        url = query_url(where=WHERE, returnIdsOnly="true", f="json")
        self.assertIn("NOMBRE_CA", url)
        self.assertIn("returnIdsOnly=true", url)
        self.assertNotIn("NOMBRE_UH", url)
        self.assertEqual(len(raw_sha256(b"test")), 64)

    def test_bbox_derived_only_from_actual_line(self):
        f = {"type": "Feature", "properties": {"OBJECTID_1": 7, "NOMBRE_CA": "Santa"},
             "geometry": {"type": "MultiLineString", "coordinates": [
                 [[-78.0, -9.0], [-77.5, -8.8]], [[-77.5, -8.8], [-77.0, -8.6]]
             ]}}
        s = feature_summary(f, 7)
        self.assertEqual(s["bbox_epsg4326"], [-78.0, -9.0, -77.0, -8.6])
        self.assertFalse(s["identity_adjudicated"])
        self.assertFalse(s["historical_2011_axis_equivalence"])
        self.assertFalse(s["map_publication_authorized"])

    def test_invalid_and_mismatched_geometry_fail_closed(self):
        f = {"type": "Feature", "properties": {"OBJECTID_1": 9},
             "geometry": {"type": "LineString", "coordinates": [[200, -9], [201, -8]]}}
        with self.assertRaises(ValueError):
            feature_summary(f, 9)
        f["geometry"]["coordinates"] = [[-78, -9], [-77, -8]]
        with self.assertRaises(ValueError):
            feature_summary(f, 10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--output")
    args, unittest_args = parser.parse_known_args()
    if args.capture:
        if not args.output:
            parser.error("--output is required with --capture")
        try:
            result = capture(args.output)
            print(json.dumps({"status": result["status"], "candidate_count": result["candidate_count"],
                              "manifest": str(Path(args.output) / "manifest.json")}, sort_keys=True))
        except SourceUnavailable as exc:
            print(json.dumps({**SAFE, "status": "SOURCE_ACCESS_UNAVAILABLE",
                              "source_layer": LAYER, "error_type": str(exc),
                              "negative_evidence": False}, sort_keys=True))
            raise SystemExit(2)
    else:
        unittest.main(argv=[__file__] + unittest_args)
