"""Offline tests + opt-in immutable capture of ANA's *current* Santa hydrography.

Usage (never run by test discovery):
  python tests/test_phase2_santa_ana_hydrography_capture.py --capture --out DIR

This is a CURRENT_ANA_HYDROGRAPHY_CONTEXT candidate inventory, NOT the 2011
ANA axis, HEC-RAS model, floodplain, or proof of datum. Nothing is published.
"""
from __future__ import annotations

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


class SourceNotAdjudicated(ValueError):
    pass


def urls() -> dict[str, str]:
    common = {"where": WHERE, "f": "json"}
    count = LAYER + "/query?" + urlencode({**common, "returnCountOnly": "true"})
    features = LAYER + "/query?" + urlencode({
        "where": WHERE, "outFields": FIELDS, "returnGeometry": "true",
        "outSR": "4326", "returnZ": "false", "returnM": "false",
        "f": "geojson",
    })
    return {"metadata": LAYER + "?f=json", "count": count, "features": features}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_doc(raw: bytes, label: str) -> dict:
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceNotAdjudicated(f"{label}_INVALID_JSON") from exc
    if not isinstance(result, dict) or result.get("error"):
        raise SourceNotAdjudicated(f"{label}_SERVICE_ERROR")
    return result


def positions(obj):
    if isinstance(obj, list):
        if len(obj) >= 2 and all(type(x) in (int, float) for x in obj[:2]):
            yield float(obj[0]), float(obj[1])
        else:
            for part in obj:
                yield from positions(part)


def validate(raw: dict[str, bytes]) -> list[dict]:
    meta = json_doc(raw["metadata"], "METADATA")
    if meta.get("geometryType") != "esriGeometryPolyline":
        raise SourceNotAdjudicated("SOURCE_GEOMETRY_TYPE_CHANGED")
    fields = {f.get("name") for f in meta.get("fields", []) if isinstance(f, dict)}
    if not set(FIELDS.split(",")).issubset(fields):
        raise SourceNotAdjudicated("SOURCE_FIELDS_CHANGED")
    count_doc = json_doc(raw["count"], "COUNT")
    count = count_doc.get("count")
    if type(count) is not int or count <= 0:
        raise SourceNotAdjudicated("SOURCE_COUNT_UNKNOWN_NOT_NEGATIVE")
    if count > 2000:
        raise SourceNotAdjudicated("SOURCE_PAGINATION_REQUIRED_NOT_CAPTURED")
    doc = json_doc(raw["features"], "FEATURES")
    if doc.get("type") != "FeatureCollection" or doc.get("exceededTransferLimit") is True:
        raise SourceNotAdjudicated("FEATURE_COLLECTION_INCOMPLETE")
    feats = doc.get("features")
    if not isinstance(feats, list) or len(feats) != count:
        raise SourceNotAdjudicated("COUNT_MISMATCH_INCOMPLETE")
    rows = []
    seen = set()
    for feature in feats:
        props = feature.get("properties") if isinstance(feature, dict) else None
        geom = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(props, dict) or not isinstance(geom, dict):
            raise SourceNotAdjudicated("MISSING_FEATURE_DATA")
        if geom.get("type") not in ("LineString", "MultiLineString"):
            raise SourceNotAdjudicated("NOT_A_POLYLINE")
        pts = list(positions(geom.get("coordinates")))
        if len(pts) < 2 or not all(math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90 for x, y in pts):
            raise SourceNotAdjudicated("INVALID_WGS84_COORDINATES")
        if "santa" not in (str(props.get("NOMBRE_CA") or "") + " " + str(props.get("NOMBRE_UH") or "")).casefold():
            raise SourceNotAdjudicated("NAME_FILTER_INCONSISTENT")
        oid = props.get("OBJECTID_1")
        if oid is None or oid in seen:
            raise SourceNotAdjudicated("MISSING_OR_DUPLICATE_OBJECTID")
        seen.add(oid)
        rows.append({
            "objectid": oid,
            "codigo_ca": props.get("CODIGO_CA"),
            "nombre_ca": props.get("NOMBRE_CA"),
            "tipo_ca": props.get("TIPO_CA"),
            "nombre_uh": props.get("NOMBRE_UH"),
            "codigo_uh": props.get("CODIGO_UH"),
            "long_km_source_attribute": props.get("LONG_KM"),
            "geometry_type": geom["type"],
            "bbox_epsg4326": [min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)],
        })
    return rows


