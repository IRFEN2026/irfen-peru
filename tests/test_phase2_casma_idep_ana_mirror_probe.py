"""Fail-closed, independently sourced IDEP/ANA-attributed Casma N7 mirror probe.

Metadata observed 2026-10-24:
https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/FeatureServer/7
Government IDEP host; polygon Feature Layer, fields NIVEL7/CODIGO/NOMBRE/
AREA_KM2, maxRecordCount 1000, geoJSON query, service CRS EPSG:3857.
This is NOT evidence of original INRENA Uh_pfas100 lineage, identical bytes,
2007 geometry, topology, or operational map suitability.

Offline unittest discovery does not make HTTP requests. Optional manual
capture is all-or-nothing and archives source bytes and SHA-256 per code.
"""
import argparse
import hashlib
import json
import math
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

LAYER = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/FeatureServer/7"
CODES = tuple(f"137596{i}" for i in range(1, 10))
FIELDS = "OBJECTID_1,NIVEL7,CODIGO,NOMBRE,AREA_KM2"
MAX_BYTES = 16_000_000
GUARDS = {
    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
    "production_use": False, "production_ready": False,
    "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None, "hydraulic_factors": None,
    "map_publication_enabled": False,
    "historical_geometry_equivalence_to_Uh_pfas100": False,
}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def query_url(code):
    if code not in CODES:
        raise ValueError("code outside preregistered Casma N7 set")
    params = {
        "where": "NIVEL7='{}'".format(code),
        "outFields": FIELDS, "returnGeometry": "true",
        "outSR": "4326", "f": "geojson",
    }
    return LAYER + "/query?" + urlencode(params)


def candidate(raw, code):
    """Check only capture identity/structure; NOT GEOS topology or lineage."""
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get("error") or doc.get("exceededTransferLimit"):
        raise ValueError("error or truncated response")
    if doc.get("type") != "FeatureCollection":
        raise ValueError("not a GeoJSON FeatureCollection")
    if "crs" in doc:
        crs = doc["crs"]
        if not (isinstance(crs, dict) and crs.get("type") == "name"
                and isinstance(crs.get("properties"), dict)
                and crs["properties"].get("name") in (
                    "EPSG:4326", "OGC:CRS84", "urn:ogc:def:crs:OGC::CRS84")):
            raise ValueError("explicit incompatible or unverified CRS")
    features = doc.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise ValueError("unknown candidate cardinality, not negative evidence")
    feature = features[0]
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError("invalid feature")
    attrs = feature.get("properties")
    if not isinstance(attrs, dict):
        raise ValueError("missing attributes")
    if str(attrs.get("NIVEL7")) != code or str(attrs.get("CODIGO")) != code:
        raise ValueError("NIVEL7/CODIGO identity mismatch; no tolerance")
    oid = attrs.get("OBJECTID_1")
    if isinstance(oid, bool) or not isinstance(oid, int) or oid < 0:
        raise ValueError("missing stable source object id")
    geom = feature.get("geometry")
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("not a polygon")
    polygons = ([geom.get("coordinates")] if geom["type"] == "Polygon"
                else geom.get("coordinates"))
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("missing polygon coordinates")
    xy = []
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("missing rings")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("invalid or unclosed ring")
            for point in ring:
                if not isinstance(point, list) or len(point) < 2:
                    raise ValueError("invalid position")
                x, y = point[:2]
                if any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in (x, y)):
                    raise ValueError("nonfinite position")
                if not (-180 <= x <= 180 and -90 <= y <= 90):
                    raise ValueError("position outside global lon/lat range")
                xy.append((x, y))
    if not xy:
        raise ValueError("empty geometry")
    return {
        "code": code, "source_objectid": oid, "source_name": attrs.get("NOMBRE"),
        "source_area_km2": attrs.get("AREA_KM2"),
        "geometry_type": geom["type"],
        "bbox_wgs84": [min(x for x, _ in xy), min(y for _, y in xy),
                       max(x for x, _ in xy), max(y for _, y in xy)],
        "topology_validated": False, "lineage_established": False,
    }


def validate_capture_candidate(raw, code):
    """Keep rejected source candidates UNKNOWN but expose a bounded reason for QA.

    Only the preregistered code and static validator message enter CI logs;
    never log raw response bytes or treat a rejection as a negative observation.
    """
    try:
        return candidate(raw, code)
    except ValueError as exc:
        raise ValueError(f"source candidate rejected code={code}: {exc}") from exc


