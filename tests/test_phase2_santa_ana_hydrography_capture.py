"""Fail-closed research capture of CURRENT ANA Santa-name hydrography candidates.

Institutional source (ANA, DCERH, 2018):
https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0

This is NOT the 2011 lower-Santa axis, floodplain, HEC-RAS model, or a
demonstration of datum equivalence. Run only when the public service responds:
    python tests/test_phase2_santa_ana_hydrography_capture.py --capture OUTPUT_DIR

The output directory must not exist. Commit the immutable archive only after
reviewing its attributes, raw SHA-256, and institutional source provenance.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timezone

LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
WHERE = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM"
LIMIT = 16_000_000


def urls():
    base = LAYER + "/query?"
    count = base + urlencode({"where": WHERE, "returnCountOnly": "true", "f": "json"})
    features = base + urlencode({
        "where": WHERE, "outFields": FIELDS, "returnGeometry": "true",
        "outSR": "4326", "orderByFields": "OBJECTID_1 ASC", "f": "geojson",
    })
    return count, features


def retrieve(url):
    request = Request(url, headers={
        "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
        "Accept": "application/geo+json,application/json",
    })
    with urlopen(request, timeout=60) as response:
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT:
            raise ValueError("SOURCE_RESPONSE_TOO_LARGE")
        return body, {
            "final_url": response.geturl(), "status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }


def positions(geometry):
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "LineString":
        lines = [coordinates]
    elif kind == "MultiLineString":
        lines = coordinates
    else:
        raise ValueError("NON_POLYLINE_CANDIDATE")
    if not isinstance(lines, list) or not lines:
        raise ValueError("EMPTY_POLYLINE")
    result = []
    for line in lines:
        if not isinstance(line, list) or len(line) < 2:
            raise ValueError("INVALID_LINE")
        for point in line:
            if not isinstance(point, list) or len(point) < 2:
                raise ValueError("INVALID_POSITION")
            lon, lat = point[:2]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                   not math.isfinite(v) for v in (lon, lat)):
                raise ValueError("NON_FINITE_POSITION")
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("OUTSIDE_EPSG4326_DOMAIN")
            result.append((lon, lat))
    return result


def assess(count_body, raw_body):
    count_doc = json.loads(count_body)
    count = count_doc.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("INVALID_SOURCE_COUNT")
    doc = json.loads(raw_body)
    if doc.get("type") != "FeatureCollection" or doc.get("exceededTransferLimit"):
        raise ValueError("INVALID_OR_TRUNCATED_FEATURE_COLLECTION")
    features = doc.get("features")
    if not isinstance(features, list) or len(features) != count:
        raise ValueError("COUNT_MISMATCH_OR_PAGINATION")
    rows, seen = [], set()
    for feature in features:
        if feature.get("type") != "Feature":
            raise ValueError("INVALID_FEATURE")
        props = feature.get("properties")
        if not isinstance(props, dict) or any(k not in props for k in FIELDS.split(",")):
            raise ValueError("MISSING_SOURCE_ATTRIBUTES")
        oid = props["OBJECTID_1"]
        if oid is None or isinstance(oid, bool) or not isinstance(oid, (int, str)) or oid in seen:
            raise ValueError("MISSING_OR_DUPLICATE_OBJECTID")
        seen.add(oid)
        xy = positions(feature.get("geometry") or {})
        rows.append({
            "objectid": oid,
            "codigo_ca": props["CODIGO_CA"], "nombre_ca": props["NOMBRE_CA"],
            "tipo_ca": props["TIPO_CA"], "nombre_uh": props["NOMBRE_UH"],
            "codigo_uh": props["CODIGO_UH"], "long_km_source": props["LONG_KM"],
            "geometry_type": feature["geometry"]["type"],
            "bbox_epsg4326": [min(p[0] for p in xy), min(p[1] for p in xy),
                              max(p[0] for p in xy), max(p[1] for p in xy)],
        })
    return sorted(rows, key=lambda row: str(row["objectid"]))


def capture(target, getter=retrieve):
    """All remote responses and checks complete before any target is created."""
    target = Path(target)
    if target.exists():
        raise FileExistsError("IMMUTABLE_ARCHIVE_ALREADY_EXISTS")
    count_url, feature_url = urls()
    count_body, count_http = getter(count_url)
    raw_body, feature_http = getter(feature_url)
    for http in (count_http, feature_http):
        if http.get("status") != 200:
            raise ValueError("NON_200_SOURCE")
    rows = assess(count_body, raw_body)
    manifest = {
        "source": "ANA DCERH institutional hydrography, service metadata 2018",
        "source_layer": LAYER,
        "capture_utc": datetime.now(timezone.utc).isoformat(),
        "where": WHERE, "fields": FIELDS,
        "source_count": len(rows), "candidate_features": rows,
        "count_request": {"url": count_url, "http": count_http,
                          "raw_sha256": hashlib.sha256(count_body).hexdigest()},
        "feature_request": {"url": feature_url, "http": feature_http,
                            "raw_sha256": hashlib.sha256(raw_body).hexdigest()},
        "source_crs": "EPSG:4326",
        "classification": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_CANDIDATES_ONLY",
        "historical_2011_axis_equivalence": False,
        "historical_2011_datum_established": False,
        "map_publication": False, "production_use": False,
        "production_ready": False, "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None, "hydraulic_factors": None,
        "modes": ["RESEARCH_ONLY", "TEST_ONLY"],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".santa-ana-stage-", dir=target.parent))
    try:
        blobs = {"count.json": count_body, "candidates.geojson": raw_body,
                 "manifest.json": manifest_bytes}
        for name, body in blobs.items():
            (stage / name).write_bytes(body)
        (stage / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(body).hexdigest()}  {name}\n"
            for name, body in sorted(blobs.items())), encoding="ascii")
        if target.exists():
            raise FileExistsError("IMMUTABLE_ARCHIVE_ALREADY_EXISTS")
        os.rename(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


class TestSantaANACaptureOffline(unittest.TestCase):
    @staticmethod
    def example():
        props = dict.fromkeys(FIELDS.split(","), None)
        props.update({"OBJECTID_1": 7, "NOMBRE_CA": "Santa"})
        return {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": props,
            "geometry": {"type": "LineString", "coordinates": [[-78.5, -9.1], [-78.4, -9.0]]},
        }]}

    def fake(self, count=1, doc=None):
        raw = json.dumps(doc if doc is not None else self.example()).encode()
        def get(url):
            body = json.dumps({"count": count}).encode() if "returnCountOnly" in url else raw
            return body, {"status": 200, "final_url": url}
        return get, raw

    def test_success_hashes_and_non_operational_contract(self):
        with tempfile.TemporaryDirectory() as d:
            getter, raw = self.fake()
            target = Path(d) / "archive"
            manifest = capture(target, getter)
            self.assertEqual((target / "candidates.geojson").read_bytes(), raw)
            self.assertEqual(manifest["feature_request"]["raw_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertEqual(manifest["candidate_features"][0]["bbox_epsg4326"],
                             [-78.5, -9.1, -78.4, -9.0])
            self.assertFalse(manifest["map_publication"])
            self.assertEqual(manifest["activation_gate"], "BLOCKED")
            self.assertIsNone(manifest["decision_thresholds"])
            for line in (target / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ")
                self.assertEqual(digest, hashlib.sha256((target / name).read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                capture(target, getter)

    def test_count_mismatch_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "archive"
            with self.assertRaisesRegex(ValueError, "COUNT_MISMATCH"):
                capture(target, self.fake(count=2)[0])
            self.assertFalse(target.exists())

    def test_invalid_geometry_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self.example()
            doc["features"][0]["geometry"]["type"] = "Polygon"
            target = Path(d) / "archive"
            with self.assertRaisesRegex(ValueError, "NON_POLYLINE"):
                capture(target, self.fake(doc=doc)[0])
            self.assertFalse(target.exists())

    def test_source_access_failure_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "archive"
            def unavailable(_):
                raise URLError("transient")
            with self.assertRaises(URLError):
                capture(target, unavailable)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--capture":
        try:
            report = capture(Path(sys.argv[2]))
        except (HTTPError, URLError, TimeoutError) as exc:
            print("SOURCE_ACCESS_UNAVAILABLE: " + type(exc).__name__, file=sys.stderr)
            sys.exit(2)
        print(json.dumps({"count": report["source_count"],
                          "sha256": report["feature_request"]["raw_sha256"]}))
    else:
        unittest.main()
