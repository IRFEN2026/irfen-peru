"""Santa ANA current hydrography: bounded raw capture, never Santa 2011 geometry.

Run offline regression tests:
    python -m unittest tests/test_phase2_santa_ana_hydrography_freeze.py -v
Run an explicitly requested source capture:
    python tests/test_phase2_santa_ana_hydrography_freeze.py --capture --out-dir /tmp/santa-ana

No live network calls occur during test discovery. The candidate query does not
adjudicate a 2011 axis, floodplain, hydraulic model, or map layer.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timezone

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
MAX_BYTES = 20_000_000
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
    "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "decision_thresholds": None,
    "hydraulic_factors": None, "map_publication": False,
    "historical_geometry_equivalence_to_2011_axis": False,
    "datum_2011": None,
}


class SourceUnavailable(Exception):
    """Source cannot be read: not evidence of absence or low risk."""


class SourceUnadjudicated(Exception):
    """A response was received but cannot safely be frozen as a full candidate set."""


def query_url():
    params = {
        "where": WHERE, "outFields": FIELDS, "returnGeometry": "true",
        "outSR": "4326", "f": "geojson", "orderByFields": "OBJECTID_1 ASC",
    }
    return LAYER + "/query?" + urlencode(params)


def coordinates(value):
    if not isinstance(value, (list, tuple)):
        raise SourceUnadjudicated("Invalid geometry coordinates")
    if len(value) >= 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value[:2]):
        x, y = float(value[0]), float(value[1])
        if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
            raise SourceUnadjudicated("Non-finite or non-geographic EPSG:4326 coordinates")
        yield x, y
    else:
        for child in value:
            yield from coordinates(child)


def adjudicate(raw):
    """Validate only a CURRENT_ANA_HYDROGRAPHY_CONTEXT candidate response."""
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise SourceUnadjudicated("Non-JSON response") from exc
    if not isinstance(doc, dict) or "error" in doc or doc.get("exceededTransferLimit"):
        raise SourceUnadjudicated("ArcGIS error or potentially truncated response")
    features = doc.get("features")
    if not isinstance(features, list) or not features:
        raise SourceUnadjudicated("No adjudicable candidate features; UNKNOWN, not negative")
    if len(features) > 2000:
        raise SourceUnadjudicated("Unexpectedly large candidate set; pagination QA required")
    seen = set()
    rows = []
    for feature in features:
        if not isinstance(feature, dict):
            raise SourceUnadjudicated("Malformed feature")
        geom = feature.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString"):
            raise SourceUnadjudicated("Geometry is not a line")
        points = list(coordinates(geom.get("coordinates")))
        if len(points) < 2:
            raise SourceUnadjudicated("Incomplete line geometry")
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise SourceUnadjudicated("Missing attributes")
        obj = props.get("OBJECTID_1")
        if obj is None or obj in seen:
            raise SourceUnadjudicated("Missing or duplicate OBJECTID_1")
        seen.add(obj)
        if not (props.get("NOMBRE_CA") or props.get("NOMBRE_UH")):
            raise SourceUnadjudicated("Missing river/unit name")
        xs, ys = zip(*points)
        rows.append({
            "objectid_1": obj, "codigo_ca": props.get("CODIGO_CA"),
            "nombre_ca": props.get("NOMBRE_CA"), "tipo_ca": props.get("TIPO_CA"),
            "nombre_uh": props.get("NOMBRE_UH"), "codigo_uh": props.get("CODIGO_UH"),
            "long_km_source_attribute": props.get("LONG_KM"),
            "geometry_type": geom["type"],
            "bbox_epsg4326": [min(xs), min(ys), max(xs), max(ys)],
            "positions": len(points),
        })
    return rows


def fetch_raw(url, timeout=60):
    request = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1", "Accept": "application/geo+json,application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            headers = {k: response.headers.get(k) for k in ("Content-Type", "ETag", "Last-Modified", "Date")}
            status = response.status
            final_url = response.geturl()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailable(f"SOURCE_ACCESS_UNAVAILABLE: {type(exc).__name__}") from exc
    if status != 200 or len(raw) > MAX_BYTES:
        raise SourceUnadjudicated("HTTP non-200 or response exceeds size limit")
    return raw, {"http_status": status, "headers": headers, "final_url": final_url}


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(content)
        name = temp.name
    os.replace(name, path)


def capture(out_dir):
    url = query_url()
    raw, http = fetch_raw(url)
    rows = adjudicate(raw)
    receipt = {
        "assessment_id": "santa_current_ana_hydrography_candidate_capture_v0_1",
        **GUARDS,
        "status": "CURRENT_ANA_HYDROGRAPHY_CANDIDATES_NOT_2011_MODEL",
        "source_institution": "Autoridad Nacional del Agua (ANA)",
        "source_layer": LAYER, "query_url": url,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size_bytes": len(raw), "raw_file": "santa_ana_hydrography_candidates.geojson",
        "http": http, "feature_count": len(rows), "candidates": rows,
        "source_role": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_ONLY",
        "2011_axis_transformation_authorized": False,
        "2011_floodplain_equivalence": False,
        "candidate_name_filter_is_not_identity_adjudication": True,
    }
    out = Path(out_dir)
    atomic_write(out / receipt["raw_file"], raw)
    atomic_write(out / "santa_ana_hydrography_receipt.json", (json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    return receipt


class TestSantaHydrographyFreeze(unittest.TestCase):
    def test_query_is_bounded_to_official_ana_layer(self):
        url = query_url()
        self.assertTrue(url.startswith(LAYER + "/query?"))
        self.assertIn("outSR=4326", url)
        self.assertIn("f=geojson", url)
        self.assertIn("returnGeometry=true", url)

    def test_fail_closed_guards(self):
        self.assertEqual(GUARDS["activation_gate"], "BLOCKED")
        self.assertEqual(GUARDS["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        for key in ("production_use", "production_ready", "operational_alerting_enabled", "map_publication", "historical_geometry_equivalence_to_2011_axis"):
            self.assertIs(GUARDS[key], False)
        for key in ("decision_thresholds", "hydraulic_factors", "datum_2011"):
            self.assertIsNone(GUARDS[key])

    def test_missing_or_error_responses_are_not_negatives(self):
        for body in (b'{}', b'{"features":[]}', b'{"error":{"code":400}}', b'{"features":[],"exceededTransferLimit":true}', b'not-json'):
            with self.subTest(body=body), self.assertRaises(SourceUnadjudicated):
                adjudicate(body)

    def test_no_polygon_or_missing_identity(self):
        for geom in ({"type": "Polygon", "coordinates": []}, {"type": "LineString", "coordinates": []}):
            raw = json.dumps({"features": [{"properties": {"OBJECTID_1": 1, "NOMBRE_CA": "Santa"}, "geometry": geom}]}).encode()
            with self.assertRaises(SourceUnadjudicated):
                adjudicate(raw)

    def test_synthetic_test_line_is_not_2011_model(self):
        # Deliberately synthetic test-only coordinates; never saved or published.
        raw = json.dumps({"features": [{"properties": {"OBJECTID_1": 1, "NOMBRE_CA": "Santa"}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}]}).encode()
        rows = adjudicate(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["positions"], 2)
        self.assertFalse(GUARDS["map_publication"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--out-dir", default=".")
    args, remaining = parser.parse_known_args()
    if args.capture:
        try:
            result = capture(args.out_dir)
            print(json.dumps({"status": result["status"], "sha256": result["raw_sha256"], "feature_count": result["feature_count"]}))
        except (SourceUnavailable, SourceUnadjudicated) as exc:
            print(json.dumps({"status": type(exc).__name__, "reason": str(exc), "missing_data_rule": "UNKNOWN_NOT_LOW_RISK"}))
            raise SystemExit(2)
    else:
        unittest.main(argv=[__file__] + remaining)