def capture(out_dir):
    """All nine must validate before ANY archive is written to out_dir."""
    opener = build_opener(NoRedirects())
    records, payloads = [], {}
    for code in CODES:
        url = query_url(code)
        req = Request(url, headers={
            "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
            "Accept": "application/geo+json,application/json",
        })
        with opener.open(req, timeout=35) as response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError("source status/URL mismatch")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("response size bound exceeded")
            http = {
                "status": response.status, "requested_url": url,
                "final_url": response.geturl(),
                "content_type": response.headers.get("Content-Type"),
                "http_date": response.headers.get("Date"),
                "etag": response.headers.get("ETag"),
            }
        record = validate_capture_candidate(raw, code)
        record.update({
            "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_response_bytes": len(raw), "http_provenance": http,
            "raw_path": f"{code}.geojson",
        })
        records.append(record)
        payloads[code] = raw
    manifest = {
        "source_metadata_url": LAYER, "source_metadata_observed_utc": "2026-10-24",
        "source_custody": "IDEP_GOV_HOSTED_ANA_ATTRIBUTED_LINEAGE_UNVERIFIED",
        "original_Uh_pfas100_identity_proven": False,
        "official_ANA_source_byte_equivalence_proven": False,
        "independent_n7_capture_count": len(records),
        "topology_gate_c_changed": False, "gate_b": "NOT_ESTABLISHED",
        "capture_utc": datetime.now(timezone.utc).isoformat(),
        "features": records, **GUARDS,
    }
    out = Path(out_dir)
    if out.exists():
        raise FileExistsError("refuse overwrite of archived evidence")
    # Only publish output after complete validation; no partial successful codes.
    out.mkdir(parents=True, exist_ok=False)
    for code, raw in payloads.items():
        (out / f"{code}.geojson").write_bytes(raw)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    return manifest


class TestCasmaIDEPIndependentMirrorContract(unittest.TestCase):
    def sample(self, code=CODES[0], oid=11):
        # Synthetic software fixture; not a Casma location or source observation.
        return json.dumps({"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {"OBJECTID_1": oid, "NIVEL7": code,
                           "CODIGO": code, "NOMBRE": "SYNTHETIC", "AREA_KM2": None},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        }]}).encode()

    def test_preregistered_nine_exact_codes_and_no_area_tolerance(self):
        self.assertEqual(CODES, tuple(f"137596{i}" for i in range(1, 10)))
        self.assertEqual(candidate(self.sample(), CODES[0])["code"], CODES[0])
        self.assertEqual(candidate(self.sample(), CODES[0])["topology_validated"], False)
        with self.assertRaises(ValueError):
            candidate(self.sample(), CODES[1])
        with self.assertRaises(ValueError):
            query_url("1375970")

    def test_reject_nonpolygon_and_unclosed_ring(self):
        for geometry in (
            {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1]]]},
        ):
            obj = json.loads(self.sample())
            obj["features"][0]["geometry"] = geometry
            with self.assertRaises(ValueError):
                candidate(json.dumps(obj).encode(), CODES[0])

    def test_reject_empty_duplicate_or_error_as_unknown(self):
        obj = json.loads(self.sample())
        for features in ([], obj["features"] * 2):
            obj["features"] = features
            with self.assertRaises(ValueError):
                candidate(json.dumps(obj).encode(), CODES[0])
        with self.assertRaises(ValueError):
            candidate(b'{"error":{"message":"unavailable"}}', CODES[0])
        with self.assertRaisesRegex(
            ValueError, "source candidate rejected code=1375961: unknown candidate cardinality"
        ):
            validate_capture_candidate(
                b'{"type":"FeatureCollection","features":[]}', CODES[0]
            )

    def test_source_custody_and_fail_closed_guards(self):
        self.assertIn("idep.gob.pe", LAYER)
        self.assertIn("ANA_WMS", LAYER)
        self.assertFalse(GUARDS["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(GUARDS["production_use"])
        self.assertFalse(GUARDS["production_ready"])
        self.assertFalse(GUARDS["operational_alerting_enabled"])
        self.assertFalse(GUARDS["map_publication_enabled"])
        self.assertEqual(GUARDS["activation_gate"], "BLOCKED")
        self.assertEqual(GUARDS["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(GUARDS["decision_thresholds"])
        self.assertIsNone(GUARDS["hydraulic_factors"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true",
                        help="explicitly attempt all nine public source queries")
    parser.add_argument("--out-dir")
    args, remaining = parser.parse_known_args()
    if args.capture:
        if not args.out_dir:
            parser.error("--capture requires --out-dir")
        try:
            print(json.dumps(capture(args.out_dir), ensure_ascii=False, sort_keys=True))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            # Preserve UNKNOWN and expose only bounded validator diagnostics.
            detail = (str(exc) if isinstance(exc, ValueError) and
                      str(exc).startswith("source candidate rejected code=")
                      else type(exc).__name__)
            raise SystemExit("UNKNOWN_SOURCE_ACCESS_UNAVAILABLE_OR_INVALID: "
                             + detail) from exc
    else:
        unittest.main(argv=["test_phase2_casma_idep_ana_mirror_probe.py"] + remaining)
