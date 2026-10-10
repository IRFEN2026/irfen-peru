#!/usr/bin/env python3
"""Research-only ANA current Santa hydrography raw-byte capture.

Source: ANA ONRH/Rios_Quebradas_AAVI/MapServer/0 (GeoJSON polylines);
documented in PR #334. Not the 2011 hydraulic axis or floodplain.
Offline: python tests/test_phase2_santa_ana_hydrography_freeze.py
Optional live: python tests/test_phase2_santa_ana_hydrography_freeze.py --capture DIR
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import unittest
from pathlib import Path
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


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def urls() -> tuple[str, str]:
    metadata = LAYER + "?" + urlencode({"f": "json"})
    query = LAYER + "/query?" + urlencode({
        "where": WHERE, "outFields": FIELDS, "returnGeometry": "true",
        "outSR": "4326", "returnZ": "false", "returnM": "false", "f": "geojson",
    })
    return metadata, query


def fetch(url: str) -> bytes:
    request = Request(url, headers={
        "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
        "Accept": "application/json,application/geo+json",
    })
    try:
        with urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise CaptureError("SOURCE_ACCESS_UNAVAILABLE")
            raw = response.read(16_000_001)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CaptureError("SOURCE_ACCESS_UNAVAILABLE") from exc
    if not raw or len(raw) > 16_000_000:
        raise CaptureError("SOURCE_ACCESS_UNAVAILABLE")
    return raw


def decode(raw: bytes) -> dict:
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CaptureError("SOURCE_RESPONSE_UNPARSEABLE") from exc
    if not isinstance(obj, dict) or obj.get("error"):
        raise CaptureError("SOURCE_RESPONSE_INVALID")
    return obj


def validate_metadata(obj: dict) -> None:
    if obj.get("geometryType") != "esriGeometryPolyline":
        raise CaptureError("SOURCE_SCHEMA_DRIFT")
    fields = {f.get("name") for f in obj.get("fields", []) if isinstance(f, dict)}
    if not set(FIELDS.split(",")).issubset(fields):
        raise CaptureError("SOURCE_SCHEMA_DRIFT")
    if "geojson" not in str(obj.get("supportedQueryFormats", "")).lower():
        raise CaptureError("SOURCE_SCHEMA_DRIFT")


def positions(coords):
    if isinstance(coords, list):
        if len(coords) >= 2 and all(type(v) in (int, float) for v in coords[:2]):
            yield float(coords[0]), float(coords[1])
        else:
            for part in coords:
                yield from positions(part)


def validate_candidates(obj: dict) -> tuple[str, list[dict]]:
    if obj.get("exceededTransferLimit") is True:
        raise CaptureError("SOURCE_RESULT_INCOMPLETE")
    features = obj.get("features")
    if not isinstance(features, list):
        raise CaptureError("SOURCE_RESPONSE_INVALID")
    rows = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise CaptureError("SOURCE_RESPONSE_INVALID")
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in ("LineString", "MultiLineString"):
            raise CaptureError("SOURCE_GEOMETRY_UNADJUDICATED")
        points = list(positions(geometry.get("coordinates")))
        if not points or any(
            not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90)
            for x, y in points
        ):
            raise CaptureError("SOURCE_GEOMETRY_UNADJUDICATED")
        props = feature.get("properties") or {}
        rows.append({
            "codigo_ca": props.get("CODIGO_CA"),
            "nombre_ca": props.get("NOMBRE_CA"),
            "tipo_ca": props.get("TIPO_CA"),
            "nombre_uh": props.get("NOMBRE_UH"),
            "codigo_uh": props.get("CODIGO_UH"),
            "long_km_source": props.get("LONG_KM"),
            "geometry_type": geometry["type"],
            "bbox_epsg4326": [
                min(x for x, _ in points), min(y for _, y in points),
                max(x for x, _ in points), max(y for _, y in points),
            ],
        })
    status = (
        "CURRENT_ANA_HYDROGRAPHY_CANDIDATES_UNADJUDICATED"
        if rows else "UNKNOWN_NO_CANDIDATES_IN_RESPONSE"
    )
    return status, rows


def capture(directory: Path, retrieve=fetch) -> dict:
    metadata_url, query_url = urls()
    # Fail closed: validate both complete raw responses before writing any file.
    metadata_raw = retrieve(metadata_url)
    validate_metadata(decode(metadata_raw))
    query_raw = retrieve(query_url)
    status, rows = validate_candidates(decode(query_raw))
    manifest = {
        **GUARDS,
        "source_institution": "Autoridad Nacional del Agua (ANA)",
        "source_layer": LAYER,
        "metadata_url": metadata_url,
        "query_url": query_url,
        "metadata_sha256": sha(metadata_raw),
        "metadata_bytes": len(metadata_raw),
        "query_response_sha256": sha(query_raw),
        "query_response_bytes": len(query_raw),
        "capture_status": status,
        "candidates": rows,
        "geometry_role": "CURRENT_ANA_HYDROGRAPHY_CONTEXT_ONLY",
        "historical_2011_datum_adjudicated": False,
        "historical_2011_axis_equivalence": False,
        "map_publication_authorized": False,
        "source_is_not_hydraulic_model_or_floodplain": True,
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.raw.json").write_bytes(metadata_raw)
    (directory / "query.raw.geojson").write_bytes(query_raw)
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


class TestSantaHydrographyFreeze(unittest.TestCase):
    def test_query_and_guards(self):
        _, query = urls()
        self.assertIn("outSR=4326", query)
        self.assertIn("geojson", query)
        self.assertEqual(GUARDS["activation_gate"], "BLOCKED")
        self.assertEqual(GUARDS["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(GUARDS["decision_thresholds"])
        self.assertIsNone(GUARDS["hydraulic_factors"])

    def test_synthetic_raw_sha_and_no_promotion(self):
        from tempfile import TemporaryDirectory
        metadata = json.dumps({
            "geometryType": "esriGeometryPolyline",
            "supportedQueryFormats": "JSON, geoJSON",
            "fields": [{"name": n} for n in FIELDS.split(",")],
        }).encode()
        query = json.dumps({"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"NOMBRE_CA": "SANTA"},
            "geometry": {"type": "LineString", "coordinates": [[-78.5, -8.9], [-78.4, -8.8]]},
        }]}).encode()
        with TemporaryDirectory() as d:
            result = capture(Path(d), lambda u: metadata if "?f=json" in u else query)
            self.assertEqual(result["query_response_sha256"], sha(query))
            self.assertFalse(result["map_publication_authorized"])
            self.assertFalse(result["historical_2011_axis_equivalence"])
            self.assertEqual((Path(d) / "query.raw.geojson").read_bytes(), query)

    def test_truncated_result_never_writes(self):
        from tempfile import TemporaryDirectory
        metadata = json.dumps({
            "geometryType": "esriGeometryPolyline",
            "supportedQueryFormats": "geoJSON",
            "fields": [{"name": n} for n in FIELDS.split(",")],
        }).encode()
        query = b'{"features":[],"exceededTransferLimit":true}'
        with TemporaryDirectory() as d:
            out = Path(d) / "capture"
            with self.assertRaisesRegex(CaptureError, "SOURCE_RESULT_INCOMPLETE"):
                capture(out, lambda u: metadata if "?f=json" in u else query)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--capture":
        try:
            result = capture(Path(sys.argv[2]))
            print(json.dumps({
                "capture_status": result["capture_status"],
                "query_response_sha256": result["query_response_sha256"],
            }))
        except CaptureError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
    else:
        unittest.main()
