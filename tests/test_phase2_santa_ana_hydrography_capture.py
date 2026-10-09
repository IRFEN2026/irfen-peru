"""Santa: bounded ANA current hydrography capture (NOT the ANA 2011 axis).

Run offline regression: python -m unittest tests/test_phase2_santa_ana_hydrography_capture.py
Run a manual live capture from repo root:
  python tests/test_phase2_santa_ana_hydrography_capture.py --capture --output-dir /tmp/santa-ana-capture

No live access is required for tests. A successful capture only freezes current
ANA candidate centerlines as research context, never a historical floodplain,
2011 datum, hydraulic geometry, threshold, capacity, risk, or alert.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
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


class CaptureError(RuntimeError):
    pass


def fetch_bytes(url: str, max_bytes: int = 10_000_000) -> bytes:
    req = Request(url, headers={"Accept": "application/geo+json,application/json", "User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    try:
        with urlopen(req, timeout=90) as response:
            if getattr(response, "status", 200) != 200:
                raise CaptureError("SOURCE_ACCESS_UNAVAILABLE_HTTP")
            raw = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CaptureError("SOURCE_ACCESS_UNAVAILABLE") from exc
    if not raw or len(raw) > max_bytes:
        raise CaptureError("SOURCE_ACCESS_UNAVAILABLE_EMPTY_OR_OVERSIZED")
    return raw


def query_url(*, ids_only=False, object_id=None) -> str:
    params = {"where": WHERE, "f": "json" if ids_only else "geojson"}
    if ids_only:
        params["returnIdsOnly"] = "true"
        params["returnGeometry"] = "false"
    else:
        params.update({"objectIds": str(object_id), "outFields": FIELDS, "returnGeometry": "true", "outSR": "4326", "returnZ": "false", "returnM": "false"})
    return LAYER + "/query?" + urlencode(params)


def parse_json(raw: bytes) -> dict:
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CaptureError("SOURCE_INVALID_JSON") from exc
    if not isinstance(doc, dict) or doc.get("error") or doc.get("exceededTransferLimit") is True:
        raise CaptureError("SOURCE_ERROR_OR_TRUNCATION")
    return doc


def parse_ids(raw: bytes) -> list[int]:
    doc = parse_json(raw)
    field = doc.get("objectIdFieldName")
    if field != "OBJECTID_1":
        raise CaptureError("SOURCE_OBJECTID_FIELD_DRIFT")
    ids = doc.get("objectIds")
    if not isinstance(ids, list) or not ids or any(type(x) is not int or x < 0 for x in ids):
        raise CaptureError("SOURCE_MISSING_OR_INVALID_OBJECTIDS")
    if len(set(ids)) != len(ids):
        raise CaptureError("SOURCE_DUPLICATE_OBJECTIDS")
    return sorted(ids)


def positions(value):
    if isinstance(value, (tuple, list)):
        if len(value) >= 2 and all(type(x) in (int, float) for x in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from positions(item)


def validate_feature(raw: bytes, expected_id: int) -> dict:
    doc = parse_json(raw)
    features = doc.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise CaptureError("SOURCE_FEATURE_COUNT_DRIFT")
    f = features[0]
    if f.get("type") != "Feature":
        raise CaptureError("SOURCE_NOT_GEOJSON_FEATURE")
    props = f.get("properties")
    geo = f.get("geometry")
    if not isinstance(props, dict) or not isinstance(geo, dict):
        raise CaptureError("SOURCE_MISSING_ATTRIBUTES_OR_GEOMETRY")
    if props.get("OBJECTID_1") != expected_id:
        raise CaptureError("SOURCE_OBJECTID_MISMATCH")
    if geo.get("type") not in ("LineString", "MultiLineString"):
        raise CaptureError("SOURCE_NOT_POLYLINE")
    name_ca = str(props.get("NOMBRE_CA") or "")
    name_uh = str(props.get("NOMBRE_UH") or "")
    if "SANTA" not in name_ca.upper() and "SANTA" not in name_uh.upper():
        raise CaptureError("SOURCE_SANTA_NAME_FILTER_MISMATCH")
    coords = list(positions(geo.get("coordinates")))
    if len(coords) < 2 or any(not(math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90) for x,y in coords):
        raise CaptureError("SOURCE_INVALID_WGS84_COORDINATES")
    return {"objectid": expected_id, "attributes": {key: props.get(key) for key in FIELDS.split(",")}, "geometry_type": geo["type"], "bbox_wgs84": [min(x for x,y in coords), min(y for x,y in coords), max(x for x,y in coords), max(y for x,y in coords)]}


def capture(output_dir: Path, fetch=fetch_bytes) -> dict:
    # A technical resource cap, NOT a scientific or risk threshold.
    raw_ids = fetch(query_url(ids_only=True))
    ids = parse_ids(raw_ids)
    if len(ids) > 10000:
        raise CaptureError("SOURCE_OBJECTID_COUNT_EXCEEDS_TECHNICAL_CAPTURE_CAP")
    staged = [("objectids.json", raw_ids, None, query_url(ids_only=True))]
    for object_id in ids:
        raw = fetch(query_url(object_id=object_id))
        row = validate_feature(raw, object_id)
        staged.append((f"objectid_{object_id}.geojson", raw, row, query_url(object_id=object_id)))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CaptureError("OUTPUT_DIRECTORY_NOT_EMPTY")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for filename, raw, row, url in staged:
        (output_dir / filename).write_bytes(raw)
        rows.append({"file": filename, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "requested_url": url, "candidate": row})
    manifest = {
        "source": LAYER, "source_metadata_url": LAYER + "?f=pjson", "query": WHERE,
        "retrieved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_status": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_ONLY",
        "raw_capture": rows, "candidate_count": len(ids), "guards": GUARDS,
        "historical_2011_datum_resolved": False,
        "historical_2011_geometry_equivalence_established": False,
        "map_publication_authorized": False,
        "hydraulic_geometry_recovered": False,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


class OfflineCaptureTests(unittest.TestCase):
    @staticmethod
    def ids(ids=(3, 2)):
        return json.dumps({"objectIdFieldName": "OBJECTID_1", "objectIds": list(ids)}).encode()

    @staticmethod
    def feature(object_id, name="RIO SANTA", geom=None):
        if geom is None:
            geom = {"type": "LineString", "coordinates": [[-78.7, -8.8], [-78.6, -8.9]]}
        return json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"OBJECTID_1": object_id, "NOMBRE_CA": name, "CODIGO_CA": "X", "NOMBRE_UH": "SANTA"}, "geometry": geom}]}).encode()

    def test_deterministic_raw_hashes_and_research_guards(self):
        responses = {query_url(ids_only=True): self.ids(), query_url(object_id=2): self.feature(2), query_url(object_id=3): self.feature(3)}
        with tempfile.TemporaryDirectory() as d:
            m = capture(Path(d) / "raw", lambda u: responses[u])
            self.assertEqual(m["candidate_count"], 2)
            self.assertEqual([x["file"] for x in m["raw_capture"]], ["objectids.json", "objectid_2.geojson", "objectid_3.geojson"])
            for row in m["raw_capture"]:
                self.assertEqual(row["sha256"], hashlib.sha256((Path(d)/"raw"/row["file"]).read_bytes()).hexdigest())
            self.assertFalse(m["map_publication_authorized"])
            self.assertFalse(m["historical_2011_datum_resolved"])
            self.assertEqual(m["guards"], GUARDS)

    def test_fail_closed_on_truncation_duplicate_ids_and_mismatch(self):
        for raw in (self.ids((1,1)), b'{"error":{"code":400}}', b'{"objectIdFieldName":"OID","objectIds":[1]}', b'{"objectIdFieldName":"OBJECTID_1","objectIds":[]}'):
            with self.assertRaises(CaptureError):
                parse_ids(raw)
        with self.assertRaises(CaptureError):
            validate_feature(self.feature(3), 4)
        with self.assertRaises(CaptureError):
            validate_feature(self.feature(3, geom={"type":"Polygon","coordinates":[]} ), 3)
        with self.assertRaises(CaptureError):
            validate_feature(self.feature(3, geom={"type":"LineString","coordinates":[[float('nan'), 0],[-78, -9]]}), 3)

    def test_no_partial_capture_on_source_failure(self):
        responses = {query_url(ids_only=True): self.ids(), query_url(object_id=2): self.feature(2)}
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/"raw"
            with self.assertRaises(KeyError):
                capture(target, lambda u: responses[u])
            self.assertFalse(target.exists())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capture", action="store_true")
    p.add_argument("--output-dir")
    args = p.parse_args()
    if args.capture:
        if not args.output_dir:
            p.error("--output-dir is required for --capture")
        try:
            m = capture(Path(args.output_dir))
        except CaptureError as exc:
            p.exit(2, f"UNKNOWN/SOURCE_ACCESS_UNAVAILABLE_OR_INVALID: {exc}\n")
        print(json.dumps({"source_status": m["source_status"], "candidate_count": m["candidate_count"], "map_publication_authorized": False}, sort_keys=True))
    else:
        unittest.main(argv=[__file__])