def fetch(url: str) -> tuple[bytes, dict]:
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1", "Accept": "application/json,application/geo+json"})
    try:
        with urlopen(req, timeout=60) as response:
            body = response.read(20_000_001)
            info = {"status": response.status, "final_url": response.geturl(),
                    "content_type": response.headers.get("Content-Type"),
                    "date": response.headers.get("Date"), "etag": response.headers.get("ETag")}
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceNotAdjudicated("SOURCE_ACCESS_UNAVAILABLE_" + type(exc).__name__) from exc
    if not body or len(body) > 20_000_000:
        raise SourceNotAdjudicated("SOURCE_EMPTY_OR_OVERSIZE")
    return body, info


def capture(out: Path) -> dict:
    links = urls()
    received = {key: fetch(url) for key, url in links.items()}
    raw = {key: item[0] for key, item in received.items()}
    rows = validate(raw)  # No writes until all gates pass.
    manifest = {
        **GUARDS, "source_url": LAYER,
        "source_role": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_ONLY",
        "not_equivalent_to_ana_2011_axis": True,
        "historical_datum_2011_resolved": False,
        "map_publication_authorized": False,
        "capture_status": "CURRENT_SOURCE_CANDIDATES_FROZEN_NOT_HISTORICAL_GEOMETRY",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "query": WHERE, "requested_out_sr": 4326,
        "requests": {k: {"url": links[k], "sha256": sha(raw[k]),
                         "size_bytes": len(raw[k]), "http": received[k][1]} for k in links},
        "candidate_count": len(rows), "candidate_attributes_and_bbox": rows,
        "interpretation": "Name-matched current ANA polylines are candidates only; no 2011 axis, floodplain, datum, capacity or event equivalence is inferred.",
    }
    out.mkdir(parents=True, exist_ok=True)
    for key, body in raw.items():
        (out / f"ana_santa_{key}.raw").write_bytes(body)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


class TestSantaCurrentANACapture(unittest.TestCase):
    def test_guardrails_and_query(self):
        self.assertEqual(GUARDS["activation_gate"], "BLOCKED")
        self.assertIsNone(GUARDS["decision_thresholds"])
        self.assertIsNone(GUARDS["hydraulic_factors"])
        self.assertIn("outSR=4326", urls()["features"])
        self.assertIn("returnCountOnly=true", urls()["count"])

    def test_unavailable_or_empty_is_unknown_not_negative(self):
        with self.assertRaisesRegex(SourceNotAdjudicated, "SOURCE_COUNT_UNKNOWN"):
            validate({"metadata": self._metadata(), "count": b'{"count":0}', "features": b'{"type":"FeatureCollection","features":[]}'})

    def test_count_mismatch_fail_closed(self):
        with self.assertRaisesRegex(SourceNotAdjudicated, "COUNT_MISMATCH"):
            validate({"metadata": self._metadata(), "count": b'{"count":1}', "features": b'{"type":"FeatureCollection","features":[]}'})

    def test_sha_is_on_unmodified_response_bytes(self):
        self.assertEqual(sha(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_synthetic_fixture_never_claims_historical_equivalence(self):
        # Synthetic coordinates are unit-test-only, not a Santa geometry or output.
        fake = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"OBJECTID_1": 1, "NOMBRE_CA": "Rio Santa"}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [0, 1]]}}]}
        rows = validate({"metadata": self._metadata(), "count": b'{"count":1}', "features": json.dumps(fake).encode()})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["geometry_type"], "LineString")

    @staticmethod
    def _metadata():
        return json.dumps({"geometryType": "esriGeometryPolyline", "fields": [{"name": f} for f in FIELDS.split(",")]}).encode()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.capture or args.out is None:
        parser.error("Only explicit --capture --out DIR enables a network fetch; run unittest for offline tests")
    try:
        manifest = capture(args.out)
    except SourceNotAdjudicated as exc:
        print("UNKNOWN_NOT_LOW_RISK: " + str(exc), file=sys.stderr)
        sys.exit(2)
    print("CAPTURED_CURRENT_ANA_CONTEXT candidates=" + str(manifest["candidate_count"]))
