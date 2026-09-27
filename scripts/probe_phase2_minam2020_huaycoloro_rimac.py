#!/usr/bin/env python3
"""Live MINAM Huaycoloro/Rímac vector probe for Phase-2 QA.

RESEARCH_ONLY / TEST_ONLY. This probe can freeze reproducible source payload
hashes and expose geometric candidates. It MUST NOT promote a name match or
literal source-line intersection to hydrologic identity, an official
confluence, routing, travel time, discharge, capacity, overflow or map
publication.

Source access failure remains UNKNOWN. A completed zero-result query is not
hydrologic absence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LAYER_ENDPOINT = (
    "https://geoservidorperu.minam.gob.pe/arcgis/rest/services/"
    "CS/Desarrollo_Urbano/MapServer/10"
)
QUERY_ENDPOINT = LAYER_ENDPOINT + "/query"
OUT = ROOT / "artifacts/phase2_minam2020_huaycoloro_rimac_probe.json"
TARGET_NAMES = ("HUAYCOLORO", "RIMAC", "RÍMAC")
OUT_FIELDS = (
    "OBJECTID,COD_RIO,TIPO,SUBTIPO,NOM_RIO,NOM_UH,LONG_KM,LONG_M,"
    "LABEL_RIO,NOMBDIST,NOMBPROV,NOMBDEP"
)

class SourceAccessError(Exception):
    pass

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(s.split())

def query_url() -> str:
    where = " OR ".join(f"NOM_RIO='{name}'" for name in TARGET_NAMES)
    params = {
        "where": where,
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return QUERY_ENDPOINT + "?" + urlencode(params)

def fetch(timeout: int = 30):
    req = Request(query_url(), headers={"User-Agent": "IRFEN-research-minam-huaycoloro-probe/0.1"})
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except (TimeoutError, URLError, OSError) as exc:
        raise SourceAccessError(f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceAccessError(f"{type(exc).__name__}: {exc}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise SourceAccessError(json.dumps(data["error"], ensure_ascii=False, sort_keys=True))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise SourceAccessError("MINAM response is not a GeoJSON FeatureCollection")
    return raw, data

def iter_lines(geometry: dict):
    if not geometry:
        return
    typ = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if typ == "LineString":
        yield coords
    elif typ == "MultiLineString":
        yield from coords

def _cross(ax, ay, bx, by):
    return ax * by - ay * bx

def segment_intersection(a, b, c, d, eps=1e-12):
    ax, ay = map(float, a); bx, by = map(float, b)
    cx, cy = map(float, c); dx, dy = map(float, d)
    rx, ry = bx-ax, by-ay
    sx, sy = dx-cx, dy-cy
    den = _cross(rx, ry, sx, sy)
    qpx, qpy = cx-ax, cy-ay
    if abs(den) <= eps:
        return None
    t = _cross(qpx, qpy, sx, sy) / den
    u = _cross(qpx, qpy, rx, ry) / den
    if -eps <= t <= 1+eps and -eps <= u <= 1+eps:
        return [ax+t*rx, ay+t*ry]
    return None

def exact_intersections(g1: dict, g2: dict):
    pts = []
    for l1 in iter_lines(g1) or []:
        for l2 in iter_lines(g2) or []:
            for a, b in zip(l1, l1[1:]):
                for c, d in zip(l2, l2[1:]):
                    p = segment_intersection(a, b, c, d)
                    if p is not None and all(math.isfinite(x) for x in p):
                        if not any(abs(p[0]-q[0]) < 1e-10 and abs(p[1]-q[1]) < 1e-10 for q in pts):
                            pts.append(p)
    return pts

def fail_closed_guards():
    return {
        "name_match_confirms_local_identity": False,
        "literal_line_intersection_confirms_official_confluence": False,
        "exact_huaycoloro_rimac_confluence_resolved": False,
        "routing_enabled": False,
        "travel_time_enabled": False,
        "flow_or_capacity_inference_enabled": False,
        "overflow_inference_enabled": False,
        "map_publish_enabled": False,
        "zero_query_result_may_be_inferred_as_hydrologic_absence": False,
    }

def build(raw: bytes, data: dict):
    groups = {"huaycoloro": [], "rimac": []}
    for feature in data.get("features") or []:
        props = dict(feature.get("properties") or {})
        name = norm(props.get("NOM_RIO"))
        key = "huaycoloro" if name == "HUAYCOLORO" else ("rimac" if name == "RIMAC" else None)
        if key is None:
            continue
        geom = feature.get("geometry")
        groups[key].append({
            "objectid": props.get("OBJECTID"),
            "properties": props,
            "geometry": geom,
            "geometry_sha256": hashlib.sha256(canonical(geom)).hexdigest(),
        })

    intersections = []
    for hi, hf in enumerate(groups["huaycoloro"]):
        for ri, rf in enumerate(groups["rimac"]):
            pts = exact_intersections(hf["geometry"], rf["geometry"])
            if pts:
                intersections.append({
                    "huaycoloro_candidate_index": hi,
                    "rimac_candidate_index": ri,
                    "intersection_count": len(pts),
                    "literal_source_line_intersections": pts,
                    "scientific_status": "GEOMETRIC_INTERSECTION_CANDIDATE_NOT_ADJUDICATED_CONFLUENCE",
                })

    objectids = sorted({
        int(row["objectid"])
        for rows in groups.values()
        for row in rows
        if row["objectid"] is not None
    })

    return {
        "schema_version": "0.1",
        "status": "RESEARCH_ONLY_LIVE_VECTOR_PROBE",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "query_completed": True,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "institution": "Ministerio del Ambiente",
            "platform": "Geoservidor",
            "layer": "CS/Desarrollo_Urbano/MapServer/10",
            "attribution": "IMP/ANA",
            "source_year": 2020,
            "query_url": query_url(),
            "query_format": "geoJSON",
            "requested_out_sr": 4326,
            "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
            "canonical_payload_sha256": hashlib.sha256(canonical(data)).hexdigest(),
        },
        "candidate_counts": {k: len(v) for k, v in groups.items()},
        "matching_objectids": objectids,
        "matching_feature_count": sum(len(v) for v in groups.values()),
        "candidates": groups,
        "literal_intersection_candidates": intersections,
        "guards": fail_closed_guards(),
    }

def build_unavailable(exc: Exception):
    return {
        "schema_version": "0.1",
        "status": "SOURCE_ACCESS_UNAVAILABLE",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "query_completed": False,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "institution": "Ministerio del Ambiente",
            "platform": "Geoservidor",
            "layer": "CS/Desarrollo_Urbano/MapServer/10",
            "query_url": query_url(),
        },
        "candidate_counts": {"huaycoloro": None, "rimac": None},
        "matching_objectids": None,
        "matching_feature_count": None,
        "candidates": None,
        "literal_intersection_candidates": None,
        "access": {
            "error_class": type(exc).__name__,
            "error_message": str(exc),
            "zero_candidates_inferred": False,
            "hydrologic_absence_inferred": False,
        },
        "guards": fail_closed_guards(),
    }

def self_test():
    url = query_url()
    assert "returnGeometry=true" in url
    assert "outSR=4326" in url
    assert "NOM_RIO%3D%27HUAYCOLORO%27" in url
    a = {"type":"LineString","coordinates":[[0,0],[2,2]]}
    b = {"type":"LineString","coordinates":[[0,2],[2,0]]}
    assert exact_intersections(a,b) == [[1.0,1.0]]
    d = build_unavailable(SourceAccessError("timeout"))
    assert d["query_completed"] is False
    assert d["candidate_counts"] == {"huaycoloro": None, "rimac": None}
    assert d["guards"]["zero_query_result_may_be_inferred_as_hydrologic_absence"] is False
    print("self-test ok")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw, data = fetch()
        doc = build(raw, data)
        code = 0
    except SourceAccessError as exc:
        doc = build_unavailable(exc)
        code = 2
    path.write_bytes(canonical(doc))
    print(json.dumps({
        "status": doc["status"],
        "query_completed": doc["query_completed"],
        "candidate_counts": doc["candidate_counts"],
        "matching_feature_count": doc["matching_feature_count"],
        "intersection_candidate_count": None if doc["literal_intersection_candidates"] is None else len(doc["literal_intersection_candidates"]),
        "output": str(path),
    }, ensure_ascii=False, sort_keys=True))
    return code

if __name__ == "__main__":
    raise SystemExit(main())
